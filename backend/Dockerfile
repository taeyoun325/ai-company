# AI COMPANY 백엔드 (DAY 16).
#
# ## 이 이미지가 특별한 이유
#
# 여기서 **모델이 쓴 코드를 실제로 실행한다**(pytest). 그래서 보통의
# 파이썬 서비스 이미지보다 조심할 것이 많다:
#
#   - 루트로 돌지 않는다
#   - util-linux 를 넣는다 — `unshare` 로 생성된 코드의 네트워크를 끊는다
#     (app/orchestrator/isolation.py). 없으면 격리가 조용히 꺼진다
#   - 화면 캡처 의존성(pillow·pyautogui)을 넣지 않는다. 서버에는 화면이
#     없고, saas 모드에서 그 기능은 어차피 403 이다
#
# 빌드: docker build -f backend/Dockerfile -t ai-company-backend .
# (컨텍스트는 저장소 루트다 — pricing.json·models.json 이 backend/ 안에 있지만
#  런타임 산출물 경로가 루트 기준이라 둘 다 필요하다)

FROM python:3.13-slim AS base

# PYTHONDONTWRITEBYTECODE: 읽기 전용 파일시스템에서도 돌 수 있게
# PYTHONUNBUFFERED: 로그가 버퍼에 갇혀 컨테이너 로그에 늦게 뜨지 않게
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# unshare(util-linux) 는 생성된 코드의 네트워크를 끊는 데 쓴다.
# 이게 없으면 isolation.probe() 가 실패하고, 실패 사실이 리포트에 남는다.
RUN apt-get update \
 && apt-get install -y --no-install-recommends util-linux \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성을 먼저 복사한다. 소스가 바뀔 때마다 pip install 을 다시 하지 않게.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ backend/

# 루트로 돌지 않는다. 생성된 코드가 이 사용자 권한을 그대로 갖는다.
RUN useradd --create-home --uid 10001 company \
 && mkdir -p /app/projects /app/logs \
 && chown -R company:company /app
USER company

# 산출물·로그·DB 는 볼륨으로 뺀다. 컨테이너를 갈아끼워도 남아야 한다.
# ai_company_auth.db(계정)는 **지우면 복구할 방법이 없다** — 백업 대상이다.
VOLUME ["/app/projects", "/app/logs"]

EXPOSE 8000

# 서버 배포의 기본값. compose 나 실행 시 덮어쓸 수 있다.
ENV DEPLOY_MODE=saas \
    PROVIDER_MODE=real \
    RUNNER_ISOLATE_NETWORK=1

# 헬스체크는 인증이 필요 없는 경로여야 한다. /api/state 는 401 이다.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/deploy', timeout=4).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--app-dir", "backend", "--proxy-headers", "--forwarded-allow-ips", "*"]
