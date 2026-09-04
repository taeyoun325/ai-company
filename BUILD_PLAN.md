# AI 에이전트 컴퍼니 — 제작 개요

> 범용 소프트웨어 개발사 / Python + API 직접 호출 / PM–개발–검증 3인 체제

---

## 0. 한 줄 요약

요구사항 한 문장을 넣으면 **PM(Claude)** 이 작업 그래프를 짜고, **개발자(Claude)** 가 파일을 실제로 쓰고,
**검증자(Gemini)** 가 독립적으로 반려/승인하는 루프를 돌려 **동작하는 코드 + 테스트 + 보고서**를 뱉는 파이썬 프로그램.

---

## 1. 설계 원칙 (이게 제일 중요)

| 원칙 | 내용 | 왜 |
|---|---|---|
| **오케스트레이터는 코드다** | 누가 다음에 말할지는 LLM이 아니라 파이썬 상태머신이 결정 | LLM 라우터는 디버깅이 지옥. 대회 시연 중 무한루프 나면 끝 |
| **에이전트 간 대화는 JSON** | 자연어 채팅이 아니라 스키마 고정된 구조화 출력 | 파싱 실패·토큰 낭비·"동문서방" 제거 |
| **공유 메모리는 파일시스템** | 대화 히스토리를 서로 안 넘김. `workspace/` 와 `state.json`이 진실 | 컨텍스트 폭발 방지. 3명이 각자 필요한 것만 읽음 |
| **검증자는 다른 회사 모델** | Claude 2명 + Gemini 1명인 이유가 바로 이것 | 같은 모델끼리는 **같은 실수를 같이 놓친다**(상관된 맹점). 이종 모델 교차검증이 이 프로젝트의 핵심 논리 |
| **모든 턴을 기록** | JSONL 트레이스 + 비용 누적 | 발표할 때 "이렇게 협업했습니다"를 보여줄 증거물 |
| **하드 스톱** | 라운드 상한, 토큰 상한, 달러 상한 3중 | 무한 재작업 루프 = 지갑 화재 |

---

## 2. 조직도

```
                    ┌──────────────────────────┐
   요구사항 ───────▶│  Orchestrator (Python)   │◀──── 예산·라운드 감시
                    │   상태머신 + 이벤트 버스  │
                    └───┬────────┬─────────┬───┘
                        │        │         │
              ┌─────────▼──┐ ┌───▼──────┐ ┌▼───────────┐
              │  PM        │ │ DEV      │ │ QA         │
              │ claude-    │ │ claude-  │ │ Gemini     │
              │ opus-5     │ │ opus-5   │ │ (google-   │
              │ effort:高  │ │ +툴러너  │ │  genai)    │
              │            │ │ 파일쓰기 │ │ 읽기전용   │
              └─────┬──────┘ └────┬─────┘ └─────┬──────┘
                    │             │             │
                    └─────────────┼─────────────┘
                                  ▼
                    workspace/  ·  state.json  ·  trace.jsonl
```

### 2.1 역할 카드

**PM — `claude-opus-5`, `effort: "high"`, 툴 없음(순수 추론)**
- 입력: 사용자 요구사항 + 현재 `state.json`
- 출력(JSON): `{ project_name, acceptance_criteria[], tasks[{id, title, deps[], files[], done_when}] }`
- 재호출 시점: ① 최초 기획 ② QA가 3회 연속 반려했을 때 "계획 자체가 틀렸나" 재판단 ③ 최종 승인
- 파일 쓰기 권한 **없음** — 계획만 세운다

**DEV — `claude-opus-5`, `effort: "xhigh"`, Tool Runner + 파일 툴**
- 입력: 태스크 1개 + 관련 파일 내용 + (있다면) QA 반려 사유
- 툴: `read_file`, `write_file`, `list_files`, `run_tests`(샌드박스된 pytest만)
- 출력(JSON): `{ task_id, changed_files[], summary, self_check }`
- 한 번에 **태스크 1개만**. 여러 개 몰아주면 품질이 무너짐

**QA — Gemini (`gemini-2.5-pro` 계열, `google-genai` SDK), 읽기 전용**
- 입력: 태스크 정의 + `acceptance_criteria` + 변경된 파일 **원문** + 테스트 실행 결과
- 출력(JSON): `{ verdict: "pass"|"fail", severity, findings[{file, line, issue, why}], required_fixes[] }`
- **DEV의 설명을 안 읽는다.** 코드 원문과 기준만 본다 → DEV의 자기 합리화에 오염되지 않음
- 테스트는 QA가 직접 실행하지 않고 오케스트레이터가 돌린 결과를 넘겨줌(권한 분리)

---

## 3. 실행 흐름 (상태머신)

```
INIT
 └▶ PLAN        PM 호출 → tasks[] 확정 → state.json 저장
     └▶ 태스크 큐에서 deps 충족된 것 하나 pop
         └▶ IMPLEMENT   DEV 호출 → 파일 변경
             └▶ TEST     오케스트레이터가 pytest 실행 (LLM 아님)
                 └▶ REVIEW   QA 호출 (코드 + 테스트결과)
                     ├─ pass → 태스크 완료 표시 → 다음 태스크
                     └─ fail → rework_count += 1
                          ├─ < 3 : IMPLEMENT 로 (반려사유 첨부)
                          └─ = 3 : REPLAN (PM 재호출) → 태스크 쪼개기
 └▶ 큐 비면 FINALIZE  PM이 acceptance_criteria 전체 대조 → 최종 보고서
 └▶ DONE
```

**정지 조건 (OR)**: 태스크 전부 완료 / 총 라운드 40 초과 / 누적 비용 상한 초과 / 같은 태스크 3회 REPLAN.

---

## 4. 파일 구조

```
agent-company/
├─ run.py                  # 진입점: python run.py "요구사항"
├─ orchestrator.py         # 상태머신 + 정지조건 + 비용집계
├─ agents/
│  ├─ base.py              # Agent 추상: run(payload) -> dict
│  ├─ pm.py                # Anthropic, 구조화 출력
│  ├─ dev.py               # Anthropic, tool_runner
│  └─ qa.py                # Gemini, 구조화 출력
├─ tools/
│  └─ fs.py                # read/write/list  (workspace/ 밖으로 못 나가게 경로 검사)
├─ schemas.py              # PlanSchema / DevReport / QAVerdict (pydantic)
├─ prompts/
│  ├─ pm.md  dev.md  qa.md # 시스템 프롬프트를 코드에서 분리 → 캐싱 & 튜닝 용이
├─ workspace/              # 산출물이 실제로 쌓이는 곳 (git 별도 관리)
└─ logs/
   ├─ trace.jsonl          # 전 턴 기록
   └─ cost.json            # 모델별 토큰·달러
```

---

## 5. 핵심 코드 스켈레톤

### 5.1 의존성

```bash
pip install anthropic google-genai pydantic pytest rich
```

환경변수: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`

### 5.2 스키마 (계약서 역할)

```python
# schemas.py
from pydantic import BaseModel
from typing import Literal

class Task(BaseModel):
    id: str
    title: str
    deps: list[str] = []
    files: list[str] = []
    done_when: str

class Plan(BaseModel):
    project_name: str
    acceptance_criteria: list[str]
    tasks: list[Task]

class Finding(BaseModel):
    file: str
    line: int | None = None
    issue: str
    why: str

class QAVerdict(BaseModel):
    verdict: Literal["pass", "fail"]
    severity: Literal["none", "minor", "major", "blocker"]
    findings: list[Finding] = []
    required_fixes: list[str] = []
```

### 5.3 PM — 구조화 출력 + 프롬프트 캐싱

```python
# agents/pm.py
import anthropic, json
from schemas import Plan

client = anthropic.Anthropic()
SYSTEM = open("prompts/pm.md", encoding="utf-8").read()

def plan(requirement: str, state: dict) -> Plan:
    resp = client.messages.create(
        model="claude-opus-5",
        max_tokens=16000,
        # 고정 프리픽스는 캐싱 → 재호출 때 입력비 90% 절감
        system=[{"type": "text", "text": SYSTEM,
                 "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": Plan.model_json_schema()},
        },
        messages=[{"role": "user", "content":
                   f"요구사항:\n{requirement}\n\n현재상태:\n{json.dumps(state, ensure_ascii=False)}"}],
    )
    return Plan.model_validate_json(resp.content[0].text)
```

### 5.4 DEV — Tool Runner로 에이전틱 루프

```python
# agents/dev.py
import anthropic
from anthropic import beta_tool
from tools.fs import safe_read, safe_write, safe_list

client = anthropic.Anthropic()

@beta_tool
def read_file(path: str) -> str:
    """workspace 안의 파일을 읽는다.

    Args:
        path: workspace 기준 상대경로.
    """
    return safe_read(path)

@beta_tool
def write_file(path: str, content: str) -> str:
    """workspace 안에 파일을 쓴다(덮어쓰기).

    Args:
        path: workspace 기준 상대경로.
        content: 파일 전체 내용.
    """
    safe_write(path, content)
    return f"wrote {path}"

@beta_tool
def list_files() -> str:
    """workspace의 파일 목록을 반환한다."""
    return "\n".join(safe_list())

def implement(task, feedback: str | None) -> list:
    prompt = f"태스크: {task.model_dump_json()}"
    if feedback:
        prompt += f"\n\nQA 반려 사유(반드시 전부 해결):\n{feedback}"

    runner = client.beta.messages.tool_runner(
        model="claude-opus-5",
        max_tokens=32000,
        system=[{"type": "text", "text": open("prompts/dev.md", encoding="utf-8").read(),
                 "cache_control": {"type": "ephemeral"}}],
        thinking={"type": "adaptive"},
        output_config={"effort": "xhigh"},
        tools=[read_file, write_file, list_files],
        messages=[{"role": "user", "content": prompt}],
    )
    return [m for m in runner]   # 각 턴을 trace에 기록
```

### 5.5 QA — Gemini (이종 모델 교차검증)

```python
# agents/qa.py
from google import genai
from google.genai import types
from schemas import QAVerdict

gclient = genai.Client()   # GEMINI_API_KEY

def review(task, criteria, files: dict[str, str], test_output: str) -> QAVerdict:
    body = "\n\n".join(f"### {p}\n```\n{c}\n```" for p, c in files.items())
    resp = gclient.models.generate_content(
        model="gemini-2.5-pro",
        config=types.GenerateContentConfig(
            system_instruction=open("prompts/qa.md", encoding="utf-8").read(),
            response_mime_type="application/json",
            response_schema=QAVerdict,
            temperature=0.2,
        ),
        contents=(f"태스크:\n{task.model_dump_json()}\n\n"
                  f"인수기준:\n{criteria}\n\n"
                  f"테스트 결과:\n{test_output}\n\n"
                  f"변경된 코드 원문:\n{body}"),
    )
    return QAVerdict.model_validate_json(resp.text)
```

> Gemini 모델 ID는 시점에 따라 바뀝니다. 실행 전 `gclient.models.list()`로 사용 가능한 최신 pro 계열 ID를 한 번 확인하고 상수로 박아두세요.

### 5.6 오케스트레이터 골격

```python
# orchestrator.py (핵심부만)
MAX_ROUNDS, MAX_REWORK, BUDGET_USD = 40, 3, 5.0

def run(requirement: str):
    state = {"phase": "PLAN", "done": [], "cost": 0.0}
    plan = pm.plan(requirement, state)
    queue = topo_sort(plan.tasks)
    rounds = 0

    for task in queue:
        rework = 0
        while True:
            rounds += 1
            guard(rounds, state["cost"])          # 상한 초과 시 예외로 중단

            msgs = dev.implement(task, feedback=state.get("last_feedback"))
            trace(msgs); state["cost"] += cost_of(msgs)

            test_out = run_pytest()                # 코드가 실행, LLM 아님
            files = collect_changed_files(task)
            verdict = qa.review(task, plan.acceptance_criteria, files, test_out)
            trace(verdict)

            if verdict.verdict == "pass":
                state["done"].append(task.id); state["last_feedback"] = None
                break
            rework += 1
            state["last_feedback"] = format_fixes(verdict)
            if rework >= MAX_REWORK:
                plan = pm.replan(task, verdict, state)   # 태스크 쪼개기
                queue = reinsert(queue, plan); break

    return pm.finalize(plan, state)
```

---

## 6. 프롬프트 설계 요령 (품질의 8할)

- **PM**: "너는 코드를 쓰지 않는다. 태스크는 파일 1~3개 규모로 쪼개라. `done_when`은 기계가 판정 가능한 문장이어야 한다."
- **DEV**: "한 태스크만 처리한다. 요구되지 않은 리팩터링 금지. 파일 전체를 쓸 때는 기존 내용을 먼저 읽어라."
- **QA**: "너는 DEV의 설명을 신뢰하지 않는다. 코드 원문과 인수기준만 본다. 지적할 것이 없으면 억지로 만들지 말고 pass를 내라." ← **이 마지막 문장이 없으면 QA가 영원히 트집을 잡아 루프가 안 끝납니다.**

---

## 7. 비용 설계

| 에이전트 | 모델 | 호출당 대략 | 비고 |
|---|---|---|---|
| PM | `claude-opus-5` ($5 / $25 per MTok) | 낮음 | 캐싱으로 재호출 저렴 |
| DEV | `claude-opus-5` | **최대** | 툴 루프라 턴이 많음 |
| QA | Gemini pro 계열 | 중간 | 입력은 크고 출력은 작음 |

절감 레버 (효과 순):
1. **프롬프트 캐싱** — 시스템 프롬프트 + 고정 컨텍스트에 `cache_control`. `usage.cache_read_input_tokens`가 0이면 어딘가 매 요청 바뀌는 값(타임스탬프 등)이 섞인 것.
2. **DEV에 파일 전체를 넣지 말 것** — 툴로 필요할 때만 읽게 하기.
3. **effort 튜닝** — PM은 `high`, DEV는 `xhigh`, 단순 태스크는 `medium`으로 내려 A/B.
4. 비용이 정말 문제면 DEV만 `claude-sonnet-5`($2/$10)로 내려 비교 측정. 품질 저하가 없을 때만 유지.

---

## 8. 제작 로드맵

| 단계 | 목표 | 완료 기준 |
|---|---|---|
| **D1** 뼈대 | 3개 에이전트가 각각 JSON 하나씩 반환 | 3개 스키마 검증 통과 |
| **D2** 루프 | DEV↔QA 반려 루프 1회전 성공 | fail → 재작업 → pass 로그 |
| **D3** 파일시스템 | workspace에 실제 코드 생성 | 생성된 pytest가 통과 |
| **D4** 안전장치 | 라운드·비용·경로 탈출 방지 | 상한 도달 시 정상 종료 |
| **D5** 관측 | trace.jsonl → HTML 리포트 | 협업 타임라인 시각화 |
| **D6** 데모 | "TODO REST API 만들어줘" 엔드투엔드 | 무개입 완주 |

---

## 9. 알려진 리스크와 대응

| 리스크 | 증상 | 대응 |
|---|---|---|
| QA 무한 반려 | 사소한 지적으로 계속 fail | severity 도입, `minor`는 pass로 통과시키고 백로그로 |
| DEV가 파일 날림 | write_file이 기존 내용 덮음 | 쓰기 전 자동 백업 + diff를 trace에 기록 |
| 경로 탈출 | `../../etc/passwd` | `Path.resolve()` 후 workspace 하위인지 검사 (필수) |
| JSON 파싱 실패 | 스키마 위반 | 구조화 출력 + pydantic 검증 + 1회 재시도 |
| 데모 중 API 장애 | 발표 망함 | trace 리플레이 모드(기록된 응답 재생) 준비 |

---

## 10. "왜 3명인가"에 대한 답변 (심사 대비)

1인 LLM은 **자기가 쓴 코드를 자기가 검토**하므로 실수를 못 본다.
Claude 2명으로 나눈 이유는 *역할 분리*(계획 ≠ 구현) — 컨텍스트와 권한이 달라야 각자 잘한다.
3번째를 **Gemini**로 둔 이유는 *공급자 분리* — 동일 모델은 학습 분포가 같아 같은 유형의 버그를 함께 놓친다.
이 구조는 실제 소프트웨어 회사의 기획/개발/QA 분리를 그대로 옮긴 것이며, 3인 모두 파일시스템이라는 **공유 작업물**을 통해서만 소통한다.
