# 현재 상태 — 무엇이 되고, 무엇이 안 됐나

마지막 갱신: 2026-09-18 · **DAY 2 / 14 완료**

---

## 가장 먼저 알아야 할 것

**실제 모델로 아직 한 번도 돌려본 적이 없다.**

이전 제품에서 물려받은 리스크이고, 지금도 그대로다. 방침이
"API 키는 제작을 마친 뒤 맨 마지막에" 이므로 DAY 13~14까지 이어진다.

자체 테스트 134개 통과는 **권한 게이트와 경로 검사가 지켜진다**는 뜻이지,
에이전트 협업이 실제로 성공한다는 뜻이 아니다. 이 구분을 계속 지킨다.

**대응책**(구조로 막는다, [docs/architecture.md](docs/architecture.md) §4):
Mock 과 실제 Provider 가 **같은 계약 테스트**를 통과하게 만들고, 키 유무에
따른 교체를 **설정 한 줄**로 좁힌다. 그래야 마지막 날 키를 꽂는 일이
개조 공사가 아니라 설정 변경이 된다.

---

## DAY 1 — 완료

### 분석
- 저장소가 **다른 제품**이었음을 확인하고 재사용 지도를 만들었다
  ([docs/architecture.md](docs/architecture.md))
- `backend/legacy/` 는 이미 import 조차 되지 않는 상태임을 확인 —
  이전해도 회귀가 없다는 근거

### 구조 (지시서 §6)
- `frontend/` + `backend/app/{providers,agents,orchestrator,tools,database,usage,models,api}`
- 평평한 top-level import 를 `app.` 패키지 import 로 일괄 이전.
  **호출부는 한 줄도 고치지 않았다** — 별칭으로 부르던 이름을 그대로 뒀다
- 빈 패키지의 `__init__.py` 에 무엇이 언제 들어오는지 기록

### 환경
- `.venv` + `backend/requirements.txt` 전체 설치 (Python 3.14 휠 전부 존재)
- `backend/run.py` 실행 진입점
- Next.js 16.3.5 · React 19.2.8 · Tailwind 4 · TypeScript 5 스캐폴딩
- `next.config.ts` 에 `/api` → `127.0.0.1:8000` 프록시 (SSE 포함, CORS 불필요)

### 설정 (지시서 §14)
- 단가표를 코드에서 빼 `backend/pricing.json` 으로. `verified: false` 표시
- §18 의 안전장치 상수(`MAX_AGENT_STEPS` · `MAX_RETRY` · 비용 상한 3종)를
  `config.py` 에 이름 그대로 배치
- `.env.example` · `docker-compose.yml`

### 테스트
- 구조 이전 후 **134개 전부 통과**
- 실패했던 32개는 전부 `monkeypatch.setattr("screen.perform", …)` 처럼
  **문자열로 지정된 패치 대상**이 원인이었다. 보안 로직은 무사했다

---

## DAY 2 — 완료

### Provider 어댑터 (§7)
- `providers/base.py` — `AIProvider` 인터페이스. 하위 클래스는 `available` ·
  `_generate` · `_stream` 셋만 구현하면 재시도·사용량 집계를 공짜로 얻는다
- `providers/mock.py` — **결정적** Mock. 같은 요청에 같은 답을 준다
- `providers/claude.py` — Anthropic 어댑터. SDK 예외를 우리 예외로 번역한다
- `providers/registry.py` — 키 유무 분기가 **여기 한 곳에만** 있다

### 안전장치 (§18)
- 재시도 + 지수 백오프 + 지터. `retry-after` 헤더를 존중한다
- 재시도 가능 여부를 **예외 타입에 박았다.** 인증 오류에 5번 재시도하는 것은
  5번 틀리는 것이다
- 스트리밍은 재시도하지 않는다 — 조각을 내보낸 뒤 다시 하면 같은 문장이 두 번 보인다
- `FallbackProvider`. **Mock 은 이 사슬에 넣지 않았다** — 실패가 성공처럼
  보이면 가짜 결과물이 진짜처럼 나간다

### 계약 테스트
- 같은 계약을 Mock 과 Claude 에 **똑같이** 건다. 키가 없어 Claude 쪽 5개는
  skip 되지만, skip 이 출력에 남아 "아직 검증 안 됨"을 계속 드러낸다
- 실패한 호출이 사용량에 잡히지 않는지, 백오프가 상한을 넘지 않는지,
  오류 메시지에서 키가 가려지는지까지 확인

### API
- `GET /api/providers` · `/api/state` 에 제공자 현황. `mock: true` 를
  화면이 표시할 수 있어야 한다

### 정정
- DAY 1 계획에 `providers/mock.py` 를 `legacy/agents/mock.py` 에서 가져온다고
  적었는데 틀렸다. 그건 **에이전트 수준**(plan/implement/review) 대본이지
  제공자 수준 목이 아니다. DAY 4~5 에 쓴다. 제공자 목은 새로 썼다

---

## 다음 — DAY 3

- `providers/gemini.py` — 기존 `gemini_client.py` 를 인터페이스 아래로
- `providers/openai.py` — 신규
- 두 제공자를 같은 계약 테스트에 추가 (키 없으면 skip)
- 대체 사슬 설정 (Claude → Gemini 등)
- 모델 설정 시스템

---

## 아직 손대지 않은 것

| 지시서 | 항목 | 예정 |
|---|---|---|
| §7 | Gemini · OpenAI 어댑터 | DAY 3 |
| §8 | 직원 5명 정의 | DAY 4 |
| §9 §10 | Orchestrator · AUTO | DAY 5 |
| §11 | MANUAL 모드 | DAY 6 |
| §13 | SSE 실시간 로그 | DAY 7 (버스는 이미 있음) |
| §12 CEO 화면 | 대시보드 | DAY 8 |
| §4 | 가상 사무실 UI | DAY 9 |
| §14 §15 | 사용량 · 크레딧 | DAY 11 |
| §12 | 프로젝트 저장 | DAY 12 |
| §16 | 가격 페이지 | 미정 |

---

## 고치지 못한 위험 — 정직하게

### 실제 모델 실행 0회
위에 적은 그대로. 가장 큰 것이다.

### 단가표가 검증되지 않았다
`pricing.json` 의 값은 이전 작업에서 물려받았고 공식 단가와 대조되지
않았다. 검증 전까지 **§17 원가 관리(판매가의 50% 이하)는 계산이 아니라
추측이다.** DAY 11에 실제 단가로 대조한다.

### `usage/` 의 에이전트 키가 하드코딩되어 있다
`PM` · `DEV` · `QA` 세 개로 고정이다. 직원 5명 체계(§8)로 바꿀 때
같이 고쳐야 한다. 안 고치면 직원별 사용량이 섞인다.

### docker 가 이 개발 머신에 없다
`docker-compose.yml` 은 작성했지만 실행으로 검증하지 못했다.

### 물려받은 위험은 그대로 남아 있다
`run_command` 는 사용자 권한 그대로 실행되고, 화면 캡처는 외부로 나가며,
프롬프트 주입을 완전히 막을 수는 없다. 이전 제품의 방어(승인 게이트)가
그대로 붙어 있지만, AI COMPANY 가 SaaS 로 가면 **이 전제가 달라진다** —
서버에서 남의 코드를 돌리는 문제는 DAY 13 보안 테스트에서 다시 본다.
