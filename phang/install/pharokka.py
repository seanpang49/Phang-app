"""
Install and manage Pharokka + its database.

Conda env : ~/.phang/envs/pharokka  (Python 3.12)
Database  : ~/.phang/databases/pharokka_db/
Stamp file: ~/.phang/databases/pharokka_db/DB_MANIFEST.json
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from phang.config import DB_PHAROKKA, DB_MANIFEST_FILENAME, ENV_PHAROKKA, PYTHON_VERSIONS
from phang.install.common import (
    conda_install,
    create_env,
    env_exists,
    find_conda,
    get_installed_version,
    get_latest_bioconda_version,
    load_manifest,
    save_manifest,
    _run_conda,
)

logger = logging.getLogger(__name__)

_MANIFEST = DB_PHAROKKA / DB_MANIFEST_FILENAME


def ensure_pharokka() -> str:
    """
    Ensure Pharokka is installed and its database is current.

    Returns the installed Pharokka version string.
    """
    conda = find_conda()

    # --- Conda env ---
    if not env_exists(ENV_PHAROKKA):
        create_env(conda, ENV_PHAROKKA, PYTHON_VERSIONS["pharokka"])
        conda_install(conda, ENV_PHAROKKA, ["pharokka"])
    else:
        # Already installed — only update if version is unknown
        ver = get_installed_version(conda, ENV_PHAROKKA, "pharokka.py", "--version")
        if ver == "unknown":
            conda_install(conda, ENV_PHAROKKA, ["pharokka"])

    installed_ver = get_installed_version(conda, ENV_PHAROKKA, "pharokka.py", "--version")
    latest_ver = get_latest_bioconda_version(conda, "pharokka")
    logger.info("Pharokka installed: %s  |  latest bioconda: %s", installed_ver, latest_ver)

    # --- Database ---
    manifest = load_manifest(_MANIFEST)
    db_has_files = DB_PHAROKKA.exists() and any(
        p for p in DB_PHAROKKA.iterdir() if p.name != _MANIFEST.name
    ) if DB_PHAROKKA.exists() else False

    db_current = (
        db_has_files
        and manifest is not None
        and manifest.get("tool_version") == installed_ver
    )

    if db_current:
        logger.info("Pharokka DB is up to date — skipping download.")
    else:
        logger.info("Installing/updating Pharokka databases…")
        DB_PHAROKKA.mkdir(parents=True, exist_ok=True)
        _run_conda([
            conda, "run", "--no-capture-output", "-p", str(ENV_PHAROKKA),
            "install_databases.py", "-o", str(DB_PHAROKKA),
        ])
        save_manifest(
            _MANIFEST,
            {
                "tool": "pharokka",
                "tool_version": installed_ver,
                "latest_bioconda_version": latest_ver,
                "db_dir": str(DB_PHAROKKA),
                "downloaded_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        logger.info("Pharokka DB ready: %s", DB_PHAROKKA)

    return installed_ver
