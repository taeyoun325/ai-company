# AI COMPANY

**AI 직원들이 실제 회사처럼 협업합니다.**

당신은 CEO다. AI 직원에게 직접 지시하거나(MANUAL), AUTO 로 맡기면
오케스트레이터가 기획부터 검수까지 끝까지 돌린다.

```
CEO ─▶ AUTO ─▶ 전략가 ─▶ 분석가(테스트 선작성) ─▶ 개발자/작가/디자이너
                                                      │
                          pytest ◀───────────────────┘
                            │
                            ▼
                      분석가 교차검증 ──반려──▶ 재작업
                            │통과
                            ▼
                      전략가 최종검수 ─▶ 산출물
```

---

## 지금 상태 — 정직하게

**DAY 26.** 전 구간이 돈다. 다만 **Mock 으로** 돈다 — 그리고 DAY 25 부터는
세 회사의 프로토콜을 흉내 내는 로컬 서버 위에서 **실제 SDK 로도** 돈다.

| | 상태 |
|---|---|
| AUTO · MANUAL 전 구간 | ✅ 기획→테스트→구현→검증→재작업→검수 |
| AI 직원 5명 · 권한 경계 | ✅ 코드로 강제 |
| 제공자 3사 + Mock | ✅ 교체는 설정 한 줄 |
| 화면 (사무실·프로젝트·요금제·설정) | ✅ |
| 사무실 — 부서·회의실·대표실·비서실 | ✅ 직원 상태 5종 + 이유 한 줄 · 하루 시나리오 12단계 (DAY 25) · 직원을 끌어 다른 팀에 배치 (DAY 26) |
| 대표 승인 지점 · 대표 지시창 | ✅ 승인·수정 요청·보류·폐기 · "왜 늦어져?" 는 병목 하나만 (DAY 25) |
| 태스크 병렬 실행 · 프로젝트별 권한 · 시간 지표 | ✅ 같은 직원도 파일이 안 겹치면 동시에 — 파일 예약 (DAY 25 · 26) |
| 여러 Claude 세션 조정 | ✅ 다른 세션이 잡은 파일은 편집·셸 명령·커밋에서 막힌다 (`scripts/claims.py` · DAY 26) |
| 크레딧 · 요금제 · 원가(§17) | ✅ 공식 단가와 대조 · 원가 비율 35% 이하 |
| 요금제 4종 · 자체 키(BYOK) | ✅ 무료 없음 — 결제해야 쓴다 |
| 인증 · 테넌트 분리 | ✅ 이메일+비밀번호. 계정별로 완전히 갈린다 |
| 컨테이너 배포 | ⚠️ 파일은 있지만 docker 가 없어 검증 못 함 |
| 자체 테스트 | **873 통과 / 25 보류** · 화면 시험(Playwright) **37 통과** |
| **실제 모델 완주** | ❌ **키가 없다** |

보류된 15개는 실제 제공자의 **계약 테스트**다. Mock 과 똑같은 계약이
걸려 있고 키가 없어서 skip 된다. 키를 넣는 순간 자동으로 걸린다. 나머지
보류 10개는 돈이 드는 실물 통합 시험이라 `LIVE_PROVIDER_TESTS=1` 로 켜야 돈다.

마지막 줄이 이 프로젝트의 최대 리스크다. 자세한 것은 [STATUS.md](STATUS.md).

---

## 실행

키가 없어도 뜬다. 없으면 Mock 직원이 일하고, 화면 곳곳에 `MOCK` 배지가
붙는다 — 대본을 결과물로 착각하지 않도록.

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

`http://localhost:3000` — `/api` 는 백엔드(8000)로 넘어간다.
단, `/api/stream` 만은 전용 라우트가 가로챈다: Next 의 rewrite 가 SSE 를
버퍼링해서 이벤트가 하나도 안 온다(DAY 8~10 에 실제로 겪었다).

**테스트**

```bash
.venv/Scripts/python.exe -m pytest -q
```

**화면 시험** (Playwright · DAY 26) — 켜둔 개발 서버와 데이터는 건드리지 않는다.
시험용 백엔드(8765 · Mock · 임시 폴더)와 프론트(3765 · `.next-e2e`)를 따로 띄운다.

```bash
cd frontend && npx playwright install chromium && npm run test:e2e
```

브라우저를 받기 싫으면 설치된 것을 쓴다: `PW_CHANNEL=msedge npm run test:e2e`.

---

## 키를 넣으면

```bash
# 1. 점검 — 실제 호출 없이 설정만 본다
curl localhost:8000/api/preflight

# 2. 최초 실물 호출 — 제공자별 1번씩. 싸다
python scripts/first_real_run.py

# 3. 보류됐던 계약 테스트 15개가 자동으로 걸린다
.venv/Scripts/python.exe -m pytest backend/tests/test_providers.py -q

# 4. 직원 설정 그대로 · JSON 계약 · 캐시 — 몇 센트 (full 이면 프로젝트 한 건, 상한 $0.50)
LIVE_PROVIDER_TESTS=1 .venv/Scripts/python.exe -m pytest backend/tests/test_live_providers.py -q
```

설정 화면(`/settings`)에서 등록해도 되고, 그쪽이 더 안전하다 —
환경변수로 넣으면 브로커가 기동 즉시 꺼내서 `os.environ` 에서 지운다.

---

## 구조

```
ai-company/
├── frontend/                Next.js 16 · TypeScript · Tailwind 4
│   └── src/
│       ├── app/             사무실 · 프로젝트 · MANUAL · 요금제 · 설정
│       ├── components/      랜딩 · 흐름 도형 · 아이콘 · 공용 UI
│       ├── lib/motion.ts    움직임 한 곳 (anime.js v4 · DAY 20)
│       └── lib/i18n.tsx     한국어 · English · 日本語 (DAY 20, 절반)
│       ├── components/      Office · ChatLog · TaskBoard · FileViewer
│       └── lib/             api · useStream(SSE) · useLoader
├── backend/
│   ├── run.py               실행 진입점
│   ├── pricing.json         단가·크레딧·요금제 (코드 밖, §14 §16)
│   ├── models.json          모델 카탈로그 (코드 밖, §7)
│   ├── app/
│   │   ├── main.py          FastAPI 앱
│   │   ├── deploy.py        배포 자세 — local / saas (DAY 13)
│   │   ├── tenant.py        요금제 → 누구의 키로 부를까 (DAY 19)
│   │   ├── byok.py          고객이 맡긴 키 (암호화 보관, DAY 19)
│   │   ├── auth/            로그인 · 세션 · 테넌트 분리 (DAY 15)
│   │   ├── api/             라우터 — auth · local_tools(이전 제품)
│   │   ├── preflight.py     출항 전 점검 (DAY 14)
│   │   ├── bus.py           이벤트 버스 → SSE (§13)
│   │   ├── providers/       AI 제공자 어댑터 (§7) ← 모델 교체 지점
│   │   ├── agents/          직원 5명 · 계약 스키마 · JSON 파서 (§8)
│   │   ├── orchestrator/    상태머신 · MANUAL · 격리 러너 (§9 §10 §11)
│   │   ├── usage/           토큰·비용·크레딧 (§14 §15)
│   │   ├── database/        프로젝트 저장 + SQLite 색인 (§12)
│   │   ├── tools/           직원별 권한이 걸린 파일 도구
│   │   └── models/          API 스키마
│   ├── legacy/              이전 설계. 참고용, 실행되지 않음
│   └── tests/               490개
├── scripts/first_real_run.py
├── docker-compose.yml       배포 (미검증 — docker 가 이 머신에 없다)
└── docs/
    ├── architecture.md      재사용 지도
    ├── deploy.md            도메인 사기 전에 읽을 것
    └── security.md          막는 것과 **막지 못하는 것**
```

`§` 는 개발 지시서의 항목 번호다.

---

## 이 제품의 몇 가지 결정

**검증자는 다른 회사 모델이다.** 구현이 Claude 면 검증은 Gemini 다.
같은 회사 모델끼리 검토하면 학습 분포가 같아 **같은 실수를 함께 놓친다.**
대체 사슬도 회사를 건너게 걸었고, 검증자의 대체에 Claude 를 두지 않는다 —
그러면 교차검증 전제가 조용히 사라진다. 그건 "느리게라도 돌아감"이
아니라 "검증한 척"이다.

**테스트를 구현보다 먼저 쓴다.** 검증자가 인수기준으로 테스트를 쓰고,
구현자는 `tests/` 를 **읽지도 못한다.** 읽을 수 있으면 테스트를 통과시키는
코드를 쓰게 되고, 그건 인수기준을 만족시키는 것과 다르다.

**검증자는 담당자의 설명을 보지 않는다.** 산출물 원문과 기준만 본다.
자기 합리화에 오염되면 교차검증이 형식만 남는다.

**순서는 코드가 정한다.** LLM 라우터는 "왜 저 직원을 불렀나"에 답할 수
없고 무한 루프에서 멈출 방법이 없다. AUTO 에서 모델이 고르는 것은
태스크별 담당자 하나뿐이고, 그것도 검사 없이 따르지 않는다.

**비용은 호출 전에 막는다.** 사후 감지는 상한이 아니라 부고다.
다음 호출의 최악 비용을 미리 더해서 넘으면 그 자리에서 멈춘다.

**무료 요금제가 없다.** Mock 전용 무료도 두지 않는다 — 가입한 사람이 받는
것이 대본이 지어낸 산출물이고, 그건 체험이 아니라 오해를 파는 것이다.
데모는 로그인 이전에 보여주고, 계정을 만든 사람에게는 진짜만 준다.

**요금제가 누구의 키로 부를지를 정한다.** 자체 키(BYOK) 고객은 자기 키로만
돌고, 유료는 운영자 키로 돌며 그 비용만 크레딧에서 깎인다. 이 분기는 `app/tenant.py` **한 곳**에 있다.
퍼뜨리면 한 군데만 빠뜨려도 결제하지 않은 사람이 우리 키를 태우거나
BYOK 고객의 요금을 우리가 낸다 — 둘 다 조용히 일어나고 청구서로만 드러난다.

**BYOK 에서 키가 없으면 멈춘다.** 운영자 키로 대신 부르지 않는다(할인
요금제를 판 자리에서 우리가 모델 값을 내게 된다). Mock 으로 떨어지지도
않는다(대본이 지어낸 글이 고객의 AI 결과물이 된다). 차라리 시작을 거부한다.

**Mock 을 숨기지 않는다.** 전용 색과 배지를 두고 어디에도 재사용하지
않는다. 예쁜 화면을 위해 이걸 빼면 아무도 진짜와 대본을 구분하지 못한다.

---

## 이 저장소의 이전 이력

여기에는 원래 **다른 제품**이 있었다 — Claude Code 형태의 로컬 개발도구.
AI COMPANY 는 그 위에 새로 지었고, 검증된 계층(`bus` · `usage` ·
`secrets_broker` · `approvals` · 격리 러너 · 테스트)은 버리지 않았다.

다만 **전제가 바뀌었다**: 로컬 도구의 "내 컴퓨터에서 내가 쓴다"는
SaaS 에서 성립하지 않는다. 같은 코드가 서버에서 돌면 임의 명령 실행도
화면 캡처도 뜻이 달라진다. `DEPLOY_MODE=saas` 가 그 기능들을 전면
차단한다 — [docs/security.md](docs/security.md).

`backend/legacy/` 는 실행되지 않는다. 설계 기록이자 부품 창고다.
자세한 대응표는 [docs/architecture.md](docs/architecture.md).

---

## 알려진 위험

- **실제 모델로 완주해본 적이 없다.** 최대 미검증 구간.
- **컨테이너를 띄워본 적이 없다.** docker 가 이 머신에 없다.
- **비밀번호 재설정·이메일 인증·결제가 없다.**
- **여러 프로젝트를 모아 보는 대시보드는 인스턴스를 못 넘는다.** 나머지(세션·지갑·좌석·
  승인·재개·정지)는 DAY 22~26 에 옮겼다 — [docs/deploy.md](docs/deploy.md).
- **프롬프트 주입은 막지 못한다.** 줄였을 뿐이고, 진짜 방어는 구조 쪽에
  걸려 있다 — 설득당한 직원도 권한 밖 파일은 못 쓴다.
- **docker 로 검증하지 못했다.** PostgreSQL 이전도 실제로 해보지 않았다 —
  다만 "고칠 곳이 몇 군데인가"는 이제 테스트가 지킨다.

전부 [STATUS.md](STATUS.md) 와 [docs/security.md](docs/security.md) 에
근거와 함께 적혀 있다.
