#!/bin/sh
# Cloud Run 앱 기동 (DAY 27). supervisor.py 가 **임대를 받은 뒤에만** 부른다.
#
#   1. Cloud Storage 에서 SQLite 를 되살린다 (Litestream)
#   2. Litestream 이 복제하면서 앱(백엔드 127.0.0.1:8000 + Next 0.0.0.0:$PORT)을 띄운다
#
# JSON·프로젝트·첨부는 버킷 마운트(/mnt/state)에 바로 쓰이므로 여기서 할 일이 없다.
# 종료: supervisor 가 프로세스 그룹 전체에 SIGTERM 을 보낸다. Litestream 은
# -exec 로 감싼 앱이 끝나면 남은 WAL 을 올리고 끝난다.
set -eu

DB=${DB_DIR:-/app/db}
mkdir -p "$DB" "${LOGS_DIR:-/app/logs}"

cat > /tmp/run-app.sh <<'EOF'
#!/bin/sh
python -m uvicorn app.main:app --app-dir /app/backend \
  --host 127.0.0.1 --port 8000 --timeout-keep-alive 75 \
  --proxy-headers --forwarded-allow-ips 127.0.0.1 &
BACK=$!
cd /app/web && HOSTNAME=0.0.0.0 node server.js &
WEB=$!
trap 'kill $WEB $BACK 2>/dev/null' TERM INT
# 둘 중 하나라도 죽으면 내려간다 — 반쪽만 살아 있는 서버는 더 나쁘다.
while kill -0 $BACK 2>/dev/null && kill -0 $WEB 2>/dev/null; do sleep 1; done
kill $WEB $BACK 2>/dev/null || true
wait
EOF
chmod +x /tmp/run-app.sh

if [ -z "${STATE_BUCKET:-}" ]; then
  echo "[start] STATE_BUCKET 이 없습니다 — 상태가 재시작마다 사라집니다." >&2
  exec /tmp/run-app.sh
fi

for db in ai_company_auth.db ai_company.db; do
  litestream restore -config /etc/litestream.yml -if-db-not-exists -if-replica-exists "$DB/$db"
done

exec litestream replicate -config /etc/litestream.yml -exec /tmp/run-app.sh
