# 건강 관리 Slack 에이전트

아침·점심·저녁에 **먼저 말을 걸어** 무엇을 먹었는지 묻고, 답변을 파싱해 **칼로리를 계산·기록**하고,
쌓인 기록을 바탕으로 **하루 요약과 음식 추천**을 해주는 Slack DM 에이전트입니다.
(리브에 이은 두 번째 Slack 에이전트 — [설계 문서](../) 기반 MVP)

## 동작 방식

- **스케줄러(APScheduler)** 가 매일 09:00 / 13:00 / 19:00 (KST)에 DM으로 식사 질문을 보내고,
  2시간 동안 해당 끼니 기록이 없으면 **한 번 더** 물어봅니다.
- 사용자가 자유 텍스트(예: `김치찌개랑 밥 한 공기, 계란말이`)나 **음식 사진**으로 답하면
  LLM이 음식명·분량을 파싱하고 칼로리를 추정 → **SQLite**에 저장합니다.
- `NUTRITION_API_KEY`를 설정하면 파싱된 음식명으로 **식약처 식품영양성분 DB**를 조회해
  공식 수치로 칼로리를 보정합니다 (키가 없거나 조회 실패 시 LLM 추정만 사용).
- 저녁 식사를 기록하면 **하루 총 칼로리 + 영양 밸런스 코멘트**를 자동으로 보내고,
  매주 **일요일 21:00**에는 주간 리포트를 보냅니다.
- DM 명령어:
  - `요약` — 오늘 하루 식사 요약
  - `추천` — 최근 7일 기록 기반 다음 식사 메뉴 추천
  - `주간` — 최근 7일 주간 리포트
  - `목표 2000` — 하루 목표 칼로리 설정 / `목표` — 현재 목표 확인 (기록 시 남은 칼로리 표시)
  - `수정 김치찌개랑 밥` — 마지막 기록을 고쳐서 다시 계산 (같은 끼니·날짜 유지)
  - `삭제` — 마지막 기록 삭제
  - `도움말` — 사용법 안내

칼로리는 기본적으로 LLM 추정(오차 ±20~30%)이며, 식약처 DB 보정으로 정확도를 높일 수 있습니다.
새벽(00~04시)에 기록한 야식은 전날 저녁으로 집계됩니다.

## LLM 백엔드

리브와 같은 비용 원칙(구독 계정 CLI 사용, API 과금 회피)을 따르며, `.env`로 전환할 수 있습니다.

| `LLM_BACKEND` | 설명 |
|---|---|
| `cli` (기본) | 로컬 CLI를 자식 프로세스로 실행. `LLM_CLI=codex`(기본, ChatGPT 계정) 또는 `claude`(Claude Code CLI). CLI에 로그인되어 있어야 하고, PATH에 없으면 `LLM_CLI_PATH`로 절대 경로를 지정합니다. 사진은 임시 파일로 저장해 CLI에 전달합니다(codex는 `-i` 플래그, claude는 파일 경로를 읽게 함) |
| `api` | Anthropic API 직접 호출 (`claude-opus-5`). structured outputs로 JSON이 보장되고, 안전 분류기 오탐 시 서버 측에서 `claude-opus-4-8`로 자동 폴백합니다. `ANTHROPIC_API_KEY` 필요 |

CLI 모드에서는 JSON 스키마를 프롬프트로 요구하고 응답에서 JSON을 추출·검증합니다.
출력에 배너가 섞여도 견디도록 만들어져 있지만, 파싱 안정성은 `api` 모드가 더 높습니다.

## Slack 앱 설정

리브에서 쓰던 워크스페이스에 새 앱을 만들거나 기존 앱에 권한을 추가하세요.
이 에이전트는 **Socket Mode**를 사용하므로 공개 URL(이벤트 수신 서버)이 필요 없습니다.

1. https://api.slack.com/apps → **Create New App** (From scratch)
2. **Socket Mode** 활성화 → App-Level Token 발급 (`connections:write` 스코프) → `SLACK_APP_TOKEN`
3. **OAuth & Permissions** → Bot Token Scopes에 `chat:write`, `im:history`, `im:read`, `im:write`,
   `files:read`(사진 기록용) 추가
   → 워크스페이스에 설치 → Bot User OAuth Token → `SLACK_BOT_TOKEN`
4. **Event Subscriptions** → Enable Events → Subscribe to bot events에 `message.im` 추가
5. **App Home** → Messages Tab 활성화 ("Allow users to send Slash commands and messages from the messages tab" 체크)
6. Slack 프로필 → 더보기(⋯) → **멤버 ID 복사** → `SLACK_USER_ID`

### (선택) 식약처 식품영양성분 DB

1. [공공데이터포털](https://www.data.go.kr)에서 "식품의약품안전처_식품영양성분DB" 검색 → 활용신청
2. 발급된 인증키를 `.env`의 `NUTRITION_API_KEY`에 설정
3. 조회 결과는 로컬 `nutrition_cache` 테이블에 캐시되어 같은 음식은 재조회하지 않습니다

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
| `app.py` | Slack Bolt(Socket Mode) 앱 + 스케줄러(식사 질문·리마인더·주간 리포트) |
| `logic.py` | 기록/수정/삭제/목표/요약/추천/주간 리포트 비즈니스 로직 (테스트 대상) |
| `llm.py` | Claude API 래퍼 (텍스트·사진 파싱, DB 보정, 요약·추천·리포트 프롬프트) |
| `nutrition.py` | 식약처 식품영양성분 DB 조회·보정 (키 없으면 무동작) |
| `db.py` | SQLite 저장소 (`meals`, `settings`, `nutrition_cache` 테이블) |
| `meal_slots.py` | KST 시간대·식사 슬롯 판정 |
| `config.py` | `.env` 로딩 및 설정 |

## 주의

- `.env`, `*.db`는 `.gitignore`에 포함되어 커밋되지 않습니다. Slack 토큰(`xoxb-...`)과
  API 키는 절대 커밋하지 마세요.
- **절전 주의**: 스케줄러가 프로세스 안에서 돌기 때문에 컴퓨터가 잠들어 있으면 그 시간의
  식사 질문·리마인더는 발송되지 않습니다. 장기적으로는 24시간 켜져 있는 환경(라즈베리파이,
  소형 서버 등)으로 옮기는 것을 권장합니다. CLI 백엔드를 쓸 경우 해당 서버에도 CLI 로그인이
  필요합니다.
