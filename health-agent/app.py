"""건강 관리 Slack 에이전트 — Socket Mode 앱 본체."""
import base64
import logging
import re
import urllib.request
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import config
import db
import llm
import logic
from meal_slots import KST, SLOT_LABELS, logical_date_kst, now_kst

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("health-agent")

scheduler = BackgroundScheduler(timezone=KST)

MEAL_PROMPTS = {
    "breakfast": "좋은 아침이에요! ☀️ 오늘 아침은 무엇을 드셨나요? (아직이라면 드신 후에 알려주세요)",
    "lunch": "점심시간이네요! 🍚 점심으로 무엇을 드셨나요?",
    "dinner": "저녁 드셨나요? 🌙 오늘 저녁 메뉴를 알려주시면 하루 요약도 함께 드릴게요.",
}

SUMMARY_KEYWORDS = {"요약", "오늘 요약", "하루 요약"}
RECOMMEND_KEYWORDS = {"추천", "메뉴 추천", "뭐 먹지", "뭐 먹을까"}
WEEKLY_KEYWORDS = {"주간", "주간 리포트", "주간리포트"}
DELETE_KEYWORDS = {"삭제", "기록 삭제", "마지막 삭제", "취소"}
HELP_KEYWORDS = {"도움말", "help", "사용법"}

GOAL_RE = re.compile(r"^목표(?:\s+(\d{3,5})\s*(?:kcal|칼로리)?)?$")
CORRECT_RE = re.compile(r"^수정[:\s]\s*(.+)$", re.DOTALL)

HELP_TEXT = (
    "제가 할 수 있는 일이에요! 🙌\n"
    "• 드신 음식을 자유롭게 적거나 *사진을 보내주세요* → 칼로리를 계산해 기록해요\n"
    "• `요약` → 오늘 하루 식사 요약과 영양 코멘트\n"
    "• `추천` → 최근 기록 기반 다음 식사 메뉴 추천\n"
    "• `주간` → 최근 7일 주간 리포트 (매주 일요일 밤에도 자동 발송)\n"
    "• `목표 2000` → 하루 목표 칼로리 설정 / `목표` → 현재 목표 확인\n"
    "• `수정 김치찌개랑 밥` → 마지막 기록을 고쳐서 다시 계산\n"
    "• `삭제` → 마지막 기록 삭제\n"
    "매일 아침 9시 / 오후 1시 / 저녁 7시에 제가 먼저 여쭤보고, 2시간 동안 기록이 없으면 한 번 더 알려드려요!"
)


def _download_slack_image(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {config.SLACK_BOT_TOKEN}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _handle_image(event, say) -> bool:
    """메시지에 이미지가 있으면 사진 기록으로 처리한다. 처리했으면 True."""
    images = [
        f for f in (event.get("files") or [])
        if (f.get("mimetype") or "").startswith("image/") and f.get("url_private_download")
    ]
    if not images:
        return False
    file = images[0]
    caption = (event.get("text") or "").strip()
    say("📸 사진을 확인하고 있어요...")
    data = _download_slack_image(file["url_private_download"])
    image_b64 = base64.standard_b64encode(data).decode("utf-8")
    reply, is_dinner = logic.record_meal_from_image(image_b64, file["mimetype"], caption)
    say(reply)
    if is_dinner:
        say(logic.build_daily_summary())
    return True


def create_app() -> App:
    app = App(token=config.SLACK_BOT_TOKEN)

    @app.event("message")
    def handle_message(event, say):
        # DM 채널의 사용자 메시지만 처리. 사진 업로드는 subtype=file_share로 오므로 허용한다.
        if event.get("channel_type") != "im" or event.get("bot_id"):
            return
        if event.get("subtype") not in (None, "file_share"):
            return
        # 다른 워크스페이스 멤버의 DM이 소유자 기록에 섞이지 않도록 소유자만 처리
        if event.get("user") != config.SLACK_USER_ID:
            return

        try:
            if _handle_image(event, say):
                return

            text = (event.get("text") or "").strip()
            if not text:
                return

            goal_match = GOAL_RE.match(text)
            correct_match = CORRECT_RE.match(text)

            if text in HELP_KEYWORDS:
                say(HELP_TEXT)
            elif text in SUMMARY_KEYWORDS:
                say(logic.build_daily_summary())
            elif text in RECOMMEND_KEYWORDS:
                say(logic.build_recommendation())
            elif text in WEEKLY_KEYWORDS:
                say(logic.build_weekly_report())
            elif text in DELETE_KEYWORDS:
                say(logic.delete_last_meal())
            elif goal_match:
                if goal_match.group(1):
                    say(logic.set_goal(int(goal_match.group(1))))
                else:
                    goal = logic.get_goal()
                    say(
                        f"현재 하루 목표는 {goal:,} kcal예요. `목표 2000`처럼 보내면 바꿀 수 있어요."
                        if goal
                        else "아직 목표가 없어요. `목표 2000`처럼 보내서 설정해 보세요!"
                    )
            elif correct_match:
                reply, _ = logic.correct_last_meal(correct_match.group(1).strip())
                say(reply)
            else:
                reply, is_dinner = logic.record_meal(text)
                say(reply)
                if is_dinner:
                    say(logic.build_daily_summary())
        except llm.LLMTruncatedError:
            say("기록이 너무 길어서 한 번에 처리하지 못했어요. 식사를 나눠서 보내주시겠어요? 🙏")
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
        return
    # 2시간 뒤 기록이 없으면 1회 재질문
    sent_at = now_kst()
    scheduler.add_job(
        send_reminder,
        "date",
        run_date=sent_at + timedelta(hours=2),
        args=[app, slot, logical_date_kst(sent_at), sent_at.isoformat(timespec="seconds")],
        id=f"reminder-{slot}",
        replace_existing=True,
    )


def send_reminder(app: App, slot: str, meal_date: str, since_iso: str) -> None:
    try:
        if db.has_meal_since(meal_date, slot, since_iso):
            return
        app.client.chat_postMessage(
            channel=_dm_channel(app),
            text=f"아직 {SLOT_LABELS[slot]} 기록이 없어요! 드셨다면 메뉴를 알려주세요 🙂 (안 드셨으면 넘어가도 괜찮아요)",
        )
        logger.info("리마인더 발송: %s", slot)
    except Exception:
        logger.exception("리마인더 발송 실패: %s", slot)


def send_weekly_report(app: App) -> None:
    try:
        app.client.chat_postMessage(
            channel=_dm_channel(app),
            text="📊 이번 주 식사 리포트예요!\n\n" + logic.build_weekly_report(),
        )
        logger.info("주간 리포트 발송")
    except Exception:
        logger.exception("주간 리포트 발송 실패")


def start_scheduler(app: App) -> BackgroundScheduler:
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
    scheduler.add_job(
        send_weekly_report,
        CronTrigger(day_of_week="sun", hour=21, minute=0, timezone=KST),
        args=[app],
        id="weekly-report",
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
