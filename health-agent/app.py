"""건강 관리 Slack 에이전트 — Socket Mode 앱 본체."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import config
import db
import logic
from meal_slots import KST

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("health-agent")

MEAL_PROMPTS = {
    "breakfast": "좋은 아침이에요! ☀️ 오늘 아침은 무엇을 드셨나요? (아직이라면 드신 후에 알려주세요)",
    "lunch": "점심시간이네요! 🍚 점심으로 무엇을 드셨나요?",
    "dinner": "저녁 드셨나요? 🌙 오늘 저녁 메뉴를 알려주시면 하루 요약도 함께 드릴게요.",
}

SUMMARY_KEYWORDS = {"요약", "오늘 요약", "하루 요약"}
RECOMMEND_KEYWORDS = {"추천", "메뉴 추천", "뭐 먹지", "뭐 먹을까"}
HELP_KEYWORDS = {"도움말", "help", "사용법"}

HELP_TEXT = (
    "제가 할 수 있는 일이에요! 🙌\n"
    "• 드신 음식을 자유롭게 적어주세요 (예: \"김치찌개랑 밥 한 공기, 계란말이\") → 칼로리를 계산해 기록해요\n"
    "• `요약` → 오늘 하루 식사 요약과 영양 코멘트\n"
    "• `추천` → 최근 기록을 바탕으로 다음 식사 메뉴 추천\n"
    "매일 아침 9시 / 오후 1시 / 저녁 7시에 제가 먼저 여쭤볼게요!"
)


def create_app() -> App:
    app = App(token=config.SLACK_BOT_TOKEN)

    @app.event("message")
    def handle_message(event, say):
        # DM 채널의 사용자 메시지만 처리 (봇 메시지·수정/삭제 등 subtype 이벤트 제외)
        if event.get("channel_type") != "im" or event.get("bot_id") or event.get("subtype"):
            return
        text = (event.get("text") or "").strip()
        if not text:
            return

        try:
            if text in HELP_KEYWORDS:
                say(HELP_TEXT)
            elif text in SUMMARY_KEYWORDS:
                say(logic.build_daily_summary())
            elif text in RECOMMEND_KEYWORDS:
                say(logic.build_recommendation())
            else:
                reply, is_dinner = logic.record_meal(text)
                say(reply)
                if is_dinner:
                    say(logic.build_daily_summary())
        except Exception:
            logger.exception("메시지 처리 실패")
            say("죄송해요, 처리 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요. 🙏")

    return app


def _dm_channel(app: App) -> str:
    resp = app.client.conversations_open(users=[config.SLACK_USER_ID])
    return resp["channel"]["id"]


def send_meal_prompt(app: App, slot: str) -> None:
    try:
        app.client.chat_postMessage(channel=_dm_channel(app), text=MEAL_PROMPTS[slot])
        logger.info("식사 질문 발송: %s", slot)
    except Exception:
        logger.exception("식사 질문 발송 실패: %s", slot)


def start_scheduler(app: App) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=KST)
    for slot, (hour, minute) in {
        "breakfast": (9, 0),
        "lunch": (13, 0),
        "dinner": (19, 0),
    }.items():
        scheduler.add_job(
            send_meal_prompt,
            CronTrigger(hour=hour, minute=minute, timezone=KST),
            args=[app, slot],
            id=f"meal-prompt-{slot}",
        )
    scheduler.start()
    return scheduler


def main() -> None:
    missing = [
        name
        for name, value in {
            "SLACK_BOT_TOKEN": config.SLACK_BOT_TOKEN,
            "SLACK_APP_TOKEN": config.SLACK_APP_TOKEN,
            "SLACK_USER_ID": config.SLACK_USER_ID,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit(f".env에 다음 값을 설정해 주세요: {', '.join(missing)}")

    db.init_db()
    app = create_app()
    start_scheduler(app)
    logger.info("건강 관리 에이전트 시작 (Socket Mode)")
    SocketModeHandler(app, config.SLACK_APP_TOKEN).start()


if __name__ == "__main__":
    main()
