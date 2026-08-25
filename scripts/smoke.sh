#!/usr/bin/env sh
# Phase 1 smoke test against a running API.
set -eu
BASE="${API_BASE:-http://localhost:8002}"
TOKEN="${INTERNAL_API_TOKEN:-dev-internal-token}"
H="X-Internal-Token: ${TOKEN}"

echo "== health =="
curl -sf "$BASE/health" | tee /dev/stderr
echo

echo "== seed =="
SEED=$(curl -sf -X POST -H "$H" "$BASE/api/v1/internal/seed")
echo "$SEED"
WS=$(echo "$SEED" | python -c "import sys,json; print(json.load(sys.stdin)['workspace_id'])")

echo "== create monitor =="
MON=$(curl -sf -X POST -H "$H" -H "Content-Type: application/json" \
  -d '{"name":"Smoke example.com","url":"https://example.com/","mode":"whole_page","schedule_interval_minutes":60,"notification_email":"smoke@example.com"}' \
  "$BASE/api/v1/workspaces/$WS/monitors")
echo "$MON"
MID=$(echo "$MON" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo "== manual run =="
curl -sf -X POST -H "$H" "$BASE/api/v1/workspaces/$WS/monitors/$MID/run"
echo

echo "== wait =="
i=0
while [ "$i" -lt 30 ]; do
  i=$((i + 1))
  sleep 2
  RUNS=$(curl -sf -H "$H" "$BASE/api/v1/workspaces/$WS/monitors/$MID/runs")
  STATUS=$(echo "$RUNS" | python -c "import sys,json; d=json.load(sys.stdin); print(d[0]['status'] if d else '')")
  echo "status=$STATUS"
  case "$STATUS" in
    succeeded|failed|cancelled) break ;;
  esac
done

echo "== usage =="
curl -sf -H "$H" "$BASE/api/v1/workspaces/$WS/usage"
echo

echo "$STATUS" | grep -q succeeded
echo "SMOKE OK"
