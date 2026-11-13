import os
import sqlite3
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("LATE_DB_PATH", os.path.join(BASE_DIR, "late_students.db"))


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS persons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('student', 'teacher', 'employee')),
                course INTEGER,
                group_name TEXT
            );

            CREATE TABLE IF NOT EXISTS cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                person_id INTEGER NOT NULL UNIQUE,
                FOREIGN KEY (person_id) REFERENCES persons(id)
            );

            CREATE TABLE IF NOT EXISTS passages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER NOT NULL,
                passed_at TEXT NOT NULL,
                FOREIGN KEY (card_id) REFERENCES cards(id)
            );

            CREATE TABLE IF NOT EXISTS late_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL,
                passage_id INTEGER NOT NULL UNIQUE,
                late_date TEXT NOT NULL,
                minutes_late INTEGER NOT NULL,
                UNIQUE (person_id, late_date),
                FOREIGN KEY (person_id) REFERENCES persons(id),
                FOREIGN KEY (passage_id) REFERENCES passages(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('lesson_start', '09:00')"
        )


def seed_demo_data():
    people = [
        ("Иванов Иван Иванович", "student", 1, "ИС-26", "1001"),
        ("Петрова Анна Сергеевна", "student", 1, "ИС-26", "1002"),
        ("Соколов Алексей Дмитриевич", "student", 3, "ИС1-24", "1003"),
        ("Козлова Мария Андреевна", "student", 2, "ИС2-25", "1004"),
        ("Вороков Инал Капланович", "teacher", None, None, "2001"),
        ("Магомедов Керим Мурадович", "teacher", None, None, "2002"),
    ]
    with connect() as db:
        for full_name, role, course, group_name, card_code in people:
            existing = db.execute(
                "SELECT id FROM persons WHERE full_name = ?", (full_name,)
            ).fetchone()
            if existing:
                person_id = existing["id"]
                db.execute(
                    """
                    UPDATE persons
                    SET role = ?, course = ?, group_name = ?
                    WHERE id = ?
                    """,
                    (role, course, group_name, person_id),
                )
            else:
                cursor = db.execute(
                    """
                    INSERT INTO persons (full_name, role, course, group_name)
                    VALUES (?, ?, ?, ?)
                    """,
                    (full_name, role, course, group_name),
                )
                person_id = cursor.lastrowid
            db.execute(
                "INSERT OR IGNORE INTO cards (code, person_id) VALUES (?, ?)",
                (card_code, person_id),
            )


def get_setting(key):
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key, value):
    with connect() as db:
        db.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def list_cards():
    with connect() as db:
        return db.execute(
            """
            SELECT c.code, p.full_name, p.role, p.course, p.group_name
            FROM cards c
            JOIN persons p ON p.id = c.person_id
            ORDER BY p.role DESC, p.full_name
            """
        ).fetchall()


def register_passage(card_code, passed_at):
    moment = datetime.fromisoformat(passed_at)
    with connect() as db:
        person = db.execute(
            """
            SELECT p.*, c.id AS card_id
            FROM cards c
            JOIN persons p ON p.id = c.person_id
            WHERE c.code = ?
            """,
            (card_code,),
        ).fetchone()
        if not person:
            raise ValueError("Карта не зарегистрирована")

        cursor = db.execute(
            "INSERT INTO passages (card_id, passed_at) VALUES (?, ?)",
            (person["card_id"], moment.isoformat(timespec="minutes")),
        )
        passage_id = cursor.lastrowid

        start_hour, start_minute = map(int, get_setting("lesson_start").split(":"))
        start = moment.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        eligible = (
            person["role"] == "student"
            and person["course"] in (1, 2)
            and moment > start
        )
        if eligible:
            minutes_late = int((moment - start).total_seconds() // 60)
            db.execute(
                """
                INSERT OR IGNORE INTO late_records
                    (person_id, passage_id, late_date, minutes_late)
                VALUES (?, ?, ?, ?)
                """,
                (person["id"], passage_id, moment.date().isoformat(), minutes_late),
            )
    return person


def recent_passages(limit=20):
    with connect() as db:
        return db.execute(
            """
            SELECT ps.passed_at, p.full_name, p.role, p.course, p.group_name, c.code,
                   lr.id IS NOT NULL AS is_late
            FROM passages ps
            JOIN cards c ON c.id = ps.card_id
            JOIN persons p ON p.id = c.person_id
            LEFT JOIN late_records lr ON lr.passage_id = ps.id
            ORDER BY ps.passed_at DESC, ps.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def list_late_records(date_filter=None):
    query = """
        SELECT lr.late_date, ps.passed_at, p.full_name, p.group_name,
               p.course, lr.minutes_late
        FROM late_records lr
        JOIN persons p ON p.id = lr.person_id
        JOIN passages ps ON ps.id = lr.passage_id
    """
    params = ()
    if date_filter:
        query += " WHERE lr.late_date = ?"
        params = (date_filter,)
    query += " ORDER BY ps.passed_at DESC"
    with connect() as db:
        return db.execute(query, params).fetchall()


def list_first_arrivals(date_filter=None):
    query = """
        SELECT substr(ps.passed_at, 1, 10) AS arrival_date,
               MIN(ps.passed_at) AS passed_at,
               p.full_name, p.role, p.course, p.group_name
        FROM passages ps
        JOIN cards c ON c.id = ps.card_id
        JOIN persons p ON p.id = c.person_id
        WHERE 1 = 1
    """
    params = ()
    if date_filter:
        query += " AND substr(ps.passed_at, 1, 10) = ?"
        params = (date_filter,)
    query += """
        GROUP BY p.id, substr(ps.passed_at, 1, 10)
        ORDER BY passed_at DESC
    """
    with connect() as db:
        return db.execute(query, params).fetchall()


def clear_events():
    with connect() as db:
        db.execute("DELETE FROM late_records")
        db.execute("DELETE FROM passages")
