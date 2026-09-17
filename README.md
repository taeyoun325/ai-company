# AI COMPANY

**AI 직원들이 실제 회사처럼 협업합니다.**

당신은 CEO다. AI 직원에게 직접 업무를 지시하거나, AUTO 모드에서
오케스트레이터가 알맞은 직원을 골라 일을 맡기게 한다.

```
CEO ─▶ 직원 선택 / AUTO ─▶ Orchestrator ─▶ AI 작업 ─▶ 다른 AI 검증 ─▶ 결과
```

---

## 지금 상태 — 정직하게

**DAY 2 / 14 완료.** 제공자 계층이 섰다. 아직 AI 직원은 일하지 않는다.

| | 상태 |
|---|---|
| 백엔드 서버 (FastAPI) | 동작 — 36개 라우트, `GET /api/state` 200 |
| 프론트엔드 (Next.js 16) | 스캐폴딩 + 빌드 통과. 화면은 아직 기본 템플릿 |
| 자체 테스트 | **177개 통과 / 5개 보류** |
| Provider 추상화 (§7) | ✅ `AIProvider` · Mock · Claude · 레지스트리 |
| 재시도·백오프·대체 (§18) | ✅ 기반 클래스에 내장 |
| Gemini · OpenAI 어댑터 | DAY 3 |
| Orchestrator (§9) | DAY 5 |
| 가상 사무실 UI (§4) | DAY 9 |
| Credit 시스템 (§15) | DAY 11 |
| **실제 모델 호출** | **0회 — 아직 한 번도 안 해봤다** |

보류된 5개는 Claude 제공자의 **계약 테스트**다. Mock 과 똑같은 계약이
걸려 있고 키가 없어서 skip 된다. 키를 넣는 순간 자동으로 걸린다.

마지막 줄이 이 프로젝트의 최대 리스크다. 자세한 것은 [STATUS.md](STATUS.md).

---

## 실행

키가 없어도 뜬다. 없으면 Mock 제공자로 동작한다 — `PROVIDER_MODE` 한 줄로
바뀐다(`auto` · `mock` · `real`). 배포에서는 `real` 을 쓴다. `auto` 로 두면
키 설정이 빠졌을 때 조용히 Mock 이 돌아가서 가짜 결과물이 진짜처럼 나간다.

**백엔드**

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
.venv/Scripts/python.exe backend/run.py
```

**프론트엔드** (다른 터미널)

```bash
cd frontend && npm install && npm run dev
```

`http://localhost:3000` — `/api` 는 백엔드(8000)로 그대로 넘어간다.
SSE도 이 경로를 타므로 CORS 설정이 따로 없다.

**테스트**

```bash
.venv/Scripts/python.exe -m pytest -q
```

환경변수는 [.env.example](.env.example)에 전부 주석과 함께 있다.

---

## 구조

```
ai-company/
├── frontend/              Next.js 16 · TypeScript · Tailwind 4
├── backend/
│   ├── run.py             실행 진입점
│   ├── pricing.json       모델 단가·크레딧 배수 (코드 밖, §14)
│   ├── app/
│   │   ├── main.py        FastAPI 앱
│   │   ├── config.py      경로·모델·안전장치·단가 로딩
│   │   ├── bus.py         이벤트 버스 → SSE (§13)
│   │   ├── providers/     AI 제공자 어댑터 (§7) ← 모델 교체 지점
│   │   ├── agents/        AI 직원 정의 (§8)
│   │   ├── orchestrator/  업무 분배·검증·재작업 (§9)
│   │   ├── usage/         토큰·비용·크레딧 (§14 §15)
│   │   ├── database/      영속화 (§12)
│   │   ├── tools/         에이전트가 쓰는 도구
│   │   ├── models/        API 스키마
│   │   └── api/           라우터
│   ├── legacy/            이전 설계. 참고용, 실행되지 않음
│   └── tests/             134개
└── docs/
```

`§` 는 개발 지시서의 항목 번호다. 폴더가 곧 지시서의 어느 요구사항을
담당하는지 가리킨다.

---

## 이 저장소의 이전 이력

이 저장소에는 **다른 제품**이 있었다 — Claude Code 형태의 로컬 개발도구
("AI 에이전트 컴퍼니"). AI COMPANY 는 그 위에 새로 짓되, 검증된 계층을
버리지 않았다.

| 물려받은 것 | 쓰이는 곳 |
|---|---|
| `bus.py` | 실시간 작업 로그 (§13) |
| `usage/` | 사용량·비용 집계 (§14) |
| `secrets_broker.py` | 키를 환경에서 꺼내 지운다 (§18) |
| `approvals.py` | 권한 게이트 5모드 |
| `workspace.py` | 경로 탈출 차단 |
| `providers/anthropic_client.py` · `gemini_client.py` | Provider 어댑터의 속 (§7) |
| `legacy/orchestrator.py` | 위상정렬·재작업 루프·비용 하드스톱 (§9 참고본) |
| `legacy/agents/mock.py` | Mock 직원 (§1) |
| `tests/` 134개 | 보안 불변식 |

`backend/legacy/` 는 **실행되지 않는다.** import 조차 되지 않는 상태였고
(DAY 1 확인) 그대로 뒀다. 설계 기록이자 부품 창고다.

자세한 대응표는 [docs/architecture.md](docs/architecture.md).

---

## 알려진 위험

- **실제 모델로 한 번도 안 돌려봤다.** Mock 으로 전 구간을 만들고 맨
  마지막에 키를 넣는 방침이다. 그래서 Provider 계층은 **Mock 과 실제가
  같은 계약을 통과하는지** 테스트로 못박아야 한다. 안 그러면 마지막 날
  키를 꽂는 순간 전부 터진다.
- **단가표가 검증되지 않았다.** `pricing.json` 의 값은 이전 작업에서
  물려받은 것이고 공식 단가와 대조되지 않았다. 검증 전까지 §17 원가
  계산(판매가의 50% 이하)은 근거가 아니라 추측이다. `verified: false`
  로 파일에 적어뒀다.
- **docker 가 이 개발 머신에 없다.** `docker-compose.yml` 은 아직
  실행으로 검증되지 않았다.
