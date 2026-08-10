import config
import db
import nutrition


def _use_tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()


_PARSED = {"foods": [{"name": "김치찌개", "quantity": "1인분", "kcal": 450}], "total_kcal": 450, "comment": ""}


def test_refine_noop_without_api_key(monkeypatch):
    monkeypatch.setattr(config, "NUTRITION_API_KEY", "")
    assert nutrition.refine(dict(_PARSED)) == _PARSED


def test_refine_noop_when_lookup_empty(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "NUTRITION_API_KEY", "dummy")
    monkeypatch.setattr(nutrition, "lookup", lambda name: [])
    assert nutrition.refine(dict(_PARSED)) == _PARSED


def test_refine_falls_back_on_llm_error(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "NUTRITION_API_KEY", "dummy")
    monkeypatch.setattr(nutrition, "lookup", lambda name: [{"FOOD_NM_KR": "김치찌개", "AMT_NUM1": "45"}])

    import llm

    def boom(parsed, refs):
        raise RuntimeError("api down")

    monkeypatch.setattr(llm, "refine_meal", boom)
    assert nutrition.refine(dict(_PARSED)) == _PARSED


def test_refine_applies_llm_result(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "NUTRITION_API_KEY", "dummy")
    monkeypatch.setattr(nutrition, "lookup", lambda name: [{"FOOD_NM_KR": "김치찌개", "AMT_NUM1": "45"}])

    import llm

    refined = {"foods": [{"name": "김치찌개", "quantity": "1인분", "kcal": 400}], "total_kcal": 400, "comment": "보정됨"}
    monkeypatch.setattr(llm, "refine_meal", lambda parsed, refs: refined)
    assert nutrition.refine(dict(_PARSED)) == refined


def test_lookup_uses_cache(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    db.cache_nutrition("김치찌개", [{"FOOD_NM_KR": "김치찌개", "AMT_NUM1": "45"}])

    calls = []
    monkeypatch.setattr(nutrition.urllib.request, "urlopen", lambda *a, **k: calls.append(1))

    items = nutrition.lookup("김치찌개")
    assert items == [{"FOOD_NM_KR": "김치찌개", "AMT_NUM1": "45"}]
    assert not calls  # 캐시 히트 시 네트워크 호출 없음
