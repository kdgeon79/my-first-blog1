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
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nutrition_cache (
    food_name TEXT PRIMARY KEY,
    result_json TEXT NOT NULL,        -- 식약처 조회 결과(항목 리스트), 빈 리스트면 미발견
    fetched_at TEXT NOT NULL
);
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


def last_meal() -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM meals ORDER BY id DESC LIMIT 1").fetchone()
    return _row_to_dict(row) if row else None


def delete_meal(meal_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))


def has_meal(meal_date: str, slot: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM meals WHERE meal_date = ? AND slot = ? LIMIT 1", (meal_date, slot)
        ).fetchone()
    return row is not None


def any_meal_since(since_iso: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM meals WHERE created_at >= ? LIMIT 1", (since_iso,)
        ).fetchone()
    return row is not None


def get_setting(key: str, default: str | None = None) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_cached_nutrition(food_name: str) -> list | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT result_json FROM nutrition_cache WHERE food_name = ?", (food_name,)
        ).fetchone()
    return json.loads(row["result_json"]) if row else None


def cache_nutrition(food_name: str, items: list) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO nutrition_cache (food_name, result_json, fetched_at) VALUES (?, ?, ?) "
            "ON CONFLICT(food_name) DO UPDATE SET result_json = excluded.result_json, "
            "fetched_at = excluded.fetched_at",
            (food_name, json.dumps(items, ensure_ascii=False), now_kst().isoformat(timespec="seconds")),
        )
