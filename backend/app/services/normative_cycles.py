from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ..config import get_settings
from ..models import NormativeSubmission
from ..utils.audit import utcnow


@dataclass(frozen=True)
class NormativePeriod:
    start: date | None
    end: date | None
    opens_at: datetime | None
    closes_at: datetime | None


def monday_in_club(now: datetime | None = None) -> date:
    value = now or utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    day = value.astimezone(ZoneInfo(get_settings().timezone)).date()
    return day - timedelta(days=day.weekday())


def normative_period(normative, now: datetime | None = None) -> NormativePeriod:
    if not getattr(normative, "recurrence_days", None):
        return NormativePeriod(None, None, None, None)
    now = now or utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    zone = ZoneInfo(get_settings().timezone)
    day = now.astimezone(zone).date()
    anchor = normative.recurrence_start_date or monday_in_club(normative.created_at or now)
    start = anchor + timedelta(
        days=max(0, (day - anchor).days // normative.recurrence_days) * normative.recurrence_days
    )
    end = start + timedelta(days=normative.recurrence_days)
    return NormativePeriod(
        start,
        end,
        datetime.combine(start, time.min, zone).astimezone(timezone.utc),
        datetime.combine(end, time.min, zone).astimezone(timezone.utc),
    )


def period_submission_clause(normative, now: datetime | None = None):
    start = normative_period(normative, now).start
    return NormativeSubmission.period_start_date == start if start else NormativeSubmission.period_start_date.is_(None)


def is_current_submission(normative, submission, now: datetime | None = None) -> bool:
    return getattr(submission, "period_start_date", None) == normative_period(normative, now).start


def attach_period(normative, now: datetime | None = None):
    now = now or utcnow()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    period = normative_period(normative, now)
    normative.current_period_start_date = period.start
    normative.current_period_end_date = period.end
    normative.next_reset_at = period.closes_at
    normative.is_submission_open = normative.is_active and (period.opens_at is None or now >= period.opens_at)
    return normative
