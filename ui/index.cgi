#!/bin/sh
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/syno/bin:/usr/syno/sbin

APP_NAME="AV_ImgData"
BACKEND_BASE="http://127.0.0.1:9771"

# DSM already gates /webman/3rdparty behind an authenticated session.
# Accept requests that carry a DSM session cookie.
if [ -z "${HTTP_COOKIE:-}" ] || ! echo "$HTTP_COOKIE" | grep -q "_SSID="; then
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
if [ -n "${CONTENT_LENGTH:-}" ] && [ "${CONTENT_LENGTH}" -gt 0 ]; then
  body_file="$(mktemp /tmp/av_imgdata_body.XXXXXX)"
  dd bs=1 count="${CONTENT_LENGTH}" >"${body_file}" 2>/dev/null
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
  [ -n "$body_file" ] && rm -f "$body_file"
  exit 0
fi

hdr_file="$(mktemp /tmp/av_imgdata_hdr.XXXXXX)"
out_file="$(mktemp /tmp/av_imgdata_out.XXXXXX)"
$curl_cmd -s -D "$hdr_file" -o "$out_file" -X "$method" \
  ${HTTP_COOKIE:+-H "Cookie: $HTTP_COOKIE"} \
  ${CONTENT_TYPE:+-H "Content-Type: $CONTENT_TYPE"} \
  ${HTTP_ORIGIN:+-H "Origin: $HTTP_ORIGIN"} \
  ${HTTP_REFERER:+-H "Referer: $HTTP_REFERER"} \
  ${HTTP_X_SYNO_TOKEN:+-H "X-SYNO-TOKEN: $HTTP_X_SYNO_TOKEN"} \
  ${body_file:+--data-binary "@$body_file"} \
  "$target"

[ -n "$body_file" ] && rm -f "$body_file"

status_line="$(head -n 1 "$hdr_file")"
status="${status_line#HTTP/* }"
content_type="$(awk 'tolower($1)=="content-type:" {print $0; exit}' "$hdr_file")"

echo "Status: $status"
if [ -n "$content_type" ]; then
  echo "$content_type"
else
  echo "Content-Type: application/json"
fi
echo
cat "$out_file"

rm -f "$hdr_file" "$out_file"
