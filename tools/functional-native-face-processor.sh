#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM="${SYNO_PLATFORM:-${AV_IMGDATA_NATIVE_PLATFORM:-local}}"
NATIVE_ROOT="${PROJECT_DIR}/build/native/${PLATFORM}/face_processor-install/usr/local/AV_ImgData"
NATIVE_BINARY="${NATIVE_ROOT}/bin/av-imgdata-face-processor"
REQUIRED="${AV_IMGDATA_NATIVE_FUNCTIONAL_TEST_REQUIRED:-0}"

fail_or_skip() {
  local message="$1"
  if [ "${REQUIRED}" = "1" ]; then
    echo "ERROR: ${message}" >&2
    exit 1
  fi
  echo "SKIP: ${message}" >&2
  exit 0
}

resolve_model_root() {
  if [ -n "${AV_IMGDATA_NATIVE_MODEL_ROOT:-}" ]; then
    printf '%s\n' "${AV_IMGDATA_NATIVE_MODEL_ROOT}"
    return
  fi
  local candidate
  for candidate in \
    "${HOME:-}/.insightface" \
    "${HOME:-}/.insightface/models" \
    "${PROJECT_DIR}/models" \
    "${PROJECT_DIR}/dev/models" \
    "${PROJECT_DIR}/build/native/${PLATFORM}/models"; do
    if [ -f "${candidate}/buffalo_l/det_10g.onnx" ] && [ -f "${candidate}/buffalo_l/w600k_r50.onnx" ]; then
      printf '%s\n' "${candidate}"
      return
    fi
    if [ -f "${candidate}/models/buffalo_l/det_10g.onnx" ] && [ -f "${candidate}/models/buffalo_l/w600k_r50.onnx" ]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done
}

if [ ! -x "${NATIVE_BINARY}" ]; then
  fail_or_skip "native face processor missing or not executable: ${NATIVE_BINARY}"
fi

MODEL_ROOT="$(resolve_model_root || true)"
MODEL_NAME="${AV_IMGDATA_NATIVE_MODEL_NAME:-buffalo_l}"
if [ -z "${MODEL_ROOT}" ]; then
  fail_or_skip "InsightFace ONNX model root not found. Set AV_IMGDATA_NATIVE_MODEL_ROOT and AV_IMGDATA_NATIVE_MODEL_NAME."
fi

if [ -n "${AV_IMGDATA_NATIVE_TEST_IMAGE:-}" ]; then
  TEST_IMAGE="${AV_IMGDATA_NATIVE_TEST_IMAGE}"
elif [ -f "${PROJECT_DIR}/dev/20160620_081556.jpg" ]; then
  TEST_IMAGE="${PROJECT_DIR}/dev/20160620_081556.jpg"
else
  TEST_IMAGE="${PROJECT_DIR}/tests/images/test_pic.jpg"
fi
if [ ! -f "${TEST_IMAGE}" ]; then
  fail_or_skip "native functional test image missing: ${TEST_IMAGE}"
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/av-imgdata-native-functional.XXXXXX")"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

"${NATIVE_BINARY}" probe --model-root "${MODEL_ROOT}" --model-name "${MODEL_NAME}" >/tmp/av-imgdata-native-probe.out

cat >"${TMP_DIR}/embed-input.json" <<JSON
{"contract_version":"1.0","job_id":"functional-embed","type":"face_native_embed","input":{"image_path":"${TEST_IMAGE}","source_id":"functional-image"},"options":{"model_root":"${MODEL_ROOT}","model_name":"${MODEL_NAME}","min_confidence":0.35,"max_faces":0,"det_size":[640,640],"normalize_coordinates":true}}
JSON
"${NATIVE_BINARY}" embed --input "${TMP_DIR}/embed-input.json" --output "${TMP_DIR}/embed-output.json" --workdir "${TMP_DIR}" >/dev/null
python3 -m json.tool "${TMP_DIR}/embed-output.json" >/dev/null
python3 -c '
import json, math, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["type"] == "face_native_embed", payload.get("type")
assert payload["status"] == "completed", payload
faces = payload.get("result", {}).get("faces") or []
assert len(faces) >= int(sys.argv[2]), f"expected at least {sys.argv[2]} faces, got {len(faces)}"
for face in faces:
    assert "box" in face or "bbox" in face, face
    embedding = face.get("embedding") or []
    assert len(embedding) >= 128, f"embedding too short: {len(embedding)}"
    assert all(math.isfinite(float(value)) for value in embedding), "embedding contains non-finite values"
    norm = math.sqrt(sum(float(value) * float(value) for value in embedding))
    assert 0.90 <= norm <= 1.10, f"embedding norm outside expected range: {norm}"
' "${TMP_DIR}/embed-output.json" "${AV_IMGDATA_NATIVE_MIN_FACES:-1}"

cat >"${TMP_DIR}/batch-input.json" <<JSON
{"contract_version":"1.0","job_id":"functional-batch","type":"face_native_embed_batch","input":{"image_paths":["${TEST_IMAGE}","${TEST_IMAGE}"]},"options":{"model_root":"${MODEL_ROOT}","model_name":"${MODEL_NAME}","min_confidence":0.35,"max_faces":0,"det_size":[640,640],"normalize_coordinates":true}}
JSON
"${NATIVE_BINARY}" embed_batch --input "${TMP_DIR}/batch-input.json" --output "${TMP_DIR}/batch-output.json" --workdir "${TMP_DIR}" >/dev/null
python3 -m json.tool "${TMP_DIR}/batch-output.json" >/dev/null
python3 -c '
import json, math, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["type"] == "face_native_embed_batch", payload.get("type")
assert payload["status"] == "completed", payload
images = payload.get("result", {}).get("images") or []
assert len(images) == 2, f"expected 2 batch images, got {len(images)}"
for image in images:
    assert image.get("status") == "completed", image
    faces = image.get("faces") or []
    assert len(faces) >= int(sys.argv[2]), f"expected at least {sys.argv[2]} faces, got {len(faces)}"
    embedding = faces[0].get("embedding") or []
    assert len(embedding) >= 128, f"embedding too short: {len(embedding)}"
    norm = math.sqrt(sum(float(value) * float(value) for value in embedding))
    assert 0.90 <= norm <= 1.10, f"embedding norm outside expected range: {norm}"
' "${TMP_DIR}/batch-output.json" "${AV_IMGDATA_NATIVE_MIN_FACES:-1}"

echo "Native face processor functional checks passed: binary=${NATIVE_BINARY} model_root=${MODEL_ROOT} model_name=${MODEL_NAME} image=${TEST_IMAGE}"
