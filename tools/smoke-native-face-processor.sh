#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM="${SYNO_PLATFORM:-${AV_IMGDATA_NATIVE_PLATFORM:-local}}"
NATIVE_ROOT="${PROJECT_DIR}/build/native/${PLATFORM}/face_processor-install/usr/local/AV_ImgData"
NATIVE_BINARY="${NATIVE_ROOT}/bin/av-imgdata-face-processor"

if [ ! -x "${NATIVE_BINARY}" ]; then
  echo "ERROR: native face processor missing or not executable: ${NATIVE_BINARY}" >&2
  exit 1
fi

VERSION_OUTPUT="$("${NATIVE_BINARY}" version)"
case "${VERSION_OUTPUT}" in
  *onnxruntime-native*) ;;
  *)
    echo "ERROR: native face processor version does not report onnxruntime-native: ${VERSION_OUTPUT}" >&2
    exit 1
    ;;
esac

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/av-imgdata-native-smoke.XXXXXX")"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

cat >"${TMP_DIR}/rank-input.json" <<'JSON'
{"contract_version":"1.0","job_id":"rank-smoke","type":"face_native_rank_embeddings","input":{},"options":{},"target_embeddings":[[1,0],[0,1]],"profile_embeddings":[[1,0],[0,1],[0.7,0.3]]}
JSON
"${NATIVE_BINARY}" rank_embeddings --input "${TMP_DIR}/rank-input.json" --output "${TMP_DIR}/rank-output.json" >/dev/null
python3 -m json.tool "${TMP_DIR}/rank-output.json" >/dev/null
python3 -c 'import json, sys; p=json.load(open(sys.argv[1])); assert p["type"] == "face_native_rank_embeddings"; assert p["status"] == "completed"; assert p["result"]["ranks"][0]["best_index"] == 0' "${TMP_DIR}/rank-output.json"

cat >"${TMP_DIR}/profile-input.json" <<'JSON'
{"contract_version":"1.0","job_id":"profile-smoke","type":"face_native_profile_math","input":{},"options":{},"embeddings":[[1,0],[0.8,0.2],[0.9,0.1]]}
JSON
"${NATIVE_BINARY}" profile_math --input "${TMP_DIR}/profile-input.json" --output "${TMP_DIR}/profile-output.json" >/dev/null
python3 -m json.tool "${TMP_DIR}/profile-output.json" >/dev/null
python3 -c 'import json, sys; p=json.load(open(sys.argv[1])); assert p["type"] == "face_native_profile_math"; assert p["status"] == "completed"; assert p["result"]["centroid_embedding"]; assert isinstance(p["result"]["medoid_index"], int)' "${TMP_DIR}/profile-output.json"

echo "Native face processor smoke checks passed: ${NATIVE_BINARY}"
