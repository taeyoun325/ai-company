# 배포 — 도메인 사기 전에 읽을 것

DAY 16 산출물.

> **이 문서의 내용은 실행으로 검증되지 않았다.** 이 개발 머신에 docker 가
> 없다(DAY 1·16 확인). Dockerfile 과 compose 는 의도를 맞춰 썼지만
> **한 번도 뜬 적이 없다.** 처음 올릴 때는 실패를 예상하고
> `docker compose logs -f` 를 보면서 할 것.

---

## 0. 순서

도메인부터 사고 싶겠지만, 순서가 거꾸로면 **가입할 수 없는 제품**을
홍보하게 된다.

1. 컨테이너로 한 번 띄워본다 (아래 1절)
2. 키를 넣고 실물 호출을 확인한다 (`scripts/first_real_run.py`)
3. 도메인 + TLS
4. 그다음 랜딩 사이트

---

## 1. 띄우기

```bash
cp .env.example .env     # 키를 채운다
docker compose up -d --build
docker compose logs -f
```

`http://localhost:3000` 이 뜨면 된다. 첫 화면은 **가입**이다 —
`DEPLOY_MODE=saas` 라서 로그인 없이는 아무것도 보이지 않는다.

### 올리자마자 할 일

**바로 본인 계정을 만든다.** 계정이 0개인 동안에는 그 주소를 찾은
아무나 첫 사용자가 된다. 화면에도 "이 서버의 첫 계정입니다"라고 뜨고,
`/api/preflight` 가 경고로 잡는다.

---

## 2. 상태가 사는 곳

| 볼륨 | 내용 | 잃으면 |
|---|---|---|
| `data` | **계정 DB**, 색인 DB, 지갑, 저장된 키 | **복구 불가.** 계정이 전부 사라진다 |
| `projects` | 산출물 파일 | 만든 것이 사라진다 |
| `logs` | 실행 트레이스 | 기록만 사라진다 |

백업은 `data` 와 `projects` 다. 색인(`ai_company.db`)은 지워도
`POST /api/projects/reindex` 로 파일에서 다시 만든다 — 하지만
계정 DB(`ai_company_auth.db`)는 다시 만들 방법이 없다.

---

## 3. 생성된 코드를 어디서 돌리나

**이게 이 배포에서 가장 조심할 부분이다.** 백엔드는 모델을 부르려고
바깥 네트워크가 필요하고, 같은 컨테이너에서 모델이 쓴 코드도 돈다.
컨테이너 수준에서는 둘을 갈라놓을 수 없다.

지금 하는 것:

- **프로세스 수준 네트워크 차단** — `unshare --net` 으로 pytest 자식에게
  빈 네트워크를 준다(`app/orchestrator/isolation.py`). 리눅스 전용이고,
  커널이 비특권 네임스페이스를 막아두면 안 된다
- 되는지 여부가 **테스트 리포트에 실린다**(`network_isolated`). 안 되면
  안 된다고 적힌다 — 막았다고 믿게 만드는 것이 안 막는 것보다 나쁘다
- 루트로 돌지 않는다 (uid 10001)
- CPU · 메모리 · 프로세스 수 제한

compose 가 `cap_add: SYS_ADMIN` 과 `seccomp:unconfined` 를 주는 이유가
네임스페이스 때문이다. 이게 싫다면 두 줄을 지워라 — 격리가 꺼지고
리포트에 "커널이 거부했습니다"가 찍힌다. **조용히 꺼지지는 않는다.**

### 제대로 하려면

실행 전용 서비스를 따로 두고 `network_mode: none` 을 걸어야 한다.
오케스트레이터가 테스트 실행을 다른 컨테이너로 넘기는 구조 변경이라
아직 하지 않았다. 그때까지는 위의 한 겹이 전부다.

---

## 4. TLS 가 없으면 세션이 샌다

세션 쿠키는 https 로 와야 `Secure` 가 붙는다. 앞단에서 TLS 를 끊는다면
**`X-Forwarded-Proto: https` 를 넘길 것.** 이 값이 없으면 앱은 평문
연결로 판단하고 `Secure` 를 붙이지 않는다.

Caddy 예시 (TLS 자동):

```
ai-company.example.com {
    reverse_proxy frontend:3000
}
```

nginx 라면 `proxy_set_header X-Forwarded-Proto $scheme;` 를 꼭 넣는다.

백엔드는 `--proxy-headers --forwarded-allow-ips "*"` 로 돈다. 프록시 뒤에
있다는 전제이므로, **프록시 없이 백엔드를 직접 노출하면 안 된다** —
`X-Forwarded-For` 를 공격자가 마음대로 적을 수 있고, 로그인 횟수 제한이
그 값을 믿는다.

---

## 5. 올리기 전 점검

```bash
curl https://your-domain/api/preflight?strict=true
```

`ready: false` 면 무엇이 막고 있는지 줄 단위로 나온다. 실제 모델을
부르지 않으므로 돈이 들지 않는다.

주요 항목:

| 점검 | 통과 조건 |
|---|---|
| API 키 | anthropic · gemini 둘 다 (교차검증 전제) |
| PROVIDER_MODE | `real` — `auto` 는 조용히 Mock 으로 떨어진다 |
| 배포 자세 | `DEPLOY_MODE=saas` |
| 계정 | 1개 이상 |
| 단가 | 검증됨 |
| 원가 비율 | 유료 요금제 **35% 이하** (`credits.MAX_COST_RATIO`) |
| 메일 | `SMTP_URL` · `PUBLIC_URL` · 평문 SMTP 경고 |
| 고객 키 보관 | `BYOK_SECRET` 이 환경변수에 있는가 |

---

## 6. 아직 없는 것

- **결제** — 크레딧은 실제로 줄지만 충전은 데모 버튼이다
- **PostgreSQL 이전** — SQL 은 표준으로 썼지만 실제로 옮겨보지 않았다.
  `docker compose --profile postgres up -d db` 로 DB 만 띄울 수는 있다
- **다중 인스턴스** — 아래 참조

### 비밀번호 재설정 · 이메일 인증은 **구조가 끝났다** (DAY 22)

이 문서는 "발송 경로를 붙이지 않았다"고 적고 있었지만 그건 DAY 16 의
사실이다. 지금은 `SMTP_URL` 한 줄이면 나간다:

- 없으면 메일이 **나가지 않고** 서버 로그에만 남는다. 화면과 프리플라이트가
  그 사실을 그대로 말한다(`delivered=False`).
- 남의 기계에 평문 `smtp://` 로 설정하면 서버가 STARTTLS 를 안 내밀 때
  **발송을 거절한다** — 메일 본문에 재설정 링크가 들어 있기 때문이다.
  프리플라이트가 그 조건을 미리 경고한다.
- 실제 SMTP 서버에 붙여본 적은 없지만, 프로토콜 대화는 가짜 서버를 띄워
  확인했다(`backend/tests/test_mail_smtp.py`).

### 다중 인스턴스 — **무엇이 남았는지** (DAY 22 갱신)

"세션·크레딧·실행 상태가 프로세스 메모리에 있다"는 것도 옛말이다. 지금
메모리에 남은 것은 셋뿐이다:

| 무엇 | 어디 | 두 대로 띄우면 |
|---|---|---|
| 세션 | SQLite (`sessions` 테이블) | 문제 없음 |
| 크레딧 지갑 | SQLite (`wallets`) | 문제 없음 |
| 실행 스레드 목록 (`engine._runs`) | 메모리 | 동시 실행 한도가 **인스턴스마다** 따로 세진다 |
| MANUAL 점유 (`manual._busy`) | 메모리 | 같은 프로젝트에 두 사람이 동시에 지시할 수 있다 |
| 로그인 실패 횟수 (`service._buckets`) | 메모리 | 잠금이 인스턴스마다 따로 세져 실질 한도가 N 배가 된다 |

마지막 줄이 보안 쪽이라 제일 중요하다. **지금은 인스턴스 하나로만
돌려야 한다.**
