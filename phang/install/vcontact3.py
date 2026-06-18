"""
Install and manage vConTACT3.

Conda env : ~/.phang/envs/vcontact3  (Python 3.10)
Database  : ~/.phang/databases/vcontact3_db/

The reference database (v230) is fetched as a prebuilt tarball from Zenodo and
extracted. We deliberately avoid ``vcontact3 prepare_databases``: it invokes
MMseqs2 at install time (the AVX code path that SIGILLs under Rosetta on Apple
Silicon) and is network-fragile. Downloading the prebuilt tarball is
deterministic and architecture-independent; vConTACT3 builds its runtime
MMseqs2 index from the reference DB at run time.
"""

from __future__ import annotations

import logging
from datetime import datetime

from phang.config import DB_MANIFEST_FILENAME, DB_VCONTACT3, ENV_VCONTACT3, PYTHON_VERSIONS
from phang.install.common import (
    conda_install,
    create_env,
    download_file,
    env_exists,
    extract_tar_gz,
    find_conda,
    get_installed_version,
    load_manifest,
    save_manifest,
)

logger = logging.getLogger(__name__)
_MANIFEST = DB_VCONTACT3 / DB_MANIFEST_FILENAME

# Prebuilt vConTACT3 reference DB (v230), hosted on Zenodo (record 15598380).
_DB_URL = "https://zenodo.org/records/15598380/files/v230.tar.gz"
_DB_TARBALL_NAME = "v230.tar.gz"


def _db_ready() -> bool:
    json_ok = any(DB_VCONTACT3.glob("*.json"))
    ref_dir_ok = any(p.is_dir() and p.name.startswith("v") for p in DB_VCONTACT3.iterdir()) if DB_VCONTACT3.exists() else False
    return json_ok and ref_dir_ok


def _save_db_manifest(installed_ver: str) -> None:
    save_manifest(
        _MANIFEST,
        {
            "tool": "vcontact3",
            "tool_version": installed_ver,
            "db_dir": str(DB_VCONTACT3),
            "source": _DB_URL,
            "prepared_at": datetime.now().isoformat(timespec="seconds"),
        },
    )


def _extract_staged_tarballs() -> bool:
    """Extract any v*.tar.gz already present in the DB dir. Returns True if one extracted."""
    extracted = False
    for tarball in sorted(DB_VCONTACT3.glob("v*.tar.gz")):
        try:
            extract_tar_gz(tarball, DB_VCONTACT3)
            extracted = True
        except Exception as exc:
            logger.warning("Could not extract %s: %s", tarball.name, exc)
            tarball.unlink(missing_ok=True)
    return extracted


def _ensure_db(installed_ver: str) -> None:
    DB_VCONTACT3.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(_MANIFEST)

    if _db_ready():
        logger.info("vConTACT3 DB already present: %s", DB_VCONTACT3)
        if manifest is None:
            _save_db_manifest(installed_ver)
        return

    # 1) Use any already-staged tarball first (offline / pre-seeded installs).
    _extract_staged_tarballs()

    # 2) Otherwise fetch the prebuilt v230 reference DB from Zenodo, then extract.
    if not _db_ready():
        logger.info("Downloading vConTACT3 reference DB (v230) from Zenodo…")
        download_file(_DB_URL, DB_VCONTACT3 / _DB_TARBALL_NAME)
        _extract_staged_tarballs()

    if not _db_ready():
        raise RuntimeError(
            "vConTACT3 database is missing after download/extract. Expected a "
            f"'*.json' manifest and a 'v*/' reference directory under {DB_VCONTACT3}. "
            f"Re-run, or manually place v230.tar.gz there (from {_DB_URL})."
        )
    _save_db_manifest(installed_ver)


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
    _ensure_db(ver)
    logger.info("vConTACT3 installed: %s", ver)
    return ver
