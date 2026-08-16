#!/bin/sh
set -eu

usage() {
  cat <<'EOF'
Usage:
  start-av-imgdata-worker.sh \
    [--config <path>] \
    [--worker-bin <path>] \
    [--path-base-dir <path>] \
    [--api-url <url>] \
    [--enrollment-code <code>] \
    [--insecure-tls]

Runs the worker API loop continuously in the foreground.
If no worker.token exists, the worker enrolls with the supplied code or asks for one.
--insecure-tls disables HTTPS certificate verification for local test setups.
Stop it with Ctrl+C or SIGTERM.
EOF
}

CONFIG_PATH=""
WORKER_BIN=""
PATH_BASE_DIR=""
API_URL=""
ENROLLMENT_CODE=""
INSECURE_TLS=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --config) CONFIG_PATH=${2:-}; shift 2 ;;
    --worker-bin) WORKER_BIN=${2:-}; shift 2 ;;
    --path-base-dir) PATH_BASE_DIR=${2:-}; shift 2 ;;
    --api-url) API_URL=${2:-}; shift 2 ;;
    --enrollment-code) ENROLLMENT_CODE=${2:-}; shift 2 ;;
    --insecure-tls) INSECURE_TLS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -d "$SCRIPT_DIR/bin" ]; then
  BUNDLE_ROOT=$SCRIPT_DIR
else
  BUNDLE_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
fi

CONFIG_PATH=${CONFIG_PATH:-$BUNDLE_ROOT/config/worker-config.example.json}
WORKER_BIN=${WORKER_BIN:-$BUNDLE_ROOT/bin/av-imgdata-worker}
API_LOOP="$BUNDLE_ROOT/bin/av-imgdata-worker-api-loop"
TOKEN_PATH="$BUNDLE_ROOT/worker.token"
INIT_SCRIPT="$BUNDLE_ROOT/initialize-av-imgdata-worker.sh"
if [ ! -f "$INIT_SCRIPT" ]; then
  INIT_SCRIPT="$SCRIPT_DIR/initialize-av-imgdata-worker.sh"
fi

for required in "$API_LOOP" "$WORKER_BIN" "$CONFIG_PATH" "$INIT_SCRIPT"; do
  if [ ! -f "$required" ]; then
    echo "ERROR: required worker file is missing: $required" >&2
    exit 3
  fi
done

if [ ! -x "$API_LOOP" ] || [ ! -x "$WORKER_BIN" ]; then
  echo "ERROR: worker executables are not executable" >&2
  exit 4
fi

json_string() {
  key=$1
  sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$CONFIG_PATH" | head -n 1
}

[ -n "$PATH_BASE_DIR" ] || PATH_BASE_DIR=$(json_string path_base_dir)
[ -n "$API_URL" ] || API_URL=$(json_string worker_api_base_url)
WORKER_ID=$(json_string worker_id)
MODEL_PACK=$(json_string model_name)
[ -n "$MODEL_PACK" ] || MODEL_PACK=buffalo_l

if [ -z "$PATH_BASE_DIR" ]; then
  echo "ERROR: path base is missing in arguments and configuration" >&2
  exit 5
fi
if [ -z "$API_URL" ]; then
  echo "ERROR: API URL is missing in arguments and configuration" >&2
  exit 6
fi
if [ -z "$WORKER_ID" ]; then
  echo "ERROR: worker_id is missing in configuration" >&2
  exit 6
fi
if [ ! -d "$PATH_BASE_DIR" ]; then
  echo "ERROR: worker path base is not accessible: $PATH_BASE_DIR" >&2
  exit 7
fi

if [ ! -f "$TOKEN_PATH" ] && [ -z "$ENROLLMENT_CODE" ]; then
  printf '%s' "Worker token not found. Enter registration code: " >&2
  IFS= read -r ENROLLMENT_CODE
fi

printf '%s\n' "Synchronizing worker configuration and DSM-authorized model files."
set -- sh "$INIT_SCRIPT" \
  --api-url "$API_URL" \
  --worker-id "$WORKER_ID" \
  --path-base-dir "$PATH_BASE_DIR" \
  --model-pack "$MODEL_PACK" \
  --config "$CONFIG_PATH"
if [ -n "$ENROLLMENT_CODE" ]; then
  set -- "$@" --enrollment-code "$ENROLLMENT_CODE"
fi
if [ "$INSECURE_TLS" -ne 0 ]; then
  set -- "$@" --insecure-tls
fi
"$@"

printf '%s\n' \
  "Starting AV ImgData worker in continuous foreground mode." \
  "Bundle:    $BUNDLE_ROOT" \
  "Config:    $CONFIG_PATH" \
  "API URL:   $API_URL" \
  "Path base: $PATH_BASE_DIR" \
  "Models:    synchronized from DSM authority" \
  "Stop with Ctrl+C or SIGTERM."
[ "$INSECURE_TLS" -eq 0 ] || printf '%s\n' "WARNING: TLS certificate verification is disabled for Worker API requests." >&2

cd "$BUNDLE_ROOT"
set -- "$API_LOOP" \
  --config "$CONFIG_PATH" \
  --worker-bin "$WORKER_BIN" \
  --api-url "$API_URL" \
  --path-base-dir "$PATH_BASE_DIR"
if [ "$INSECURE_TLS" -ne 0 ]; then
  set -- "$@" --insecure-tls
fi
exec "$@"
