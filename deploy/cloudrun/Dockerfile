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

# util-linux: unshare (네트워크만 끊는 옛 방식, 로컬 리눅스와 같은 경로)
# bubblewrap: 생성된 코드를 **파일 시스템까지** 가두는 샌드박스 (DAY 27).
#   네트워크만 끊으면 생성된 코드가 서버와 같은 사용자로 계정 DB·다른 테넌트의
#   프로젝트·서버 소스를 읽고 고칠 수 있다. app/orchestrator/isolation.py 참조.
RUN apt-get update \
 && apt-get install -y --no-install-recommends util-linux bubblewrap ca-certificates \
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
COPY deploy/cloudrun/start.sh deploy/cloudrun/supervisor.py deploy/cloudrun/backend_boot.py /app/

# 로그인 횟수 제한이 믿을 '앞단 프록시' 대역 — 빌드할 때마다 구글 공개 목록에서
# 새로 만든다(backend/app/api/auth.py · TRUSTED_PROXY_FILE).
ADD https://www.gstatic.com/ipranges/goog.json /tmp/goog.json
ADD https://www.gstatic.com/ipranges/cloud.json /tmp/cloud.json
COPY deploy/cloudrun/google_proxies.py /tmp/google_proxies.py
RUN python /tmp/google_proxies.py /tmp/goog.json /tmp/cloud.json > /etc/trusted-proxies.txt \
 && grep -q "^66\.249\." /etc/trusted-proxies.txt \
 && rm /tmp/goog.json /tmp/cloud.json /tmp/google_proxies.py

# 코드와 화면 파일은 root 소유·**아무도 못 쓰게** 둔다. 윈도우에서 올린 빌드
# 컨텍스트는 권한이 777 로 들어온다 — DAY 27 에 Cloud Run 에서 서버 사용자가
# /app/backend 에 파일을 만들 수 있는 것을 실제로 확인했다.
# 쓸 수 있는 곳은 로컬 DB·로그 폴더뿐이다. 나머지 상태는 버킷 마운트(/mnt/state)다.
RUN useradd --create-home --uid 10001 company \
 && chmod -R a-w,a+rX /app/backend /app/web /app/start.sh /app/supervisor.py /app/backend_boot.py \
      /etc/litestream.yml /etc/trusted-proxies.txt \
 && chmod a+x /app/start.sh \
 && mkdir -p /app/db /app/logs \
 && chown company:company /app/db /app/logs
USER company

# 상태가 사는 곳 (DAY 27):
#   /app/db      SQLite — 로컬 디스크 + Litestream (gcsfuse 위에서 SQLite 는 깨진다)
#   /app/logs    실행 트레이스 — 로컬에 덧붙이고 TRACE_ARCHIVE_DIR 로 주기 보관
#   /mnt/state   Cloud Storage 마운트 — JSON·프로젝트 산출물·첨부·예약
ENV DEPLOY_MODE=saas \
    DB_DIR=/app/db \
    LOGS_DIR=/app/logs \
    DATA_DIR=/mnt/state/data \
    PROJECTS_DIR=/mnt/state/projects \
    ATTACHMENTS_DIR=/mnt/state/attachments \
    SCHEDULES_FILE=/mnt/state/data/schedules.json \
    TRACE_ARCHIVE_DIR=/mnt/state/traces \
    RUNNER_ISOLATE_NETWORK=1 \
    SESSION_COOKIE=__session \
    TRUSTED_PROXY_FILE=/etc/trusted-proxies.txt \
    PORT=8080

EXPOSE 8080
# 감독자가 임대를 받은 뒤에야 start.sh(복원 → 복제 → 앱)를 띄운다.
CMD ["python", "/app/supervisor.py"]
