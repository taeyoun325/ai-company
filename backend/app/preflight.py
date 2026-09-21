"""출항 전 점검 (지시서 §18, DAY 14).

## 이 파일이 존재하는 이유

이 제품의 최대 리스크는 처음부터 하나였다: **실제 모델로 한 번도 돌려본
적이 없다.** 방침("키는 제작을 마친 뒤 맨 마지막에")의 대가이고, 이전
팀도 같은 순서로 가서 같은 자리에 빠졌다.

그 대가를 줄이려고 구조를 이렇게 짰다 — Mock 과 실제가 같은 계약 테스트를
통과하고, 교체는 설정 한 줄. 하지만 **구조가 맞다는 것과 실제로 도는
것은 다르다.** 그 간극을 건너는 날이 오늘이고, 이 파일이 그 다리다.

## 점검은 판정이 아니라 목록이다

"준비됨 / 안 됨" 한 글자로 답하지 않는다. 무엇이 준비됐고 무엇이 아직인지
줄 단위로 내놓는다. 한 글자로 답하면, 아닌 이유를 찾으려고 로그를 뒤져야
한다.

## 호출은 하지 않는다

여기서는 **설정과 상태만** 본다. 실제 모델을 부르는 것은
`scripts/first_real_run.py` 의 일이다. 점검이 돈을 쓰면 아무도 자주
돌리지 않는다.
"""
from __future__ import annotations

from app import config, deploy, secrets_broker
from app.agents import roles
from app.providers import registry
from app.usage import credits

OK, WARN, FAIL = "ok", "warn", "fail"


def _row(name: str, level: str, detail: str, fix: str = "") -> dict:
    return {"check": name, "level": level, "detail": detail, "fix": fix}


def checks(strict: bool = False) -> list[dict]:
    """`strict` 는 "지금 배포한다"는 뜻. 경고 중 일부가 실패로 승격된다."""
    out: list[dict] = []
    st = registry.status()

    # ── 키와 제공자 ────────────────────────────────────────────────
    missing = secrets_broker.missing()
    if missing:
        out.append(_row(
            "API 키", FAIL if strict else WARN,
            f"없는 키: {', '.join(missing)}. 지금은 Mock 으로 돕니다.",
            "설정 화면에서 등록하거나 환경변수로 넣으세요."))
    else:
        out.append(_row("API 키", OK, "필수 키가 모두 있습니다."))

    if st["all_mock"]:
        out.append(_row(
            "제공자", FAIL if strict else WARN,
            "모든 직원이 Mock 으로 일합니다. 산출물은 실제 AI 의 작업 결과가 "
            "아닙니다.",
            "키를 넣거나 PROVIDER_MODE 를 확인하세요."))
    elif not st["cross_check"]:
        out.append(_row(
            "교차검증", FAIL if strict else WARN,
            "구현자와 검증자가 서로 다른 회사가 아닙니다. 같은 모델은 같은 "
            "실수를 함께 놓칩니다 — 검증이 형식만 남습니다.",
            "Anthropic 과 Google 키를 **둘 다** 넣으세요."))
    else:
        out.append(_row("제공자", OK,
                        f"실제 제공자로 동작 중 (모드 {st['mode']})."))

    if registry.mode() == "auto" and deploy.is_saas():
        out.append(_row(
            "PROVIDER_MODE", FAIL,
            "배포(saas)인데 auto 입니다. 키 설정이 빠지면 조용히 Mock 이 돌고 "
            "가짜 결과물이 진짜처럼 나갑니다.",
            "PROVIDER_MODE=real 로 두세요."))

    # ── 계약 검증 여부 ─────────────────────────────────────────────
    unverified = [p["name"] for p in st["providers"] if not p["key"]]
    if unverified:
        out.append(_row(
            "제공자 계약 테스트", WARN,
            f"키가 없어 계약이 아직 검증되지 않은 제공자: "
            f"{', '.join(unverified)}. 해당 테스트는 skip 으로 남아 있습니다.",
            "키를 넣고 `pytest backend/tests/test_providers.py` 를 돌리세요."))
    else:
        out.append(_row("제공자 계약 테스트", OK,
                        "모든 제공자에 키가 있어 계약 테스트가 실제로 걸립니다."))

    # ── 모델과 단가 ────────────────────────────────────────────────
    unpriced = [f"{e.id}:{e.model}" for e in roles.EMPLOYEES.values()
                if not config.is_priced(e.model)]
    if unpriced:
        out.append(_row(
            "단가", FAIL,
            f"단가를 모르는 모델로 일하려 합니다: {', '.join(unpriced)}. "
            f"비용이 0 으로 잡히면 예산 상한이 걸리지 않습니다.",
            "pricing.json 에 단가를 등록하세요."))
    elif not config.PRICES_VERIFIED:
        out.append(_row(
            "단가", WARN,
            "단가가 공식 문서와 대조되지 않았습니다. 원가와 마진은 추측입니다.",
            "pricing.json 의 값을 대조하고 verified 를 올리세요."))
    else:
        out.append(_row("단가", OK,
                        f"공식 단가와 대조됨 ({config.PRICES_VERIFIED_ON})."))

    # ── 원가 (§17) ─────────────────────────────────────────────────
    margin = credits.margin_report()
    if not margin["all_paid_plans_ok"]:
        bad = [p["plan"] for p in margin["plans"] if p["price_usd"] > 0 and not p["ok"]]
        out.append(_row(
            "원가 비율(§17)", FAIL,
            f"원가가 판매가의 {int(credits.MAX_COST_RATIO * 100)}% 를 넘는 "
            f"요금제: {', '.join(bad)}",
            "요금제의 크레딧을 줄이거나 가격을 올리세요."))
    else:
        out.append(_row("원가 비율(§17)", OK,
                        "유료 요금제가 모두 기준을 만족합니다."))

    # ── 안전장치 (§18) ─────────────────────────────────────────────
    guards = {"MAX_ROUNDS": config.MAX_ROUNDS, "MAX_REWORK": config.MAX_REWORK,
              "MAX_REPLANS": config.MAX_REPLANS, "MAX_RETRY": config.MAX_RETRY,
              "MAX_PROJECT_COST": config.MAX_PROJECT_COST}
    zeroed = [k for k, v in guards.items() if not v and k != "MAX_REPLANS"]
    if zeroed:
        out.append(_row(
            "안전장치", FAIL,
            f"상한이 0 입니다: {', '.join(zeroed)}. 무한 루프를 막을 수 없습니다.",
            ".env 를 확인하세요."))
    else:
        out.append(_row("안전장치", OK,
                        f"라운드 {config.MAX_ROUNDS} · 재작업 {config.MAX_REWORK} · "
                        f"재시도 {config.MAX_RETRY} · 프로젝트 상한 "
                        f"${config.MAX_PROJECT_COST}"))

    # ── 계정 (DAY 15) ──────────────────────────────────────────────
    if deploy.is_saas():
        try:
            from app.auth import store as auth_store
            n_users = auth_store.user_count()
        except Exception as e:                        # noqa: BLE001
            out.append(_row("계정 저장소", FAIL,
                            f"계정 DB 를 열지 못했습니다: {e}",
                            "ai_company_auth.db 의 권한과 경로를 확인하세요."))
            n_users = -1
        if n_users == 0:
            out.append(_row(
                "계정", WARN,
                "계정이 하나도 없습니다. 지금 이 주소를 찾은 **아무나** 첫 "
                "사용자가 됩니다.",
                "배포 직후 바로 본인 계정을 만드세요."))
        elif n_users > 0:
            out.append(_row("계정", OK, f"{n_users}개"))
    else:
        out.append(_row("계정", OK,
                        "로컬 모드 — 로그인 없이 'local' 사용자로 동작합니다."))

    # ── 메일 (DAY 22) ──────────────────────────────────────────────
    # 파는 제품에서 비밀번호를 잊은 사람이 돌아올 길이 있어야 한다.
    if deploy.is_saas():
        from app.auth import mail
        if not mail.configured():
            out.append(_row(
                "메일", WARN,
                "SMTP_URL 이 없습니다. 비밀번호 재설정과 이메일 확인 메일이 "
                "나가지 않고 서버 로그에만 남습니다 — 비밀번호를 잊은 "
                "사용자는 돌아올 방법이 없습니다.",
                "SMTP_URL 을 설정하세요. 화면은 메일이 나가지 않았다는 "
                "사실을 사용자에게 그대로 알립니다."))
        elif not os.getenv("PUBLIC_URL", "").strip():
            out.append(_row(
                "메일 링크", WARN,
                f"PUBLIC_URL 이 없어 메일 속 링크가 {mail.public_url()} 을 "
                f"가리킵니다. 받는 사람은 그 주소를 열 수 없습니다.",
                "PUBLIC_URL 에 실제 서비스 주소를 넣으세요."))
        else:
            out.append(_row("메일", OK, f"SMTP 설정됨 · 링크 {mail.public_url()}"))

    # ── 고객 키 보관 (BYOK · DAY 19) ───────────────────────────────
    # 파는 제품에서 남의 키를 맡아두는 일이다. 운영자가 이 한 줄을
    # 빠뜨렸다는 사실이 고객에게만 보이고 운영자에게 안 보이면 안 된다.
    if deploy.is_saas():
        from app import byok
        if byok.kek_from_env():
            out.append(_row("고객 키 보관", OK,
                            "BYOK_SECRET 이 환경에 있습니다."))
        else:
            out.append(_row(
                "고객 키 보관", WARN,
                "BYOK_SECRET 이 없습니다. 고객이 등록한 API 키의 암호화 키가 "
                "같은 서버의 파일에 있게 되고, 디스크를 가져간 사람은 고객 "
                "키도 가져갑니다.",
                "BYOK_SECRET 을 환경변수로 설정하세요. 나중에 바꾸면 이미 "
                "저장된 고객 키는 복호화되지 않습니다."))

    # ── 배포 자세 (DAY 13) ─────────────────────────────────────────
    d = deploy.status()
    if d["mode"] == "local" and strict:
        out.append(_row(
            "배포 자세", FAIL,
            "DEPLOY_MODE 가 local 입니다. 서버에서 로컬 접근 기능(임의 명령 "
            "실행·폴더 열기·화면 캡처)이 열려 있습니다.",
            "DEPLOY_MODE=saas 로 두세요. docs/security.md 참조."))
    elif d["mode"] == "saas":
        out.append(_row(
            "HTTPS", WARN,
            "세션 쿠키는 https 로 와야 `Secure` 가 붙습니다. 앞단 프록시가 "
            "TLS 를 끊는다면 `X-Forwarded-Proto: https` 를 넘기세요.",
            "이 값이 없으면 세션이 평문으로 오갈 수 있습니다."))
    if d["mode"] == "saas" and not d["sandboxed"]:
        out.append(_row(
            "샌드박스", WARN,
            "격리 선언이 없어 생성된 코드를 실행하지 않습니다. 검증자는 "
            "'테스트 없음'을 근거로 판정하게 됩니다.",
            "컨테이너에 네트워크·자원 제한을 건 뒤 SANDBOXED=1."))
    else:
        out.append(_row("배포 자세", OK,
                        f"{d['mode']}"
                        + (" · 격리 선언 있음" if d["sandboxed"] else "")))

    return out


def report(strict: bool = False) -> dict:
    rows = checks(strict)
    fails = [r for r in rows if r["level"] == FAIL]
    warns = [r for r in rows if r["level"] == WARN]
    return {
        "strict": strict,
        "ready": not fails,
        "checks": rows,
        "fail_count": len(fails),
        "warn_count": len(warns),
        # 이 한 줄이 이 제품의 최대 리스크다. 사라지면 안 된다.
        "real_model_calls": "키가 있는 제공자로 실제 호출한 기록은 "
                            "scripts/first_real_run.py 로 확인하세요.",
    }
