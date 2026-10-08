import unittest
from datetime import date

from app.schemas.core import JoinApplicationCreate
from app.services.join_input import join_text, normalize_join_phone, parse_join_birth_date, validate_join_birth_date


class JoinInputTests(unittest.TestCase):
    def test_russian_phone_formats_are_normalized(self):
        for value in ("89991234567", "+7 (999) 123-45-67", "9991234567"):
            self.assertEqual(normalize_join_phone(value), "+79991234567")

    def test_invalid_phone_is_rejected(self):
        for value in ("/start", "номер", "123", "+0123456789", "+7 123abc", "1" * 16):
            with self.assertRaises(ValueError):
                normalize_join_phone(value)

    def test_optional_phone_can_be_skipped(self):
        for value in (None, "", "нет", " Пропустить ", "-"):
            self.assertIsNone(normalize_join_phone(value))

    def test_birth_date_accepts_both_formats(self):
        self.assertEqual(parse_join_birth_date("11.04.2006"), date(2006, 4, 11))
        self.assertEqual(parse_join_birth_date("2006-04-11"), date(2006, 4, 11))

    def test_future_and_invalid_birth_dates_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_join_birth_date(date(2026, 10, 9), today=date(2026, 10, 8))
        for value in ("31.02.2010", "2999-01-01", "/start"):
            with self.assertRaises(ValueError):
                parse_join_birth_date(value)

    def test_commands_and_oversized_input_cannot_be_saved_as_application_fields(self):
        for value in ("/start", "я" * 256, " "):
            with self.assertRaises(ValueError):
                join_text(value, label="Поле")

    def test_optional_source_can_be_skipped(self):
        self.assertIsNone(join_text("Пропустить", label="Источник", optional=True))
        self.assertEqual(join_text("  От друга  ", label="Источник", optional=True), "От друга")

    def test_api_and_bot_share_phone_normalization(self):
        payload = JoinApplicationCreate(full_name="  Иванов   Иван  ", consent_given=True, phone="89991234567")
        self.assertEqual(payload.full_name, "Иванов Иван")
        self.assertEqual(payload.phone, "+79991234567")

    def test_international_phone_and_leap_birth_date_are_preserved(self):
        self.assertEqual(normalize_join_phone("+44 20 7946 0958"), "+442079460958")
        self.assertEqual(parse_join_birth_date("29.02.2012"), date(2012, 2, 29))

    def test_api_rejects_blank_name_future_date_and_oversized_fields(self):
        for extra in ({"full_name": "   "}, {"birth_date": date(2999, 1, 1)}, {"phone": "не телефон"},
                      {"motivation_text": "я" * 1501}, {"source_text": "я" * 301}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                JoinApplicationCreate(**{"full_name": "Иван Иванов", "consent_given": True, **extra})


if __name__ == "__main__":
    unittest.main()
