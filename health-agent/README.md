# 건강 관리 Slack 에이전트

아침·점심·저녁에 **먼저 말을 걸어** 무엇을 먹었는지 묻고, 답변을 파싱해 **칼로리를 계산·기록**하고,
쌓인 기록을 바탕으로 **하루 요약과 음식 추천**을 해주는 Slack DM 에이전트입니다.
(리브에 이은 두 번째 Slack 에이전트 — [설계 문서](../) 기반 MVP)

## 동작 방식

- **스케줄러(APScheduler)** 가 매일 09:00 / 13:00 / 19:00 (KST)에 DM으로 식사 질문을 보냅니다.
- 사용자가 자유 텍스트로 답하면 (예: `김치찌개랑 밥 한 공기, 계란말이`)
  **Claude(claude-opus-5)** 가 음식명·분량을 파싱하고 칼로리를 추정 → **SQLite**에 저장합니다.
- 저녁 식사를 기록하면 **하루 총 칼로리 + 영양 밸런스 코멘트**를 자동으로 보냅니다.
- DM 명령어:
  - `요약` — 오늘 하루 식사 요약
  - `추천` — 최근 7일 기록 기반 다음 식사 메뉴 추천
  - `도움말` — 사용법 안내

칼로리는 LLM 추정(오차 ±20~30%)으로 시작하며, 추후 식약처 식품영양성분 DB 연동으로 정확도를
개선할 수 있습니다. 파싱 결과는 structured outputs(JSON 스키마)로 받아 항상 유효한 JSON이
보장됩니다. 또한 안전 분류기의 드문 오탐으로 요청이 거절될 경우 서버 측에서 자동으로
`claude-opus-4-8`로 폴백하도록 설정되어 있습니다.

## Slack 앱 설정

리브에서 쓰던 워크스페이스에 새 앱을 만들거나 기존 앱에 권한을 추가하세요.
이 에이전트는 **Socket Mode**를 사용하므로 공개 URL(이벤트 수신 서버)이 필요 없습니다.

1. https://api.slack.com/apps → **Create New App** (From scratch)
2. **Socket Mode** 활성화 → App-Level Token 발급 (`connections:write` 스코프) → `SLACK_APP_TOKEN`
3. **OAuth & Permissions** → Bot Token Scopes에 `chat:write`, `im:history`, `im:read`, `im:write` 추가
   → 워크스페이스에 설치 → Bot User OAuth Token → `SLACK_BOT_TOKEN`
4. **Event Subscriptions** → Enable Events → Subscribe to bot events에 `message.im` 추가
5. **App Home** → Messages Tab 활성화 ("Allow users to send Slash commands and messages from the messages tab" 체크)
6. Slack 프로필 → 더보기(⋯) → **멤버 ID 복사** → `SLACK_USER_ID`

## 실행

```bash
cd health-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # 토큰·API 키 채우기
python app.py
```

## 테스트

```bash
pip install pytest
pytest
```

LLM 호출은 테스트에서 모두 모킹되므로 API 키 없이 실행됩니다.

## 구조

| 파일 | 역할 |
|------|------|
| `app.py` | Slack Bolt(Socket Mode) 앱 + 스케줄러 기동 |
| `logic.py` | 기록/요약/추천 비즈니스 로직 (테스트 대상) |
| `llm.py` | Claude API 래퍼 (파싱·요약·추천 프롬프트) |
| `db.py` | SQLite 저장소 (`meals` 테이블) |
| `meal_slots.py` | KST 시간대·식사 슬롯 판정 |
| `config.py` | `.env` 로딩 및 설정 |

## 주의

- `.env`, `*.db`는 `.gitignore`에 포함되어 커밋되지 않습니다. Slack 토큰(`xoxb-...`)과
  API 키는 절대 커밋하지 마세요.
