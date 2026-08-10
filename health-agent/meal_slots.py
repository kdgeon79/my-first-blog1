"""KST 기준 시간/식사 슬롯 판정."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

SLOT_LABELS = {
    "breakfast": "아침",
    "lunch": "점심",
    "dinner": "저녁",
}


def now_kst() -> datetime:
    return datetime.now(KST)


def logical_date_kst(now: datetime | None = None) -> str:
    """식사 기록용 논리 날짜. 00:00~03:59는 전날 저녁의 연장이므로 전날로 귀속한다."""
    now = now or now_kst()
    d = now.date()
    if now.hour < 4:
        d -= timedelta(days=1)
    return d.isoformat()


def current_slot(now: datetime | None = None) -> str:
    """현재 시각이 속하는 식사 슬롯.

    04:00–10:30 아침, 10:30–16:00 점심, 그 외(저녁~새벽)는 저녁으로 본다.
    """
    now = now or now_kst()
    minutes = now.hour * 60 + now.minute
    if 4 * 60 <= minutes < 10 * 60 + 30:
        return "breakfast"
    if 10 * 60 + 30 <= minutes < 16 * 60:
        return "lunch"
    return "dinner"
