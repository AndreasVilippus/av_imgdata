#!/usr/bin/env python3
"""Create a short-lived, one-time external-worker enrollment code."""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from services.worker_provisioning_service import WorkerProvisioningService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-var", default=os.getenv("SYNOPKG_PKGVAR", "/var/packages/AV_ImgData/var"))
    parser.add_argument("--state-path", default=os.getenv("AV_IMGDATA_WORKER_API_STATE_PATH", ""))
    parser.add_argument("--enrollment-id", required=True)
    parser.add_argument("--expires-minutes", type=int, default=15)
    args = parser.parse_args()

    package_var = Path(args.package_var)
    state_path = Path(args.state_path) if args.state_path else package_var / "worker-api-state.json"
    if not state_path.is_absolute():
        state_path = package_var / state_path
    service = WorkerProvisioningService(package_var=package_var, state_path=state_path)
    payload = service.create_enrollment(enrollment_id=args.enrollment_id, expires_minutes=args.expires_minutes)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
