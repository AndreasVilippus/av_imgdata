#!/bin/sh
set -eu

usage() {
  cat <<'EOF'
Usage:
  initialize-av-imgdata-worker.sh \
    --api-url <worker-api-url> \
    --worker-id <id> \
    --path-base-dir <path> \
    [--enrollment-code <code>] \
    [--model-pack buffalo_l] \
    [--config <path>] \
    [--force-enroll]
EOF
}

API_URL=""
ENROLLMENT_CODE=""
WORKER_ID=""
PATH_BASE_DIR=""
MODEL_PACK="buffalo_l"
CONFIG_PATH=""
FORCE_ENROLL=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --api-url) API_URL=${2:-}; shift 2 ;;
    --enrollment-code) ENROLLMENT_CODE=${2:-}; shift 2 ;;
    --worker-id) WORKER_ID=${2:-}; shift 2 ;;
    --path-base-dir) PATH_BASE_DIR=${2:-}; shift 2 ;;
    --model-pack) MODEL_PACK=${2:-}; shift 2 ;;
    --config) CONFIG_PATH=${2:-}; shift 2 ;;
    --force-enroll) FORCE_ENROLL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -z "$API_URL" ] || [ -z "$WORKER_ID" ] || [ -z "$PATH_BASE_DIR" ]; then
  echo "ERROR: --api-url, --worker-id and --path-base-dir are required" >&2
  usage >&2
  exit 2
fi

API_URL=${API_URL%/}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUNDLE_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
TOKEN_PATH="$BUNDLE_ROOT/worker.token"
MODEL_ROOT="$BUNDLE_ROOT/.models/face"
CONFIG_PATH=${CONFIG_PATH:-$BUNDLE_ROOT/config/worker-config.example.json}
CONFIGURE_BIN="$BUNDLE_ROOT/bin/av-imgdata-worker-configure"
MODEL_SYNC_BIN="$BUNDLE_ROOT/bin/av-imgdata-worker-model-sync"

for required in "$CONFIGURE_BIN" "$MODEL_SYNC_BIN"; do
  if [ ! -x "$required" ]; then
    echo "ERROR: required worker tool is missing or not executable: $required" >&2
    exit 3
  fi
done

TOKEN=""
if [ -f "$TOKEN_PATH" ] && [ "$FORCE_ENROLL" -eq 0 ]; then
  TOKEN=$(tr -d '\r\n' < "$TOKEN_PATH")
  [ -z "$TOKEN" ] || echo "Using existing worker token from $TOKEN_PATH"
fi

if [ -z "$TOKEN" ]; then
  if [ -z "$ENROLLMENT_CODE" ]; then
    echo "ERROR: --enrollment-code is required because no reusable worker.token exists" >&2
    exit 4
  fi
  command -v curl >/dev/null 2>&1 || { echo "ERROR: curl is required for enrollment" >&2; exit 5; }
  BODY=$(printf '{"enrollment_code":"%s","worker_id":"%s"}' "$ENROLLMENT_CODE" "$WORKER_ID")
  RESPONSE=$(curl -fSsL -X POST -H 'Content-Type: application/json' --data-binary "$BODY" "$API_URL/enroll") || {
    echo "ERROR: worker enrollment failed" >&2
    exit 6
  }
  TOKEN=$(printf '%s' "$RESPONSE" | sed -n 's/.*"token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  if [ -z "$TOKEN" ]; then
    echo "ERROR: enrollment response did not contain a token" >&2
    exit 7
  fi
  umask 077
  printf '%s' "$TOKEN" > "$TOKEN_PATH"
fi
chmod 600 "$TOKEN_PATH" 2>/dev/null || true

"$CONFIGURE_BIN" \
  --config "$CONFIG_PATH" \
  --worker-id "$WORKER_ID" \
  --api-url "$API_URL" \
  --path-base-dir "$PATH_BASE_DIR" \
  --model-pack "$MODEL_PACK"

"$MODEL_SYNC_BIN" \
  --api-url "$API_URL" \
  --token-file "$TOKEN_PATH" \
  --worker-id "$WORKER_ID" \
  --model-root "$MODEL_ROOT" \
  --model-pack "$MODEL_PACK"

echo "Worker enrolled, configured and model files synchronized."
echo "Config: $CONFIG_PATH"
echo "Token:  $TOKEN_PATH"
echo "Models: $MODEL_ROOT/$MODEL_PACK"
