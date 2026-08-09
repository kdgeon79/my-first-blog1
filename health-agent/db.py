"""SQLite 식사 기록 저장소."""
import json
import sqlite3
from datetime import timedelta

import config
from meal_slots import now_kst

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_date TEXT NOT NULL,          -- YYYY-MM-DD (KST)
    slot TEXT NOT NULL,               -- breakfast | lunch | dinner
    raw_text TEXT NOT NULL,           -- 사용자가 입력한 원문
    foods_json TEXT NOT NULL,         -- [{name, quantity, kcal}, ...]
    total_kcal REAL NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meals_date ON meals (meal_date);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def save_meal(meal_date: str, slot: str, raw_text: str, foods: list[dict], total_kcal: float) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO meals (meal_date, slot, raw_text, foods_json, total_kcal, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                meal_date,
                slot,
                raw_text,
                json.dumps(foods, ensure_ascii=False),
                total_kcal,
                now_kst().isoformat(timespec="seconds"),
            ),
        )
        return cur.lastrowid


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["foods"] = json.loads(d.pop("foods_json"))
    return d


def meals_on(meal_date: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM meals WHERE meal_date = ? ORDER BY created_at", (meal_date,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def recent_meals(days: int = 7) -> list[dict]:
    since = (now_kst().date() - timedelta(days=days - 1)).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM meals WHERE meal_date >= ? ORDER BY meal_date, created_at", (since,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]
