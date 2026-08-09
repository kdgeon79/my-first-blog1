"""Slack 이벤트와 무관한 순수 비즈니스 로직 (테스트 대상)."""
import db
import llm
from meal_slots import SLOT_LABELS, current_slot, logical_date_kst


def record_meal(text: str, slot: str | None = None) -> tuple[str, bool]:
    """식사 텍스트를 파싱·저장하고 (응답 메시지, 저녁 여부)를 돌려준다."""
    slot = slot or current_slot()
    meal_date = logical_date_kst()

    parsed = llm.parse_meal(text)
    foods = parsed["foods"]
    total = parsed["total_kcal"]
    db.save_meal(meal_date, slot, text, foods, total)

    day_total = sum(m["total_kcal"] for m in db.meals_on(meal_date))

    lines = [f"🍽 {SLOT_LABELS[slot]} 식사 기록 완료!"]
    lines += [f"• {f['name']} {f['quantity']} — 약 {round(f['kcal'])} kcal" for f in foods]
    lines.append(f"합계: 약 {round(total)} kcal (오늘 누적 {round(day_total)} kcal)")
    if parsed.get("comment"):
        lines.append(f"💬 {parsed['comment']}")
    return "\n".join(lines), slot == "dinner"


def build_daily_summary(meal_date: str | None = None) -> str:
    meal_date = meal_date or logical_date_kst()
    meals = db.meals_on(meal_date)
    if not meals:
        return "오늘 기록된 식사가 아직 없어요. 드신 음식을 말씀해 주시면 기록해 드릴게요! 🙂"
    return llm.daily_summary(meal_date, meals)


def build_recommendation(days: int = 7) -> str:
    return llm.recommend(db.recent_meals(days))
