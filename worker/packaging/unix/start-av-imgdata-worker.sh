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

CONFIG_PATH=${CONFIG_PATH:-$BUNDLE_ROOT/config/worker-config.json}
WORKER_BIN=${WORKER_BIN:-$BUNDLE_ROOT/bin/av-imgdata-worker}
API_LOOP="$BUNDLE_ROOT/bin/av-imgdata-worker-api-loop"
CONFIGURE_BIN="$BUNDLE_ROOT/bin/av-imgdata-worker-configure"
TOKEN_PATH="$BUNDLE_ROOT/worker.token"
INIT_SCRIPT="$BUNDLE_ROOT/initialize-av-imgdata-worker.sh"
if [ ! -f "$INIT_SCRIPT" ]; then
  INIT_SCRIPT="$SCRIPT_DIR/initialize-av-imgdata-worker.sh"
fi

for required in "$API_LOOP" "$WORKER_BIN" "$CONFIGURE_BIN" "$INIT_SCRIPT"; do
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

example_string() {
  key=$1
  example_path=$BUNDLE_ROOT/config/worker-config.example.json
  [ -f "$example_path" ] || return 0
  sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$example_path" | head -n 1
}

prompt_value() {
  label=$1
  default_value=${2:-}
  required=${3:-0}
  PROMPT_RESULT=""

  while :; do
    if [ -n "$default_value" ]; then
      printf '%s [%s]: ' "$label" "$default_value" >&2
    else
      printf '%s: ' "$label" >&2
    fi
    IFS= read -r value || value=
    [ -n "$value" ] || value=$default_value
    if [ -n "$value" ] || [ "$required" -eq 0 ]; then
      PROMPT_RESULT=$value
      return 0
    fi
    printf '%s\n' "This value is required." >&2
  done
}

create_config_if_missing() {
  [ ! -f "$CONFIG_PATH" ] || return 0

  example_path=$BUNDLE_ROOT/config/worker-config.example.json
  printf '%s\n' "Worker configuration was not found and will be created:" "  $CONFIG_PATH"
  if [ -f "$example_path" ]; then
    printf '%s\n' \
      "" \
      "Example configuration values:" \
      "  worker_id:           $(example_string worker_id)" \
      "  worker_api_base_url: $(example_string worker_api_base_url)" \
      "  path_base_dir:       $(example_string path_base_dir)" \
      "  log_level:           off (alternatives: error, warning, info, debug)" \
      ""
  fi

  default_worker_id=$(example_string worker_id)
  [ -n "$default_worker_id" ] || default_worker_id=worker-01
  prompt_value "Worker ID" "$default_worker_id" 1
  created_worker_id=$PROMPT_RESULT
  prompt_value "Worker API base URL, for example https://nas:5001/worker-api" "$API_URL" 1
  created_api_url=$PROMPT_RESULT
  default_path_base_dir=$PATH_BASE_DIR
  [ -n "$default_path_base_dir" ] || default_path_base_dir=$(example_string path_base_dir)
  prompt_value "Shared Photos path base, for example /mnt/photo or /srv/photo" "$default_path_base_dir" 1
  created_path_base_dir=$PROMPT_RESULT
  printf '%s\n' "Log level defaults to off. Alternatives: error, warning, info, debug."
  prompt_value "Log level" "off" 0
  created_log_level=$PROMPT_RESULT
  case "$created_log_level" in
    off|error|warning|info|debug) ;;
    *) echo "ERROR: invalid log level: $created_log_level" >&2; exit 5 ;;
  esac
  prompt_value "Face model pack" "buffalo_l" 1
  created_model_pack=$PROMPT_RESULT

  "$CONFIGURE_BIN" \
    --config "$CONFIG_PATH" \
    --worker-id "$created_worker_id" \
    --api-url "$created_api_url" \
    --path-base-dir "$created_path_base_dir" \
    --model-pack "$created_model_pack" \
    --log-level "$created_log_level"
}

create_config_if_missing
[ -f "$CONFIG_PATH" ] || { echo "ERROR: required worker file is missing: $CONFIG_PATH" >&2; exit 3; }

[ -n "$PATH_BASE_DIR" ] || PATH_BASE_DIR=$(json_string path_base_dir)
[ -n "$API_URL" ] || API_URL=$(json_string worker_api_base_url)
WORKER_ID=$(json_string worker_id)
MODEL_PACK=$(json_string model_name)
[ -n "$MODEL_PACK" ] || MODEL_PACK=buffalo_l
LOG_LEVEL=$(json_string log_level)
[ -n "$LOG_LEVEL" ] || LOG_LEVEL=off

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
  --config "$CONFIG_PATH" \
  --log-level "$LOG_LEVEL"
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
