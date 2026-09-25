# AI COMPANY — Cloud Run 한 컨테이너 배포 (DAY 27).
#
# compose(docker-compose.yml)는 프론트·백엔드를 두 컨테이너로 나눈다.
# Cloud Run 은 서비스마다 공개 주소가 생기므로, 그대로 나누면 **백엔드가
# 인터넷에 직접 열린다** — docs/deploy.md §4 가 금지한 배치다. 그래서
# 한 컨테이너에 넣고 백엔드는 127.0.0.1 에만 연다. 바깥에서는 Next 만 보인다.
# (폰 시험용 e2e/phone.mjs 와 같은 모양이다.)
#
# 상태: 계정·지갑·색인 SQLite 는 Litestream 이 Cloud Storage 로 계속 복제하고,
# 컨테이너가 새로 뜰 때 되살린다. 그래서 **인스턴스는 1개로 고정**한다 —
# 두 개가 같은 DB 를 복제하면 서로를 덮어쓴다. deploy/cloudrun/README.md 참조.
#
# 빌드: gcloud builds submit --config deploy/cloudrun/cloudbuild.yaml
# (컨텍스트는 저장소 루트)

# ── 1) 프론트 빌드 ─────────────────────────────────────────────────
# 실행 이미지가 glibc(debian)이므로 빌드도 glibc 에서 한다. alpine(musl)에서
# 만든 standalone 을 debian 에서 돌리면 네이티브 모듈이 깨질 수 있다.
FROM node:24-slim AS web
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# rewrite 목적지는 빌드 때 굳는다. 같은 컨테이너 안의 백엔드를 가리킨다.
ENV BACKEND_ORIGIN=http://127.0.0.1:8000
RUN npm run build

# ── 2) Litestream ─────────────────────────────────────────────────
FROM debian:bookworm-slim AS litestream
ARG LITESTREAM_VERSION=0.3.13
ADD https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-amd64.tar.gz /tmp/ls.tgz
RUN tar -xzf /tmp/ls.tgz -C /usr/local/bin litestream

# ── 3) 실행 ────────────────────────────────────────────────────────
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NEXT_TELEMETRY_DISABLED=1

# util-linux: 생성된 코드의 네트워크를 끊는 unshare (backend/Dockerfile 과 같은 이유)
RUN apt-get update \
 && apt-get install -y --no-install-recommends util-linux ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Next standalone 서버를 돌릴 node 만 가져온다 (npm·빌드 도구는 없다).
COPY --from=web /usr/local/bin/node /usr/local/bin/node
COPY --from=litestream /usr/local/bin/litestream /usr/local/bin/litestream

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ backend/

COPY --from=web /web/.next/standalone /app/web
COPY --from=web /web/.next/static /app/web/.next/static
COPY --from=web /web/public /app/web/public

COPY deploy/cloudrun/litestream.yml /etc/litestream.yml
COPY deploy/cloudrun/start.sh /app/start.sh

RUN useradd --create-home --uid 10001 company \
 && mkdir -p /app/data /app/projects /app/logs \
 && chown -R company:company /app \
 && chmod +x /app/start.sh
USER company

ENV DEPLOY_MODE=saas \
    DATA_DIR=/app/data \
    PROJECTS_DIR=/app/projects \
    LOGS_DIR=/app/logs \
    RUNNER_ISOLATE_NETWORK=1 \
    SESSION_COOKIE=__session \
    PORT=8080

EXPOSE 8080
CMD ["/app/start.sh"]
