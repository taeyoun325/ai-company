# 구조와 재사용 지도

DAY 1 산출물. **무엇을 물려받았고, 무엇을 새로 지어야 하는가.**

---

## 1. 출발점 — 저장소에 있던 것

이 저장소에는 AI COMPANY 와 **다른 제품**이 있었다.

| | 기존 저장소 | 지시서의 AI COMPANY |
|---|---|---|
| 정체 | Claude Code 형 **로컬 개발도구** | **SaaS** — 사용자가 CEO |
| 작업 대상 | 사용자의 실제 프로젝트 폴더 | 서버가 만드는 산출물 |
| 진행 방식 | 대화형 루프, 모델이 다음 행동 결정 | **Orchestrator + Task Graph** |
| 직원 | 메인 1 + planner/reviewer/tester | **5명 + AUTO/MANUAL 선택** |
| UI | 단일 HTML 762줄 | **Next.js + 게임형 가상 사무실** |
| 제공자 | Anthropic, Gemini | + OpenAI, Higgsfield |
| 과금 | 없음 | **Credit + 구독 요금제** |

제품 개념은 다르지만 **하부 계층은 거의 그대로 쓴다.** 검증된 보안·비용·
SSE 코드를 버릴 이유가 없다.

---

## 2. 재사용 지도

### 그대로 쓰는 것

| 물려받은 파일 | 새 자리 | 지시서 |
|---|---|---|
| `bus.py` | `app/bus.py` | §13 실시간 로그 · SSE |
| `secrets_broker.py` | `app/secrets_broker.py` | §18 기본 보안 |
| `approvals.py` | `app/approvals.py` | §18 안전장치 |
| `workspace.py` | `app/workspace.py` | 경로 탈출 차단 |
| `attachments.py` · `screen.py` | `app/` | 부가 기능 |
| `scheduler.py` · `timeline.py` | `app/` | 예약 · 협업 타임라인 |
| `server.py` | `app/main.py` | FastAPI 앱 |
| `tests_selftest.py` | `tests/test_selftest.py` | 보안 불변식 134개 |

### 손봐서 쓰는 것

| 물려받은 파일 | 새 자리 | 무엇을 고쳐야 하나 |
|---|---|---|
| `usage.py` | `app/usage/__init__.py` | 에이전트 키가 `PM/DEV/QA` 로 **하드코딩**되어 있다. 직원 5명 체계로 바꿔야 한다 (§8) |
| `config.py` | `app/config.py` | ✅ DAY 1에 단가표를 `pricing.json` 으로 뺐다 (§14) |
| `agents/llm.py` | `app/providers/anthropic_client.py` | `AIProvider` 인터페이스 아래로 넣는다 (§7) |
| `gemini.py` | `app/providers/gemini_client.py` | 같음 |
| `agent_tools.py` | `app/tools/agent_tools.py` | Developer 직원의 도구로 재사용 |
| `agent_core.py` · `subagents.py` | `app/agents/` | 도구 루프와 교차검토 프롬프트만 뽑아 쓴다 |

### 창고에 둔 것 — `backend/legacy/`

**실행되지 않는다.** DAY 1에 확인한 사실: 이전 재설계 때 `legacy/` 로
옮겨지면서 import 가 깨졌고, `pytest legacy/tests_legacy.py` 는
`ModuleNotFoundError: No module named 'config'` 로 수집조차 안 된다.
고치지 않고 그대로 뒀다 — 지우지 않는 이유는 **부품이 들어 있어서**다.

| 부품 | 어디에 쓰나 |
|---|---|
| `legacy/orchestrator.py` | **§9 의 핵심 참고본.** 위상정렬(`_topo`), 재작업 루프, 라운드·비용 하드스톱, 태스크 지문(`_sig`)이 이미 있다 |
| `legacy/schemas.py` | §9 Task Graph 계약 (`Plan` · `Task` · `QAVerdict`) |
| `legacy/store.py` | §12 프로젝트 저장 · 파일 이력 · diff |
| `legacy/agents/mock.py` | §1 Mock **직원**(plan/implement/review 대본). 제공자 수준 목이 아니다 — DAY 4~5 에 쓴다 |
| `legacy/agents/{pm,dev,qa}.py` | Strategist · Developer · Analyst 의 원형 |
| `legacy/runner.py` | 격리된 pytest 실행 |
| `legacy/tools/fs.py` | 역할별 쓰기 권한 |

---

## 3. 지금 서 있는 골격

```
backend/app/
├── main.py         FastAPI 앱 (35 라우트) — 동작함
├── config.py       경로 · 모델 · 안전장치 · 단가 로딩
├── bus.py          이벤트 버스 → SSE
├── providers/      ← DAY 2~3.  base.AIProvider 아래로 정리
│   ├── anthropic_client.py    (있음)
│   └── gemini_client.py       (있음)
├── agents/         ← DAY 4.  직원 5명 정의
├── orchestrator/   ← DAY 5.  legacy/orchestrator.py 에서 가져온다
├── usage/          토큰·비용 집계 (있음) + DAY 11 크레딧
├── database/       ← DAY 12.  legacy/store.py 에서
├── tools/          agent_tools.py (있음)
├── models/         ← API 스키마
└── api/            ← 라우트가 늘면 main.py 에서 쪼갠다
```

빈 패키지에는 `__init__.py` 에 **무엇이 언제 들어오는지** 적어뒀다.
빈 폴더는 계획이 아니라 쓰레기이기 때문이다.

---

## 4. 키 없이 만들기 — 이 결정이 구조를 정한다

방침: **API 키는 제작을 마친 뒤 맨 마지막에 넣는다.**

이 방침의 대가는 이미 한 번 치러졌다. 이전 팀도 같은 순서로 갔고
(`STATUS.md`), 그 결과 "실제 모델 실행 0회"가 최대 미검증 리스크로 남았다.
자체 테스트 134개 통과는 **권한 게이트가 지켜진다**는 뜻이지 **에이전트
협업이 성공한다**는 뜻이 아니다.

같은 자리에 두 번 빠지지 않으려면 Provider 계층을 이렇게 짜야 한다:

1. `AIProvider` 인터페이스를 먼저 못박는다 (§7). ✅ DAY 2 완료
2. `MockProvider` 와 실제 Provider 가 **같은 계약 테스트**를 통과하게 한다.
   Mock 만 통과하는 테스트는 마지막 날 아무것도 보장하지 못한다.
3. 실패 경로(재시도 · 백오프 · fallback · 사용자 알림, §18)를 Mock 에서
   **일부러 재현**한다. API 오류는 키가 있어야만 볼 수 있는 게 아니다.
4. 키 유무에 따른 Provider 선택은 **설정 한 줄**이어야 한다. 코드 분기가
   여기저기 퍼지면 마지막 날 교체가 개조 공사가 된다.

이렇게 해두면 키를 꽂는 일이 "새 기능"이 아니라 "설정 변경"이 된다.

---

## 5. 검증된 사실 (DAY 1 실측)

```
Python 3.14.5 · Node 24.18.0 · npm 11.16.0 · git 2.55.0
gh 없음 · docker 없음

backend/requirements.txt 전체 설치 성공 (Python 3.14 휠 모두 존재)
pytest -q                     →  134 passed
app.main import                →  35 routes
GET /api/state                 →  200
GET /                          →  200 (38,880 bytes)
frontend: next 16.3.5 · react 19.2.8 · tailwind 4 · typescript 5
npm run build                  →  성공, 경고 없음
legacy/tests_legacy.py         →  수집 실패 (의도된 상태)
pricing.json                   →  7개 모델, verified=false
```


---

## 6. 지시서에서 의도적으로 벗어난 곳

기록해 두지 않으면 나중에 실수로 보인다.

### §7 의 `async def generate` → 동기 + async 래퍼

지시서는 제공자 인터페이스를 async 로 적었다. 핵심은 **동기**로 두고
`agenerate()` · `astream()` 을 따로 냈다.

이유: `bus.py` 와 `usage/` 가 실행(run) 범위를 `threading.local()` 로 잡는다.
한 스레드에서 코루틴이 번갈아 돌면 그 스레드 로컬이 서로 다른 실행의 것을
가리키고, **비용이 엉뚱한 프로젝트에 붙는다.** 여러 프로젝트를 동시에 돌리는
것이 이미 설계에 들어 있으므로(§MAX_CONCURRENT) 이건 이론적 위험이 아니다.

async 표면은 `asyncio.to_thread` 로 넘기므로 스레드 로컬이 그대로 지켜진다.
FastAPI 쪽에서 필요한 모양은 다 나온다.

### Mock 은 대체(fallback) 사슬에 넣지 않는다

지시서 §18 은 "fallback provider" 를 요구한다. 대체 사슬에는 **실제 제공자만**
세웠다(예: Claude → Gemini). 실제 호출이 실패했을 때 Mock 이 받아주면,
실패가 성공처럼 보이고 사용자는 Mock 이 지어낸 글을 AI 의 작업 결과로 받는다.

Mock 은 "아무 키도 없을 때"와 "일부러 mock 모드일 때"만 쓴다. 그 사실은
`/api/providers` 로 화면까지 전달된다.
