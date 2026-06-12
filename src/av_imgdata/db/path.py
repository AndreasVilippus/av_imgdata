import os
from pathlib import Path
from typing import Optional


PACKAGE_NAME = "AV_ImgData"


def get_pkgvar_dir(package_var: Optional[str] = None) -> Path:
    value = package_var if package_var is not None else os.environ.get("SYNOPKG_PKGVAR")
    if value:
        return Path(value)
    return Path("/var/packages") / PACKAGE_NAME / "var"


def get_db_path(package_var: Optional[str] = None) -> Path:
    return get_pkgvar_dir(package_var) / "imgdata.sqlite3"
