#!/bin/sh
# Cloud Run 진입점 (DAY 27).
#
#   1. Cloud Storage 에서 DB 와 작은 JSON 상태 파일을 되살린다
#   2. 백엔드(127.0.0.1:8000)와 Next(0.0.0.0:$PORT)를 띄운다
#   3. Litestream 이 DB 를 계속 복제하고, JSON 은 주기적으로 올린다
#
# STATE_DIR 은 Cloud Storage 버킷을 마운트한 폴더다(Cloud Run 볼륨).
# SQLite 를 거기에 직접 두지 않는 이유: gcsfuse 는 파일 잠금이 없어서
# WAL 모드 SQLite 가 깨진다. DB 는 로컬 디스크 + Litestream 이다.
set -eu

DATA=/app/data
STATE_DIR=${STATE_DIR:-/mnt/state}
JSON_FILES=".staff.json .byok.json .secrets.json .credits.json"

if [ -z "${STATE_BUCKET:-}" ]; then
  echo "[start] STATE_BUCKET 이 없습니다 — 상태가 재시작마다 사라집니다." >&2
  exec sh -c 'python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --timeout-keep-alive 75 --proxy-headers --forwarded-allow-ips 127.0.0.1 & cd /app/web && HOSTNAME=0.0.0.0 exec node server.js'
fi

# ── 1) 되살리기 ────────────────────────────────────────────────────
for db in ai_company_auth.db ai_company.db; do
  litestream restore -config /etc/litestream.yml -if-db-not-exists -if-replica-exists "$DATA/$db"
done
if [ -d "$STATE_DIR" ]; then
  for f in $JSON_FILES; do
    [ -f "$STATE_DIR/json/$f" ] && cp "$STATE_DIR/json/$f" "$DATA/$f"
  done
fi

# ── 2) JSON 을 올리는 루프 ─────────────────────────────────────────
sync_json() {
  [ -d "$STATE_DIR" ] || return 0
  mkdir -p "$STATE_DIR/json"
  for f in $JSON_FILES; do
    if [ -f "$DATA/$f" ] && ! cmp -s "$DATA/$f" "$STATE_DIR/json/$f" 2>/dev/null; then
      cp "$DATA/$f" "$STATE_DIR/json/$f.tmp" && mv "$STATE_DIR/json/$f.tmp" "$STATE_DIR/json/$f"
    fi
  done
}
( while true; do sleep 15; sync_json; done ) &

# ── 3) 앱 ──────────────────────────────────────────────────────────
# 종료 신호(SIGTERM)가 오면 JSON 을 마지막으로 한 번 올린다.
# Litestream 은 -exec 로 감싼 프로세스가 끝날 때 남은 WAL 을 올리고 끝난다.
cat > /tmp/app.sh <<'EOF'
#!/bin/sh
python -m uvicorn app.main:app --app-dir /app/backend \
  --host 127.0.0.1 --port 8000 --timeout-keep-alive 75 \
  --proxy-headers --forwarded-allow-ips 127.0.0.1 &
BACK=$!
cd /app/web && HOSTNAME=0.0.0.0 node server.js &
WEB=$!
trap 'kill $WEB $BACK 2>/dev/null' TERM INT
# 둘 중 하나라도 죽으면 컨테이너를 내린다 — 반쪽만 살아 있는 서버는 더 나쁘다.
while kill -0 $BACK 2>/dev/null && kill -0 $WEB 2>/dev/null; do sleep 2; done
kill $WEB $BACK 2>/dev/null
wait
EOF
chmod +x /tmp/app.sh

trap 'sync_json' TERM INT
cd /app
litestream replicate -config /etc/litestream.yml -exec /tmp/app.sh &
LS=$!
trap 'kill -TERM $LS 2>/dev/null; wait $LS; sync_json; exit 0' TERM INT
wait $LS
sync_json
