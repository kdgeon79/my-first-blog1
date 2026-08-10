"""Slack 이벤트와 무관한 순수 비즈니스 로직 (테스트 대상)."""
from collections import defaultdict

import db
import llm
import nutrition
from meal_slots import SLOT_LABELS, current_slot, logical_date_kst

GOAL_KEY = "daily_kcal_goal"


def get_goal() -> int | None:
    value = db.get_setting(GOAL_KEY)
    return int(value) if value else None


def set_goal(kcal: int) -> str:
    db.set_setting(GOAL_KEY, str(kcal))
    return f"🎯 하루 목표 칼로리를 {kcal:,} kcal로 설정했어요! 기록할 때마다 남은 칼로리를 알려드릴게요."


def _save_and_reply(parsed: dict, text: str, slot: str, meal_date: str, prefix: str = "") -> str:
    foods = parsed["foods"]
    total = parsed["total_kcal"]
    db.save_meal(meal_date, slot, text, foods, total)

    day_total = sum(m["total_kcal"] for m in db.meals_on(meal_date))

    lines = [f"{prefix}🍽 {SLOT_LABELS[slot]} 식사 기록 완료!"]
    lines += [f"• {f['name']} {f['quantity']} — 약 {round(f['kcal'])} kcal" for f in foods]
    lines.append(f"합계: 약 {round(total)} kcal (오늘 누적 {round(day_total)} kcal)")
    goal = get_goal()
    if goal:
        remaining = goal - day_total
        if remaining >= 0:
            lines.append(f"🎯 목표 {goal:,} kcal까지 {round(remaining)} kcal 남았어요")
        else:
            lines.append(f"🎯 목표 {goal:,} kcal를 {round(-remaining)} kcal 초과했어요")
    if parsed.get("comment"):
        lines.append(f"💬 {parsed['comment']}")
    return "\n".join(lines)


def record_meal(text: str, slot: str | None = None) -> tuple[str, bool]:
    """식사 텍스트를 파싱·저장하고 (응답 메시지, 저녁 여부)를 돌려준다."""
    slot = slot or current_slot()
    meal_date = logical_date_kst()
    parsed = nutrition.refine(llm.parse_meal(text))
    return _save_and_reply(parsed, text, slot, meal_date), slot == "dinner"


def record_meal_from_image(
    image_b64: str, media_type: str, caption: str = "", slot: str | None = None
) -> tuple[str, bool]:
    """식사 사진을 파싱·저장하고 (응답 메시지, 저녁 여부)를 돌려준다."""
    slot = slot or current_slot()
    meal_date = logical_date_kst()
    parsed = nutrition.refine(llm.parse_meal_image(image_b64, media_type, caption))
    raw_text = f"[사진] {caption}".strip()
    return _save_and_reply(parsed, raw_text, slot, meal_date), slot == "dinner"


def delete_last_meal() -> str:
    meal = db.last_meal()
    if not meal:
        return "삭제할 식사 기록이 없어요."
    db.delete_meal(meal["id"])
    foods = ", ".join(f["name"] for f in meal["foods"])
    return (
        f"🗑 마지막 기록을 삭제했어요: {meal['meal_date']} {SLOT_LABELS.get(meal['slot'], meal['slot'])} "
        f"({foods}, 약 {round(meal['total_kcal'])} kcal)"
    )


def correct_last_meal(text: str) -> tuple[str, bool]:
    """마지막 기록을 지우고 같은 날짜·슬롯으로 다시 기록한다."""
    meal = db.last_meal()
    if not meal:
        return "수정할 식사 기록이 없어요. 새로 기록하려면 드신 음식을 그냥 보내주세요!", False
    # 파싱이 실패해도 원본 기록이 남도록, 파싱을 끝낸 뒤에 삭제한다
    parsed = nutrition.refine(llm.parse_meal(text))
    db.delete_meal(meal["id"])
    reply = _save_and_reply(parsed, text, meal["slot"], meal["meal_date"], prefix="🔁 마지막 기록을 수정했어요!\n")
    return reply, False


def build_daily_summary(meal_date: str | None = None) -> str:
    meal_date = meal_date or logical_date_kst()
    meals = db.meals_on(meal_date)
    if not meals:
        return "오늘 기록된 식사가 아직 없어요. 드신 음식을 말씀해 주시면 기록해 드릴게요! 🙂"
    return llm.daily_summary(meal_date, meals, goal_kcal=get_goal())


def build_recommendation(days: int = 7) -> str:
    return llm.recommend(db.recent_meals(days))


def weekly_stats(meals: list[dict]) -> str:
    """일별 합계·평균 등 통계는 코드로 계산해 LLM에 넘긴다."""
    per_day: dict[str, float] = defaultdict(float)
    for m in meals:
        per_day[m["meal_date"]] += m["total_kcal"]
    days = sorted(per_day)
    avg = sum(per_day.values()) / len(days)
    lines = [f"- {d}: {round(per_day[d])} kcal" for d in days]
    lines.append(f"기록한 날: {len(days)}일 / 7일, 하루 평균 약 {round(avg)} kcal")
    return "\n".join(lines)


def build_weekly_report() -> str:
    meals = db.recent_meals(7)
    if not meals:
        return "지난 7일간 식사 기록이 없어요. 이번 주부터 같이 기록해 봐요! 💪"
    return llm.weekly_report(weekly_stats(meals), meals, goal_kcal=get_goal())
