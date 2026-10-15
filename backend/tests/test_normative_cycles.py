from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Normative, NormativeSubmission, NormativeSubmissionFile, Notification, User
from app.schemas.core import NormativeCreate, NormativeUpdate
from app.services import normative_cycles, normatives, normative_progress


def weekly(**extra):
    return SimpleNamespace(
        id=1,
        title="Приседания",
        recurrence_days=7,
        recurrence_start_date=date(2026, 10, 5),
        created_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
        is_active=True,
        squad_id=None,
        target_audience="ALL",
        **extra,
    )


def test_cycle_changes_at_monday_midnight_barnaul():
    sunday = datetime(2026, 10, 11, 16, 59, 59, tzinfo=timezone.utc)
    monday = sunday + timedelta(seconds=1)
    first = normative_cycles.normative_period(weekly(), sunday)
    second = normative_cycles.normative_period(weekly(), monday)
    assert first.start == date(2026, 10, 5)
    assert first.closes_at == monday
    assert second.start == date(2026, 10, 12)
    assert second.end == date(2026, 10, 19)
    assert second.opens_at == monday
    assert normative_cycles.monday_in_club(monday.replace(tzinfo=None)) == second.start
    assert normative_cycles.normative_period(weekly(), monday.replace(tzinfo=None)) == second


def test_future_cycle_is_not_open_and_one_off_never_resets():
    now = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
    assert not normative_cycles.attach_period(weekly(), now).is_submission_open
    once = weekly()
    once.recurrence_days = None
    assert normative_cycles.normative_period(once, now).start is None
    assert normative_cycles.is_current_submission(
        once, SimpleNamespace(period_start_date=None), now + timedelta(days=100)
    )


def test_weekly_start_must_be_monday():
    for schema in (NormativeCreate, NormativeUpdate):
        with pytest.raises(ValidationError, match="понедельник"):
            schema(title="Бег", recurrence_days=7, recurrence_start_date=date(2026, 10, 13))
    assert NormativeCreate(title="Бег", recurrence_days=7).recurrence_start_date is None


def test_progress_preserves_history_and_excludes_other_squads(monkeypatch):
    now = datetime(2026, 10, 11, 17, tzinfo=timezone.utc)
    monkeypatch.setattr(normative_cycles, "utcnow", lambda: now)
    user = SimpleNamespace(id=1, full_name="Иванов Иван", role_code="PARTICIPANT", squad_id=1)
    norm = weekly()
    foreign = weekly()
    foreign.id, foreign.squad_id = 2, 2
    submissions = [
        SimpleNamespace(
            user_id=1,
            normative_id=1,
            status_code="ACCEPTED",
            period_start_date=date(2026, 10, 5),
            submitted_at=now - timedelta(days=1),
        )
    ]
    progress = normative_progress.member_progress(user, [norm, foreign], submissions)
    assert (progress["accepted"], progress["missing"], progress["total"], progress["accepted_all_time"]) == (0, 1, 1, 1)
    submissions.append(
        SimpleNamespace(
            user_id=1, normative_id=1, status_code="PENDING", period_start_date=date(2026, 10, 12), submitted_at=now
        )
    )
    progress = normative_progress.member_progress(user, [norm], submissions)
    assert progress["pending"] == 1 and progress["percent"] == 0
    submissions[-1].status_code = "ACCEPTED"
    assert normative_progress.member_progress(user, [norm], submissions)["percent"] == 100


class AsyncAdapter:
    def __init__(self, db):
        self.db = db

    def add(self, item):
        self.db.add(item)

    async def scalar(self, query):
        return self.db.scalar(query)

    async def scalars(self, query):
        return self.db.scalars(query)

    async def execute(self, query):
        return self.db.execute(query)

    async def flush(self):
        self.db.flush()


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite://")
    for model in (User, Normative, NormativeSubmission, NormativeSubmissionFile, Notification):
        model.__table__.create(engine)
    monkeypatch.setattr(normatives, "record_audit", AsyncMock())
    with Session(engine, expire_on_commit=False) as db:
        user = User(id=1, full_name="Participant", telegram_id=1, role_code="PARTICIPANT", status_code="ACTIVE")
        commander = User(id=2, full_name="Admin", telegram_id=2, role_code="SUPER_ADMIN", status_code="ACTIVE")
        norm = Normative(
            id=1,
            title="Приседания",
            type_code="GENERAL",
            recurrence_days=7,
            recurrence_start_date=date(2026, 10, 5),
            created_by_user_id=2,
        )
        db.add_all([user, commander, norm])
        db.flush()
        yield db, AsyncAdapter(db), user, norm
    engine.dispose()


async def submit(session, user, norm, **extra):
    return await normatives.submit_normative(
        session,
        normative=norm,
        submitter=user,
        status_code="SUBMITTED",
        comment="new work",
        file_ids=extra.pop("file_ids", []),
        audit_action_code="test",
        audit_value={},
        **extra,
    )


@pytest.mark.asyncio
async def test_two_weeks_keep_files_results_and_prevent_duplicate_notifications(database, monkeypatch):
    db, session, user, norm = database
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(normatives, "utcnow", lambda: now)
    first = await submit(session, user, norm, file_ids=[11, 11])
    db.flush()
    assert await submit(session, user, norm, file_ids=[99]) is first
    assert len(db.scalars(select(Notification)).all()) == 1
    first.status_code, first.grade_value = "ACCEPTED", "30"
    db.flush()
    assert await submit(session, user, norm, file_ids=[99]) is first
    now = datetime(2026, 10, 11, 17, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="новая неделя"):
        await submit(session, user, norm, expected_period_start=date(2026, 10, 5))
    second = await submit(session, user, norm, file_ids=[22])
    db.flush()
    assert second.id != first.id
    assert first.status_code == "ACCEPTED" and first.grade_value == "30"
    assert second.period_start_date == date(2026, 10, 12)
    assert db.scalars(
        select(NormativeSubmissionFile.file_id).where(NormativeSubmissionFile.submission_id == first.id)
    ).all() == [11]
    assert db.scalars(
        select(NormativeSubmissionFile.file_id).where(NormativeSubmissionFile.submission_id == second.id)
    ).all() == [22]
    assert len(db.scalars(select(Notification)).all()) == 2


@pytest.mark.asyncio
async def test_redo_clears_previous_review_but_once_stays_accepted(database, monkeypatch):
    db, session, user, norm = database
    monkeypatch.setattr(normatives, "utcnow", lambda: datetime(2026, 10, 10, 12, tzinfo=timezone.utc))
    first = await submit(session, user, norm)
    first.status_code, first.reviewer_comment, first.grade_value, first.reviewed_by_id = (
        "NEEDS_REDO",
        "Исправить",
        "0",
        2,
    )
    db.flush()
    assert await submit(session, user, norm) is first
    assert (first.reviewer_comment, first.grade_value, first.reviewed_by_id) == (None, None, None)
    norm.recurrence_days = None
    once = await submit(session, user, norm)
    once.status_code = "ACCEPTED"
    db.flush()
    monkeypatch.setattr(normatives, "utcnow", lambda: datetime(2027, 1, 1, tzinfo=timezone.utc))
    assert await submit(session, user, norm) is once


@pytest.mark.asyncio
async def test_enabling_weekly_keeps_existing_results_in_original_weeks(database, monkeypatch):
    from app.routers import normatives as routes

    db, session, user, norm = database
    norm.recurrence_days = None
    norm.recurrence_start_date = None
    now = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(normative_cycles, "utcnow", lambda: now)
    monkeypatch.setattr(routes, "record_audit", AsyncMock())
    older = NormativeSubmission(normative_id=1, user_id=1, status_code="ACCEPTED", submitted_at=now - timedelta(days=8))
    current = NormativeSubmission(normative_id=1, user_id=2, status_code="ACCEPTED", submitted_at=now)
    db.add_all([older, current])
    db.flush()
    session.commit = AsyncMock(side_effect=db.commit)
    session.refresh = AsyncMock(side_effect=db.refresh)
    await routes.update_normative(1, NormativeUpdate(recurrence_days=7), SimpleNamespace(user_id=2), session)
    assert norm.recurrence_start_date == date(2026, 10, 12)
    assert older.period_start_date == date(2026, 10, 5)
    assert current.period_start_date == date(2026, 10, 12)
    assert older.status_code == current.status_code == "ACCEPTED"
