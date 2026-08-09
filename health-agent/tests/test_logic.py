import config
import db
import llm
import logic


def _use_tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


def test_record_meal_saves_and_replies(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(
        llm,
        "parse_meal",
        lambda text: {
            "foods": [
                {"name": "김치찌개", "quantity": "1인분", "kcal": 450},
                {"name": "밥", "quantity": "한 공기", "kcal": 300},
            ],
            "total_kcal": 750,
            "comment": "단백질이 조금 부족해요.",
        },
    )

    reply, is_dinner = logic.record_meal("김치찌개랑 밥 한 공기", slot="lunch")

    assert "점심 식사 기록 완료" in reply
    assert "김치찌개" in reply and "450" in reply
    assert "750" in reply
    assert "단백질" in reply
    assert is_dinner is False

    from meal_slots import today_kst

    saved = db.meals_on(today_kst())
    assert len(saved) == 1
    assert saved[0]["total_kcal"] == 750


def test_record_meal_dinner_flag_and_day_total(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(
        llm,
        "parse_meal",
        lambda text: {"foods": [{"name": "샐러드", "quantity": "1그릇", "kcal": 200}], "total_kcal": 200, "comment": ""},
    )

    logic.record_meal("샐러드", slot="lunch")
    reply, is_dinner = logic.record_meal("샐러드", slot="dinner")

    assert is_dinner is True
    assert "누적 400" in reply


def test_build_daily_summary_empty(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    assert "기록된 식사가 아직 없어요" in logic.build_daily_summary()


def test_build_daily_summary_calls_llm(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    db.save_meal("2026-08-10", "lunch", "비빔밥", [{"name": "비빔밥", "quantity": "1그릇", "kcal": 550}], 550)
    monkeypatch.setattr(llm, "daily_summary", lambda date, meals: f"{date}: {len(meals)}끼 요약")

    assert logic.build_daily_summary("2026-08-10") == "2026-08-10: 1끼 요약"


def test_build_recommendation_no_history(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    # llm.recommend는 빈 기록이면 API 호출 없이 안내 문구를 돌려준다
    assert "기록이 없어요" in logic.build_recommendation()
