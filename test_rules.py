import os
import tempfile
import unittest


TEMP_DB = os.path.join(tempfile.gettempdir(), "late_students_test.db")
os.environ["LATE_DB_PATH"] = TEMP_DB

import database
from app import app, format_delay


class LateRulesTest(unittest.TestCase):
    def setUp(self):
        if os.path.exists(TEMP_DB):
            os.remove(TEMP_DB)
        database.init_db()
        database.seed_demo_data()

    def tearDown(self):
        if os.path.exists(TEMP_DB):
            os.remove(TEMP_DB)

    def test_student_before_start_is_not_late(self):
        database.register_passage("1001", "2026-11-11T08:55")
        self.assertEqual(len(database.list_late_records()), 0)

    def test_student_after_start_is_late(self):
        database.register_passage("1002", "2026-11-11T09:11")
        records = database.list_late_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["minutes_late"], 11)

    def test_teachers_are_ignored(self):
        database.register_passage("2001", "2026-11-11T09:12")
        database.register_passage("2002", "2026-11-11T09:13")
        self.assertEqual(len(database.list_late_records()), 0)

    def test_second_passage_does_not_duplicate_record(self):
        database.register_passage("1001", "2026-11-11T09:05")
        database.register_passage("1001", "2026-11-11T09:20")
        self.assertEqual(len(database.list_late_records()), 1)

    def test_requested_groups_courses_and_teachers_are_seeded(self):
        cards = database.list_cards()
        self.assertEqual(len(cards), 6)
        students = [card for card in cards if card["role"] == "student"]
        teachers = [card for card in cards if card["role"] == "teacher"]
        groups_and_courses = {
            (card["group_name"], card["course"]) for card in students
        }
        self.assertEqual(
            groups_and_courses,
            {("ИС-26", 1), ("ИС1-24", 3), ("ИС2-25", 2)},
        )
        self.assertEqual(
            {card["full_name"] for card in teachers},
            {"Вороков Инал Капланович", "Магомедов Керим Мурадович"},
        )

    def test_delay_is_formatted_as_days_hours_and_minutes(self):
        self.assertEqual(format_delay(1586), "+1 д. 2 ч. 26 мин.")
        self.assertEqual(format_delay(886), "+14 ч. 46 мин.")

    def test_csv_contains_all_students_and_teachers(self):
        database.register_passage("1001", "2026-11-11T08:55")
        database.register_passage("1002", "2026-11-11T09:11")
        database.register_passage("1003", "2026-11-11T09:20")
        database.register_passage("2001", "2026-11-11T09:15")
        response = app.test_client().get("/export.csv?date=2026-11-11")
        text = response.data.decode("utf-8-sig")
        self.assertIn("Время прохода", text)
        self.assertIn(
            "08:55;Иванов Иван Иванович;Студент;ИС-26;1;Вовремя;—", text
        )
        self.assertIn(
            "09:11;Петрова Анна Сергеевна;Студент;ИС-26;1;Опоздал;+11 мин.",
            text,
        )
        self.assertIn(
            "09:20;Соколов Алексей Дмитриевич;Студент;ИС1-24;3;Прошёл;—",
            text,
        )
        self.assertIn(
            "09:15;Вороков Инал Капланович;Преподаватель;—;—;Прошёл;—", text
        )


if __name__ == "__main__":
    unittest.main()
