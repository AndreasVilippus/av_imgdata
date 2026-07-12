#!/usr/bin/env python3
"""Create a short-lived, one-time external-worker enrollment code."""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from services.worker_api_composition_service import WorkerApiCompositionService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-var", default=os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var"))
    parser.add_argument("--state-path", default="", help="Explicit override; config and environment are used when omitted")
    parser.add_argument("--enrollment-id", required=True)
    parser.add_argument("--expires-minutes", type=int, default=15)
    args = parser.parse_args()

    composition = WorkerApiCompositionService(
        package_var=Path(args.package_var),
        state_path=Path(args.state_path) if str(args.state_path).strip() else None,
    )
    payload = composition.provisioning.create_enrollment(
        enrollment_id=args.enrollment_id,
        expires_minutes=args.expires_minutes,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
