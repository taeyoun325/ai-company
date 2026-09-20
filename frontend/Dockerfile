# AI COMPANY 프론트엔드 (DAY 16).
#
# 빌드와 실행을 나눈다(멀티 스테이지). 최종 이미지에 소스와 빌드 도구가
# 남으면 크기만 커지는 게 아니라, 배포 서버에 컴파일러가 있는 상태가 된다.
#
# 빌드: docker build -f frontend/Dockerfile -t ai-company-frontend ./frontend

# ── 1) 의존성 ──────────────────────────────────────────────────────
FROM node:24-alpine AS deps
WORKDIR /app
# package-lock.json 을 함께 복사해 `npm ci` 를 쓴다 — `npm install` 과 달리
# 잠금 파일을 그대로 재현한다. 배포에서 버전이 미끄러지면 안 된다.
COPY package.json package-lock.json ./
RUN npm ci

# ── 2) 빌드 ────────────────────────────────────────────────────────
FROM node:24-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ── 3) 실행 ────────────────────────────────────────────────────────
FROM node:24-alpine AS run
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# standalone 출력에는 실행에 필요한 node_modules 만 들어 있다.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

# node 이미지에 이미 있는 비루트 사용자.
USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
