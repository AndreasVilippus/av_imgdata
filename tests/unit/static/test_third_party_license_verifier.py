import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("tools/verify-third-party-licenses.py")


def run_verifier(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def test_third_party_license_verifier_writes_notice_for_known_runtime(tmp_path: Path):
    root = tmp_path / "package"
    (root / "lib").mkdir(parents=True)
    (root / "share" / "licenses" / "AV_ImgData" / "native-face-processor").mkdir(parents=True)
    (root / "lib" / "libonnxruntime.so.1").write_bytes(b"runtime")
    (root / "share" / "licenses" / "AV_ImgData" / "native-face-processor" / "onnxruntime.LICENSE").write_text(
        "license placeholder\n",
        encoding="utf-8",
    )

    result = run_verifier(root, "--write")

    assert result.returncode == 0, result.stderr
    notice_path = root / "share" / "licenses" / "AV_ImgData" / "third-party" / "THIRD-PARTY-NOTICES.json"
    notice = json.loads(notice_path.read_text(encoding="utf-8"))
    assert notice["schema"] == "av-imgdata-third-party-notices-v1"
    assert notice["components"][0]["id"] == "onnxruntime"
    assert notice["components"][0]["files"] == ["lib/libonnxruntime.so.1"]
    assert notice["components"][0]["evidence_files"] == [
        "share/licenses/AV_ImgData/native-face-processor/onnxruntime.LICENSE"
    ]


def test_third_party_license_verifier_rejects_unknown_runtime(tmp_path: Path):
    root = tmp_path / "package"
    (root / "lib").mkdir(parents=True)
    (root / "lib" / "libsurprise.so.1").write_bytes(b"runtime")

    result = run_verifier(root, "--write")

    assert result.returncode == 1
    assert "bundled native runtime files without license mapping" in result.stderr
    assert "lib/libsurprise.so.1" in result.stderr
    assert not (root / "share" / "licenses" / "AV_ImgData" / "third-party" / "THIRD-PARTY-NOTICES.json").exists()
