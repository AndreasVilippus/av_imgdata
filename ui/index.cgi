#!/bin/sh
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/syno/bin:/usr/syno/sbin

APP_NAME="AV_ImgData"
BACKEND_BASE="http://127.0.0.1:9771"

has_dsm_session_cookie() {
  cookie_header="$1"
  [ -n "$cookie_header" ] || return 1

  # Keep this aligned with src/api/imgdata_api.py and ui/src/App.vue:
  # DSM sessions may be represented by either _SSID or id cookies.
  case "; ${cookie_header}" in
    *"; _SSID="*|*"; id="*)
      return 0
      ;;
  esac
  return 1
}

cleanup_tmp_files() {
  [ -n "${body_file:-}" ] && rm -f "$body_file"
  [ -n "${hdr_file:-}" ] && rm -f "$hdr_file"
  [ -n "${out_file:-}" ] && rm -f "$out_file"
}

# DSM already gates /webman/3rdparty behind an authenticated session.
# Accept the same DSM session cookie names that the backend accepts.
if ! has_dsm_session_cookie "${HTTP_COOKIE:-}"; then
  echo "Status: 403 Forbidden"
  echo "Content-Type: text/plain"
  echo
  echo "Access denied"
  exit 0
fi

method="${REQUEST_METHOD:-GET}"
path="${PATH_INFO:-/}"

target="${BACKEND_BASE}${path}"
if [ -n "${QUERY_STRING:-}" ]; then
  target="${target}?${QUERY_STRING}"
fi

body_file=""
case "${CONTENT_LENGTH:-}" in
  ''|*[!0-9]*)
    content_length=0
    ;;
  *)
    content_length="$CONTENT_LENGTH"
    ;;
esac

if [ "$content_length" -gt 0 ]; then
  body_file="$(mktemp /tmp/av_imgdata_body.XXXXXX)"
  dd bs=1 count="$content_length" >"${body_file}" 2>/dev/null
fi

curl_cmd="/usr/bin/curl"
if [ ! -x "$curl_cmd" ]; then
  curl_cmd="/bin/curl"
fi

if [ ! -x "$curl_cmd" ]; then
  echo "Status: 500 Internal Server Error"
  echo "Content-Type: text/plain"
  echo
  echo "curl not found"
  cleanup_tmp_files
  exit 0
fi

hdr_file="$(mktemp /tmp/av_imgdata_hdr.XXXXXX)"
out_file="$(mktemp /tmp/av_imgdata_out.XXXXXX)"

set -- -s -D "$hdr_file" -o "$out_file" -X "$method"
[ -n "${HTTP_COOKIE:-}" ] && set -- "$@" -H "Cookie: $HTTP_COOKIE"
[ -n "${CONTENT_TYPE:-}" ] && set -- "$@" -H "Content-Type: $CONTENT_TYPE"
[ -n "${HTTP_ORIGIN:-}" ] && set -- "$@" -H "Origin: $HTTP_ORIGIN"
[ -n "${HTTP_REFERER:-}" ] && set -- "$@" -H "Referer: $HTTP_REFERER"
[ -n "${HTTP_X_SYNO_TOKEN:-}" ] && set -- "$@" -H "X-SYNO-TOKEN: $HTTP_X_SYNO_TOKEN"
[ -n "$body_file" ] && set -- "$@" --data-binary "@$body_file"

if ! "$curl_cmd" "$@" "$target"; then
  echo "Status: 502 Bad Gateway"
  echo "Content-Type: text/plain"
  echo
  echo "Backend request failed"
  cleanup_tmp_files
  exit 0
fi

status_line="$(head -n 1 "$hdr_file")"
status="${status_line#HTTP/* }"
if [ -z "$status" ] || [ "$status" = "$status_line" ]; then
  status="502 Bad Gateway"
fi
content_type="$(awk 'tolower($1)=="content-type:" {print $0; exit}' "$hdr_file")"
content_disposition="$(awk 'tolower($1)=="content-disposition:" {print $0; exit}' "$hdr_file")"

echo "Status: $status"
if [ -n "$content_type" ]; then
  echo "$content_type"
else
  echo "Content-Type: application/json"
fi
if [ -n "$content_disposition" ]; then
  echo "$content_disposition"
fi
echo
cat "$out_file"

cleanup_tmp_files
