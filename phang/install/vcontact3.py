"""
Install and manage vConTACT3.

Conda env : ~/.phang/envs/vcontact3  (Python 3.10)
Database  : ~/.phang/databases/vcontact3_db/

TODO: implement DB download per vConTACT3 docs.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from phang.config import DB_MANIFEST_FILENAME, DB_VCONTACT3, ENV_VCONTACT3, PYTHON_VERSIONS
from phang.install.common import (
    conda_install,
    create_env,
    env_exists,
    extract_tar_gz,
    find_conda,
    get_installed_version,
    load_manifest,
    save_manifest,
    _run_conda,
)

logger = logging.getLogger(__name__)
_MANIFEST = DB_VCONTACT3 / DB_MANIFEST_FILENAME


def _db_ready() -> bool:
    json_ok = any(DB_VCONTACT3.glob("*.json"))
    ref_dir_ok = any(p.is_dir() and p.name.startswith("v") for p in DB_VCONTACT3.iterdir()) if DB_VCONTACT3.exists() else False
    return json_ok and ref_dir_ok


def _ensure_db(conda: str, installed_ver: str) -> None:
    DB_VCONTACT3.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(_MANIFEST)

    if _db_ready():
        logger.info("vConTACT3 DB already present: %s", DB_VCONTACT3)
        if manifest is None:
            save_manifest(
                _MANIFEST,
                {
                    "tool": "vcontact3",
                    "tool_version": installed_ver,
                    "db_dir": str(DB_VCONTACT3),
                    "prepared_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        return

    tarballs = sorted(DB_VCONTACT3.glob("v*.tar.gz"))
    if tarballs:
        for tarball in tarballs:
            try:
                extract_tar_gz(tarball, DB_VCONTACT3)
            except Exception as exc:
                logger.warning("Could not extract %s: %s", tarball.name, exc)
                tarball.unlink(missing_ok=True)
        if _db_ready():
            save_manifest(
                _MANIFEST,
                {
                    "tool": "vcontact3",
                    "tool_version": installed_ver,
                    "db_dir": str(DB_VCONTACT3),
                    "prepared_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            return

    logger.info("Preparing vConTACT3 databases…")
    _run_conda([
        conda, "run", "--no-capture-output", "-p", str(ENV_VCONTACT3),
        "vcontact3", "prepare_databases",
        "--get-version", "latest",
        "--set-location", str(DB_VCONTACT3),
    ])
    save_manifest(
        _MANIFEST,
        {
            "tool": "vcontact3",
            "tool_version": installed_ver,
            "db_dir": str(DB_VCONTACT3),
            "prepared_at": datetime.now().isoformat(timespec="seconds"),
        },
    )


def ensure_vcontact3() -> str:
    """Ensure vConTACT3 is installed. Returns installed version."""
    conda = find_conda()

    if not env_exists(ENV_VCONTACT3):
        create_env(conda, ENV_VCONTACT3, PYTHON_VERSIONS["vcontact3"])
        # Install vcontact3 + vclust together (vclust required for ANI export)
        conda_install(conda, ENV_VCONTACT3, ["vcontact3", "vclust"])
    else:
        ver_check = get_installed_version(conda, ENV_VCONTACT3, "vcontact3")
        if ver_check == "unknown":
            conda_install(conda, ENV_VCONTACT3, ["vcontact3", "vclust"])

    ver = get_installed_version(conda, ENV_VCONTACT3, "vcontact3")
    _ensure_db(conda, ver)
    logger.info("vConTACT3 installed: %s", ver)
    return ver
