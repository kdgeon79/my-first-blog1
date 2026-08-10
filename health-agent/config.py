"""환경 변수 및 공통 설정."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Slack
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")
# 식사 질문을 받을 사용자의 Slack 멤버 ID (예: U0123ABCDEF)
SLACK_USER_ID = os.environ.get("SLACK_USER_ID", "")

# LLM 백엔드 — cli(기본): 로컬 CLI 자식 프로세스로 실행해 API 과금 없음 / api: Anthropic API
LLM_BACKEND = os.environ.get("LLM_BACKEND", "cli")
LLM_CLI = os.environ.get("LLM_CLI", "codex")            # codex | claude
LLM_CLI_PATH = os.environ.get("LLM_CLI_PATH", "")       # CLI 실행 파일 절대 경로 (PATH에 없을 때)
LLM_CLI_TIMEOUT = int(os.environ.get("LLM_CLI_TIMEOUT", "300"))

# api 백엔드용 — API 키는 SDK가 ANTHROPIC_API_KEY 환경 변수에서 직접 읽는다.
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5")

# 식약처 식품영양성분 DB (공공데이터포털) — 키가 없으면 LLM 추정만 사용
NUTRITION_API_KEY = os.environ.get("NUTRITION_API_KEY", "")
NUTRITION_API_URL = os.environ.get(
    "NUTRITION_API_URL",
    "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02",
)

# 데이터
DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "meals.db"))

TIMEZONE = "Asia/Seoul"
