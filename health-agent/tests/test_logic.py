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

    from meal_slots import logical_date_kst

    saved = db.meals_on(logical_date_kst())
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
    monkeypatch.setattr(llm, "daily_summary", lambda date, meals, goal_kcal=None: f"{date}: {len(meals)}끼 요약")

    assert logic.build_daily_summary("2026-08-10") == "2026-08-10: 1끼 요약"


def test_build_recommendation_no_history(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    # llm.recommend는 빈 기록이면 API 호출 없이 안내 문구를 돌려준다
    assert "기록이 없어요" in logic.build_recommendation()


_PARSED = {"foods": [{"name": "라면", "quantity": "1개", "kcal": 500}], "total_kcal": 500, "comment": ""}


def test_goal_tracking_in_reply(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(llm, "parse_meal", lambda text: dict(_PARSED))

    assert logic.get_goal() is None
    logic.set_goal(2000)
    assert logic.get_goal() == 2000

    reply, _ = logic.record_meal("라면", slot="lunch")
    assert "목표 2,000 kcal까지 1500 kcal 남았어요" in reply

    for _ in range(3):
        logic.record_meal("라면", slot="dinner")
    reply, _ = logic.record_meal("라면", slot="dinner")
    assert "초과했어요" in reply


def test_delete_last_meal(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    assert "삭제할 식사 기록이 없어요" in logic.delete_last_meal()

    monkeypatch.setattr(llm, "parse_meal", lambda text: dict(_PARSED))
    logic.record_meal("라면", slot="lunch")

    reply = logic.delete_last_meal()
    assert "삭제했어요" in reply and "라면" in reply
    assert db.last_meal() is None


def test_correct_last_meal_keeps_slot_and_date(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    assert "수정할 식사 기록이 없어요" in logic.correct_last_meal("밥")[0]

    monkeypatch.setattr(llm, "parse_meal", lambda text: dict(_PARSED))
    logic.record_meal("라면", slot="breakfast")

    corrected = {"foods": [{"name": "김밥", "quantity": "1줄", "kcal": 350}], "total_kcal": 350, "comment": ""}
    monkeypatch.setattr(llm, "parse_meal", lambda text: dict(corrected))
    reply, _ = logic.correct_last_meal("김밥 한 줄")

    assert "수정했어요" in reply and "김밥" in reply
    last = db.last_meal()
    assert last["slot"] == "breakfast"
    assert last["total_kcal"] == 350
    from meal_slots import logical_date_kst

    assert len(db.meals_on(logical_date_kst())) == 1


def test_weekly_stats_and_report(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    assert "기록이 없어요" in logic.build_weekly_report()

    from meal_slots import logical_date_kst

    today = logical_date_kst()
    db.save_meal(today, "lunch", "비빔밥", [{"name": "비빔밥", "quantity": "1그릇", "kcal": 600}], 600)
    db.save_meal(today, "dinner", "라면", [{"name": "라면", "quantity": "1개", "kcal": 400}], 400)

    stats = logic.weekly_stats(db.recent_meals(7))
    assert f"- {today}: 1000 kcal" in stats
    assert "기록한 날: 1일" in stats
    assert "평균 약 1000 kcal" in stats

    monkeypatch.setattr(llm, "weekly_report", lambda stats_text, meals, goal_kcal=None: "리포트")
    assert logic.build_weekly_report() == "리포트"


def test_record_meal_from_image(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(llm, "parse_meal_image", lambda b64, mt, caption="": dict(_PARSED))

    reply, is_dinner = logic.record_meal_from_image("aGk=", "image/png", "점심입니다", slot="lunch")
    assert "라면" in reply
    assert is_dinner is False
    assert db.last_meal()["raw_text"] == "[사진] 점심입니다"


def test_correct_last_meal_preserves_record_on_parse_failure(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(llm, "parse_meal", lambda text: dict(_PARSED))
    logic.record_meal("라면", slot="lunch")

    def boom(text):
        raise RuntimeError("api down")

    monkeypatch.setattr(llm, "parse_meal", boom)
    import pytest

    with pytest.raises(RuntimeError):
        logic.correct_last_meal("김밥")
    # 파싱 실패 시 원본 기록은 그대로 남아야 한다
    assert db.last_meal()["raw_text"] == "라면"
