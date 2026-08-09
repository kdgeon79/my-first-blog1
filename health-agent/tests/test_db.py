import config
import db


def _use_tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def test_save_and_query(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)

    foods = [{"name": "김치찌개", "quantity": "1인분", "kcal": 450}]
    meal_id = db.save_meal("2026-08-10", "lunch", "김치찌개", foods, 450)
    assert meal_id == 1

    meals = db.meals_on("2026-08-10")
    assert len(meals) == 1
    assert meals[0]["slot"] == "lunch"
    assert meals[0]["foods"] == foods
    assert meals[0]["total_kcal"] == 450

    assert db.meals_on("2026-08-09") == []


def test_recent_meals(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)

    from meal_slots import today_kst

    db.save_meal(today_kst(), "breakfast", "토스트", [{"name": "토스트", "quantity": "2쪽", "kcal": 300}], 300)
    db.save_meal("2000-01-01", "dinner", "옛날 기록", [{"name": "밥", "quantity": "1공기", "kcal": 300}], 300)

    recent = db.recent_meals(days=7)
    assert len(recent) == 1
    assert recent[0]["raw_text"] == "토스트"
