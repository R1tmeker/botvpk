from __future__ import annotations

import unittest

from app.roles import RoleLevel
from app.schemas.core import AppealCreate, AppealMessageCreate, AppealUpdate
from app.services.appeal_policy import can_access_appeal, reply_recipient_ids, validate_appeal_text
from app.services.bot_callbacks import callback_ids


class AppealPolicyTests(unittest.TestCase):
    def test_bot_callback_prefix_and_ids_match_real_buttons(self):
        self.assertEqual(callback_ids("appealreply:12", "appealreply", 1), [12])
        self.assertEqual(callback_ids("appealthread:12", "appealthread", 1), [12])
        self.assertEqual(callback_ids("reason:12:3", "reason", 2), [12, 3])

    def test_bot_callback_rejects_malformed_and_database_overflow_ids(self):
        for value in (None, "appealreply:0", "appealreply:-1", "appealreply:1.5", "appealreply:2147483648", "appealreply:1:2", "other:1", "appealreply:+1"):
            self.assertIsNone(callback_ids(value, "appealreply", 1))

    def test_participant_reads_only_own_appeals(self):
        self.assertTrue(can_access_appeal(author_id=1, user_id=1, role=RoleLevel.PARTICIPANT))
        self.assertFalse(can_access_appeal(author_id=1, user_id=2, role=RoleLevel.PARTICIPANT))

    def test_squad_commander_has_no_access_to_other_appeals(self):
        self.assertFalse(can_access_appeal(author_id=1, user_id=2, role=RoleLevel.SQUAD_COMMANDER))

    def test_pending_and_missing_profile_do_not_inherit_ownership(self):
        self.assertFalse(can_access_appeal(author_id=1, user_id=1, role=RoleLevel.CANDIDATE))
        self.assertFalse(can_access_appeal(author_id=None, user_id=None, role=RoleLevel.PARTICIPANT))

    def test_platoon_command_and_admin_can_reply(self):
        for role in (RoleLevel.DEPUTY_PLATOON_COMMANDER, RoleLevel.ADMIN, RoleLevel.SUPER_ADMIN):
            self.assertTrue(can_access_appeal(author_id=1, user_id=2, role=role))

    def test_blank_message_is_rejected_by_bot_and_api(self):
        for value in ("", " \n\t "):
            with self.assertRaises(ValueError):
                validate_appeal_text(value)
            with self.assertRaises(ValueError):
                AppealMessageCreate(body=value)

    def test_body_is_trimmed_and_maximum_is_shared(self):
        self.assertEqual(validate_appeal_text("  Ответ\n "), "Ответ")
        self.assertEqual(AppealMessageCreate(body="  Ответ\n ").body, "Ответ")
        self.assertEqual(len(validate_appeal_text("я" * 4000)), 4000)
        for validate in (validate_appeal_text, lambda text: AppealMessageCreate(body=text)):
            with self.assertRaises(ValueError):
                validate("я" * 4001)

    def test_author_response_notifies_assignee_without_self_notification(self):
        self.assertEqual(reply_recipient_ids(author_id=1, sender_id=1, commander_ids=[1, 2, 3], assignee_id=2), [2])

    def test_commander_author_response_notifies_other_commanders(self):
        self.assertEqual(reply_recipient_ids(author_id=1, sender_id=1, commander_ids=[1, 2, 2, 3], assignee_id=None), [2, 3])

    def test_inactive_assignee_falls_back_to_current_commanders(self):
        self.assertEqual(reply_recipient_ids(author_id=1, sender_id=1, commander_ids=[2, 3], assignee_id=9), [2, 3])

    def test_author_assigned_to_own_appeal_notifies_other_commanders(self):
        self.assertEqual(reply_recipient_ids(author_id=1, sender_id=1, commander_ids=[1, 2, 3], assignee_id=1), [2, 3])

    def test_reply_notifies_author_instead_of_every_commander(self):
        self.assertEqual(reply_recipient_ids(author_id=1, sender_id=2, commander_ids=[2, 3], assignee_id=3), [1])

    def test_deleted_author_gets_no_notification(self):
        self.assertEqual(reply_recipient_ids(author_id=None, sender_id=2, commander_ids=[2], assignee_id=2), [])

    def test_creation_trims_and_rejects_empty_and_oversize_text(self):
        self.assertEqual(AppealCreate(subject="  Тема  ", description="  Текст  ").subject, "Тема")
        for values in ({"subject": "  ", "description": "Описание"}, {"subject": "Тема", "description": "  "},
                       {"subject": "Тема", "description": "я" * 10001}):
            with self.assertRaises(ValueError):
                AppealCreate(**values)

    def test_unknown_and_null_status_are_rejected(self):
        for status in ("FORGED", None):
            with self.assertRaises(ValueError):
                AppealUpdate(status_code=status)
        self.assertEqual(AppealUpdate(status_code="NEEDS_INFO").status_code, "NEEDS_INFO")

    def test_clearing_assignee_does_not_require_status_change(self):
        self.assertEqual(AppealUpdate(assignee_user_id=None).model_dump(exclude_unset=True), {"assignee_user_id": None})


if __name__ == "__main__":
    unittest.main()
