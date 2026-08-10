"""식약처 식품영양성분 DB(공공데이터포털) 연동.

API 키(NUTRITION_API_KEY)가 없거나 조회에 실패하면 조용히 LLM 추정값을 그대로 쓴다.
조회 결과는 nutrition_cache 테이블에 캐시된다.
"""
import json
import logging
import urllib.parse
import urllib.request

import config
import db

logger = logging.getLogger("health-agent.nutrition")

# 응답 항목에서 LLM 보정에 참고할 만한 필드만 추린다 (스키마 변형에 대비해 느슨하게).
_KEEP_KEYS = {
    "FOOD_NM_KR",       # 식품명
    "AMT_NUM1",         # 에너지(kcal) / 100g
    "AMT_NUM3",         # 단백질(g)
    "AMT_NUM4",         # 지방(g)
    "AMT_NUM6",         # 탄수화물(g)
    "SERVING_SIZE",     # 1회 제공량
    "Z10500",           # 1회 섭취참고량 (일부 스키마)
    "FOOD_CAT1_NM",     # 분류
}


def _trim(item: dict) -> dict:
    kept = {k: v for k, v in item.items() if k in _KEEP_KEYS and v not in (None, "")}
    return kept or {k: v for i, (k, v) in enumerate(item.items()) if i < 8}


def lookup(food_name: str) -> list[dict]:
    """음식명으로 공식 영양성분 후보를 조회한다 (최대 3건). 실패 시 빈 리스트."""
    cached = db.get_cached_nutrition(food_name)
    if cached is not None:
        return cached

    params = urllib.parse.urlencode(
        {
            "serviceKey": config.NUTRITION_API_KEY,
            "type": "json",
            "pageNo": "1",
            "numOfRows": "3",
            "FOOD_NM_KR": food_name,
        }
    )
    try:
        req = urllib.request.Request(f"{config.NUTRITION_API_URL}?{params}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("body", {}).get("items") or []
        if isinstance(items, dict):  # 단건이면 dict로 오는 스키마 대비
            items = [items]
        items = [_trim(i) for i in items if isinstance(i, dict)]
    except Exception:
        logger.warning("식약처 API 조회 실패: %s", food_name, exc_info=True)
        return []  # 실패는 캐시하지 않음 — 다음에 재시도

    db.cache_nutrition(food_name, items)
    return items


def refine(parsed: dict) -> dict:
    """LLM 파싱 결과를 식약처 DB 수치로 보정한다. 키가 없거나 실패하면 원본 반환."""
    if not config.NUTRITION_API_KEY:
        return parsed
    refs = []
    for food in parsed.get("foods", [])[:8]:
        items = lookup(food["name"])
        if items:
            refs.append({"query": food["name"], "db_items": items})
    if not refs:
        return parsed
    try:
        import llm  # 순환 임포트 방지를 위해 지연 임포트

        return llm.refine_meal(parsed, refs)
    except Exception:
        logger.warning("영양 DB 보정 실패 — LLM 추정값 사용", exc_info=True)
        return parsed
