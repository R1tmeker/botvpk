from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.roles import RoleLevel
from app.schemas.core import BulkEventResponseCreate, EventResponseCreate
from app.services.audiences import visible_audiences
from app.services.event_response_policy import EventResponseError, validate_event_available, validate_response_details

NOW = datetime(2026, 10, 8, 10, tzinfo=timezone.utc)


def event(**overrides):
    values = dict(squad_id=1, status_code="PLANNED", requires_response=True,
                  start_datetime=NOW + timedelta(hours=3), response_deadline_at=NOW + timedelta(hours=1))
    values.update(overrides)
    return SimpleNamespace(**values)


class ResponsePolicyTests(unittest.TestCase):
    def validate(self, item=None, role=RoleLevel.PARTICIPANT, squad_id=1):
        validate_event_available(item or event(), role=role, squad_id=squad_id, now=NOW)

    def test_own_squad_and_common_event_are_allowed(self):
        self.validate()
        self.validate(event(squad_id=None), squad_id=None)

    def test_public_user_cannot_respond(self):
        with self.assertRaises(EventResponseError):
            self.validate(role=RoleLevel.CANDIDATE)

    def test_foreign_squad_is_rejected_for_participant_and_deputy(self):
        for role in (RoleLevel.PARTICIPANT, RoleLevel.DEPUTY_SQUAD_COMMANDER):
            with self.subTest(role=role), self.assertRaises(EventResponseError):
                self.validate(event(squad_id=2), role=role)

    def test_commander_has_existing_cross_squad_permission(self):
        self.validate(event(squad_id=2), role=RoleLevel.SQUAD_COMMANDER)

    def test_expired_deadline_cannot_be_bypassed_by_bulk_or_old_button(self):
        with self.assertRaisesRegex(EventResponseError, "Срок ответа"):
            self.validate(event(response_deadline_at=NOW - timedelta(seconds=1)))

    def test_deadline_boundary_and_commander_override(self):
        self.validate(event(response_deadline_at=NOW))
        self.validate(event(response_deadline_at=NOW - timedelta(minutes=1)), role=RoleLevel.DEPUTY_SQUAD_COMMANDER)

    def test_started_cancelled_and_non_response_events_are_rejected(self):
        for item in (event(start_datetime=NOW), event(status_code="CANCELLED"), event(requires_response=False)):
            with self.subTest(item=item), self.assertRaises(EventResponseError):
                self.validate(item, role=RoleLevel.ADMIN)

    def test_unknown_response_and_empty_absence_are_rejected(self):
        for code, comment in (("FORGED", None), ("NOT_COMING", "   ")):
            with self.subTest(code=code), self.assertRaises(EventResponseError):
                validate_response_details(code, requires_response=True, custom_reason=comment)

    def test_reason_must_be_active_and_required_comment_must_be_present(self):
        for reason in (None, SimpleNamespace(is_active=False, requires_comment=False), SimpleNamespace(is_active=True, requires_comment=True)):
            with self.subTest(reason=reason), self.assertRaises(EventResponseError):
                validate_response_details("NOT_COMING", requires_response=True, absence_reason_id=4, reason=reason)

    def test_reason_comment_is_trimmed_and_preserves_selected_reason(self):
        result = validate_response_details("NOT_COMING", requires_response=True, absence_reason_id=4,
                                          reason=SimpleNamespace(is_active=True, requires_comment=True), custom_reason="  Болен  ")
        self.assertEqual(result, ("NOT_COMING", 4, "Болен"))

    def test_changing_to_coming_clears_previous_absence(self):
        self.assertEqual(validate_response_details("COMING", requires_response=True, absence_reason_id=4, custom_reason="Болен"), ("COMING", None, None))

    def test_comment_limit_matches_database_column(self):
        with self.assertRaises(EventResponseError):
            validate_response_details("NOT_COMING", requires_response=True, custom_reason="я" * 501)
        self.assertEqual(len(validate_response_details("NOT_COMING", requires_response=True, custom_reason="я" * 500)[2]), 500)

    def test_bulk_ids_are_unique_positive_and_bounded(self):
        for ids in ([], [1, 1], [0], [-1], list(range(1, 52))):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                BulkEventResponseCreate(event_ids=ids)
        self.assertEqual(BulkEventResponseCreate(event_ids=[2, 1]).event_ids, [2, 1])

    def test_api_schema_rejects_unknown_response_and_unreasoned_bulk_absence(self):
        with self.assertRaises(ValueError):
            EventResponseCreate(response_code="FORGED")
        with self.assertRaises(ValueError):
            BulkEventResponseCreate(event_ids=[1], response_code="NOT_COMING")

    def test_material_search_does_not_expose_commander_audience(self):
        self.assertNotIn("COMMANDERS", visible_audiences("PARTICIPANT", RoleLevel.PARTICIPANT))
        self.assertNotIn("PARTICIPANTS", visible_audiences("CANDIDATE", RoleLevel.CANDIDATE))
        self.assertIn("COMMANDERS", visible_audiences("SQUAD_COMMANDER", RoleLevel.SQUAD_COMMANDER))


if __name__ == "__main__":
    unittest.main()
