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

    from meal_slots import logical_date_kst

    db.save_meal(logical_date_kst(), "breakfast", "토스트", [{"name": "토스트", "quantity": "2쪽", "kcal": 300}], 300)
    db.save_meal("2000-01-01", "dinner", "옛날 기록", [{"name": "밥", "quantity": "1공기", "kcal": 300}], 300)

    recent = db.recent_meals(days=7)
    assert len(recent) == 1
    assert recent[0]["raw_text"] == "토스트"


def test_last_meal_and_delete(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)

    assert db.last_meal() is None
    db.save_meal("2026-08-10", "lunch", "비빔밥", [{"name": "비빔밥", "quantity": "1그릇", "kcal": 550}], 550)
    db.save_meal("2026-08-10", "dinner", "라면", [{"name": "라면", "quantity": "1개", "kcal": 500}], 500)

    last = db.last_meal()
    assert last["raw_text"] == "라면"

    db.delete_meal(last["id"])
    assert db.last_meal()["raw_text"] == "비빔밥"


def test_has_meal_and_any_meal_since(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)

    db.save_meal("2026-08-10", "lunch", "비빔밥", [{"name": "비빔밥", "quantity": "1그릇", "kcal": 550}], 550)
    # 슬롯별 존재 여부 — 질문 전에 미리 기록해도 리마인더가 안 가야 한다
    assert db.has_meal("2026-08-10", "lunch")
    assert not db.has_meal("2026-08-10", "dinner")
    # 질문 이후 아무 끼니든 기록되면 리마인더가 안 가야 한다
    assert db.any_meal_since("2000-01-01T00:00:00")
    assert not db.any_meal_since("2999-01-01T00:00:00")


def test_settings(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)

    assert db.get_setting("daily_kcal_goal") is None
    assert db.get_setting("daily_kcal_goal", "0") == "0"
    db.set_setting("daily_kcal_goal", "2000")
    assert db.get_setting("daily_kcal_goal") == "2000"
    db.set_setting("daily_kcal_goal", "1800")
    assert db.get_setting("daily_kcal_goal") == "1800"


def test_nutrition_cache(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)

    assert db.get_cached_nutrition("김치찌개") is None
    db.cache_nutrition("김치찌개", [{"FOOD_NM_KR": "김치찌개", "AMT_NUM1": "45"}])
    assert db.get_cached_nutrition("김치찌개") == [{"FOOD_NM_KR": "김치찌개", "AMT_NUM1": "45"}]
    db.cache_nutrition("없는음식", [])
    assert db.get_cached_nutrition("없는음식") == []
