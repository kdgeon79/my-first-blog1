"""Claude API 호출 래퍼: 식사 파싱, 하루 요약, 음식 추천."""
import json

import anthropic

import config

client = anthropic.Anthropic()


class LLMRefusalError(RuntimeError):
    """안전 분류기가 요청을 거절해 폴백까지 모두 실패한 경우."""


class LLMTruncatedError(RuntimeError):
    """응답이 max_tokens 한도에서 잘린 경우."""


# 파싱 결과 스키마 — structured outputs 로 항상 유효한 JSON을 보장한다.
MEAL_SCHEMA = {
    "type": "object",
    "properties": {
        "foods": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "음식 이름"},
                    "quantity": {"type": "string", "description": "분량 (예: 1인분, 한 공기)"},
                    "kcal": {"type": "number", "description": "추정 칼로리"},
                },
                "required": ["name", "quantity", "kcal"],
                "additionalProperties": False,
            },
        },
        "total_kcal": {"type": "number"},
        "comment": {"type": "string", "description": "한 줄 영양 코멘트"},
    },
    "required": ["foods", "total_kcal", "comment"],
    "additionalProperties": False,
}

_PARSE_SYSTEM = (
    "당신은 한국 음식에 밝은 영양사입니다. 사용자가 자유 텍스트로 적은 식사 기록에서 "
    "음식명과 분량을 파악하고 각 음식의 칼로리를 추정하세요. 분량이 명시되지 않으면 "
    "일반적인 1인분 기준으로 추정합니다. 칼로리는 대략적인 추정치(±20~30%)면 충분합니다. "
    "comment에는 이 식사에 대한 짧은 영양 코멘트를 한 문장으로 적으세요."
)

_SUMMARY_SYSTEM = (
    "당신은 친근한 건강 관리 코치입니다. 사용자의 하루 식사 기록을 보고 "
    "총 칼로리와 영양 밸런스(탄수화물/단백질/지방, 채소 섭취 등)를 짧게 평가하세요. "
    "따뜻하고 격려하는 톤으로, 5문장 이내로 답합니다. Slack 메시지로 보내기 좋게 "
    "마크다운 헤더 없이 짧은 문단과 이모지 정도만 사용하세요."
)

_PARSE_IMAGE_SYSTEM = (
    "당신은 한국 음식에 밝은 영양사입니다. 사용자가 보낸 식사 사진에서 보이는 음식과 "
    "대략적인 분량을 파악하고 각 음식의 칼로리를 추정하세요. 사진과 함께 온 텍스트가 있으면 "
    "참고하세요. 칼로리는 대략적인 추정치(±20~30%)면 충분합니다. "
    "comment에는 이 식사에 대한 짧은 영양 코멘트를 한 문장으로 적으세요."
)

_REFINE_SYSTEM = (
    "당신은 영양 데이터 전문가입니다. LLM이 추정한 식사 파싱 결과와, 식약처 식품영양성분 DB에서 "
    "조회한 공식 수치가 주어집니다. DB 항목이 해당 음식과 실제로 일치하는 경우에만 그 수치"
    "(보통 100g당 에너지)를 분량에 맞게 환산해 kcal를 보정하세요. 일치하는 항목이 없으면 "
    "기존 추정치를 유지합니다. 음식 목록 자체(이름·분량)는 바꾸지 말고 kcal와 total_kcal, "
    "comment만 조정하세요."
)

_WEEKLY_SYSTEM = (
    "당신은 친근한 건강 관리 코치입니다. 사용자의 최근 7일 식사 통계와 기록을 보고 "
    "주간 리포트를 작성하세요: ① 한 주 식사 패턴 요약 ② 잘한 점 1가지 ③ 개선하면 좋을 점 1~2가지 "
    "④ 다음 주 실천 제안 1가지. 따뜻하고 격려하는 톤으로 8문장 이내, "
    "마크다운 헤더 없이 짧은 문단과 이모지 정도만 사용하세요."
)

_RECOMMEND_SYSTEM = (
    "당신은 친근한 건강 관리 코치입니다. 사용자의 최근 식사 기록을 보고 "
    "부족해 보이는 영양소를 짚어주고, 다음 식사로 좋을 한국에서 구하기 쉬운 메뉴를 "
    "2~3가지 추천하세요. 각 추천에 한 줄 이유를 덧붙입니다. 5문장 이내, "
    "마크다운 헤더 없이 짧은 문단과 이모지 정도만 사용하세요."
)


def _create(system: str, user_content, schema: dict | None = None) -> str:
    kwargs: dict = {}
    if schema is not None:
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
    response = client.beta.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        # 안전 분류기가 드물게 오탐으로 거절할 때 서버 측에서 자동 폴백한다.
        betas=["server-side-fallback-2026-06-01"],
        fallbacks=[{"model": "claude-opus-4-8"}],
        **kwargs,
    )
    if response.stop_reason == "refusal":
        raise LLMRefusalError("요청이 안전 정책상 처리되지 않았습니다.")
    if response.stop_reason == "max_tokens":
        raise LLMTruncatedError("응답이 최대 길이에서 잘렸습니다.")
    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise LLMTruncatedError("모델 응답에 텍스트가 없습니다.")
    return text


def parse_meal(text: str) -> dict:
    """자유 텍스트 식사 기록 → {foods, total_kcal, comment}."""
    raw = _create(_PARSE_SYSTEM, f"식사 기록: {text}", schema=MEAL_SCHEMA)
    return json.loads(raw)


def parse_meal_image(image_b64: str, media_type: str, caption: str = "") -> dict:
    """식사 사진 → {foods, total_kcal, comment}."""
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
        {"type": "text", "text": f"식사 사진입니다. {caption}".strip()},
    ]
    raw = _create(_PARSE_IMAGE_SYSTEM, content, schema=MEAL_SCHEMA)
    return json.loads(raw)


def refine_meal(parsed: dict, refs: list[dict]) -> dict:
    """식약처 DB 조회 결과로 파싱된 칼로리를 보정한다."""
    payload = (
        f"LLM 추정 파싱 결과:\n{json.dumps(parsed, ensure_ascii=False)}\n\n"
        f"식약처 식품영양성분 DB 조회 결과:\n{json.dumps(refs, ensure_ascii=False)}"
    )
    raw = _create(_REFINE_SYSTEM, payload, schema=MEAL_SCHEMA)
    return json.loads(raw)


def _format_meals(meals: list[dict]) -> str:
    lines = []
    for m in meals:
        foods = ", ".join(f"{f['name']} {f['quantity']}({f['kcal']}kcal)" for f in m["foods"])
        lines.append(f"[{m['meal_date']} {m['slot']}] {foods} — 합계 {m['total_kcal']}kcal")
    return "\n".join(lines)


def daily_summary(meal_date: str, meals: list[dict], goal_kcal: int | None = None) -> str:
    """하루 식사 기록 → 총 칼로리 + 영양 밸런스 코멘트."""
    goal_line = f"\n사용자의 하루 목표 칼로리: {goal_kcal} kcal (목표 대비 평가도 포함하세요)" if goal_kcal else ""
    return _create(
        _SUMMARY_SYSTEM,
        f"{meal_date} 하루 식사 기록입니다:\n{_format_meals(meals)}{goal_line}",
    )


def weekly_report(stats_text: str, meals: list[dict], goal_kcal: int | None = None) -> str:
    """최근 7일 통계 + 기록 → 주간 리포트."""
    goal_line = f"\n사용자의 하루 목표 칼로리: {goal_kcal} kcal" if goal_kcal else ""
    return _create(
        _WEEKLY_SYSTEM,
        f"주간 통계:\n{stats_text}{goal_line}\n\n상세 기록:\n{_format_meals(meals)}",
    )


def recommend(meals: list[dict]) -> str:
    """최근 식사 기록 → 다음 식사 메뉴 추천."""
    if not meals:
        return "아직 쌓인 식사 기록이 없어요. 먼저 식사를 기록해 주시면 맞춤 추천을 드릴게요! 🙂"
    return _create(
        _RECOMMEND_SYSTEM,
        f"최근 식사 기록입니다:\n{_format_meals(meals)}\n\n다음 식사 메뉴를 추천해 주세요.",
    )
