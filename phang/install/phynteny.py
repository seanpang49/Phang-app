"""
Install and manage Phynteny (phynteny_transformer) + pretrained models.

Conda env : ~/.phang/envs/phynteny  (Python 3.9 — required for ARM PyTorch)
Models    : ~/.phang/databases/phynteny_models/
Manifest  : ~/.phang/databases/phynteny_models/DB_MANIFEST.json
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path

from phang.config import DB_PHYNTENY_MODELS, DB_MANIFEST_FILENAME, ENV_PHYNTENY, PYTHON_VERSIONS
from phang.install.common import (
    _run_conda,
    conda_install,
    create_env,
    env_exists,
    find_conda,
    get_installed_version,
    get_latest_bioconda_version,
    load_manifest,
    make_conda_cmd,
    save_manifest,
)

logger = logging.getLogger(__name__)

_MANIFEST = DB_PHYNTENY_MODELS / DB_MANIFEST_FILENAME


def get_phynteny_models_dir() -> Path:
    """Return the directory that should be passed to ``-m`` at runtime."""
    nested = DB_PHYNTENY_MODELS / "models"
    return nested if nested.exists() else DB_PHYNTENY_MODELS


def _models_present() -> bool:
    """Return True if the runtime models directory contains real model files."""
    models_dir = get_phynteny_models_dir()
    if not models_dir.exists():
        return False
    required = [
        "category_mapping.pkl",
        "calibration_models.pkl",
    ]
    if not all((models_dir / name).exists() for name in required):
        return False
    return any(models_dir.glob("fold_*transformer.model"))


def _upgrade_transformers(conda: str) -> None:
    """Upgrade transformers to a version that includes EsmModel (>=4.24.0).

    Bioconda's phynteny_transformer pulls in transformers~=4.19 which lacks
    EsmModel.  Pinning <5.0.0 avoids the breaking API change in 5.x.
    """
    logger.info("Ensuring transformers>=4.20.0,<5.0.0 in phynteny env…")
    _run_conda(make_conda_cmd(conda, [
        "run", "--no-capture-output", "-p", str(ENV_PHYNTENY),
        "pip", "install", "transformers>=4.20.0,<5.0.0",
    ]))


def ensure_phynteny() -> str:
    """
    Ensure phynteny_transformer is installed and models are downloaded.

    Returns the installed version string.
    """
    conda = find_conda()

    # --- Conda env ---
    # Phynteny needs Python 3.9 due to PyTorch ARM compatibility.
    # Bioconda's phynteny_transformer pulls in transformers~=4.19 which lacks
    # EsmModel (added in 4.24.0).  We upgrade transformers after every conda
    # install to ensure >=4.24.0 while staying below the breaking 5.0 API.
    if not env_exists(ENV_PHYNTENY):
        create_env(conda, ENV_PHYNTENY, PYTHON_VERSIONS["phynteny"])
        conda_install(conda, ENV_PHYNTENY, ["phynteny_transformer"])
        _upgrade_transformers(conda)
    else:
        ver_check = get_installed_version(conda, ENV_PHYNTENY, "phynteny_transformer")
        if ver_check == "unknown":
            # Try in-place install; if it fails (dependency conflict), recreate env
            try:
                conda_install(conda, ENV_PHYNTENY, ["phynteny_transformer"])
                _upgrade_transformers(conda)
            except subprocess.CalledProcessError:
                logger.warning(
                    "In-place phynteny_transformer install failed (likely dependency conflict). "
                    "Recreating conda env…"
                )
                import shutil
                shutil.rmtree(ENV_PHYNTENY, ignore_errors=True)
                create_env(conda, ENV_PHYNTENY, PYTHON_VERSIONS["phynteny"])
                conda_install(conda, ENV_PHYNTENY, ["phynteny_transformer"])
                _upgrade_transformers(conda)
        else:
            # Env exists and package is present — still ensure transformers is
            # at a working version (covers users who installed before this fix).
            _upgrade_transformers(conda)

    installed_ver = get_installed_version(conda, ENV_PHYNTENY, "phynteny_transformer")
    latest_ver = get_latest_bioconda_version(conda, "phynteny_transformer")
    logger.info(
        "phynteny_transformer installed: %s  |  latest bioconda: %s",
        installed_ver, latest_ver,
    )

    # --- Models ---
    manifest = load_manifest(_MANIFEST)
    models_current = (
        _models_present()
        and manifest is not None
        and manifest.get("tool_version") == installed_ver
    )

    if models_current:
        logger.info("Phynteny models are up to date — skipping download.")
    else:
        logger.info("Downloading Phynteny pretrained models…")
        DB_PHYNTENY_MODELS.mkdir(parents=True, exist_ok=True)
        _run_conda([
            conda, "run", "--no-capture-output", "-p", str(ENV_PHYNTENY),
            "install_models", "-o", str(DB_PHYNTENY_MODELS),
        ])
        if not _models_present():
            raise RuntimeError(
                f"Phynteny models were not installed correctly under {DB_PHYNTENY_MODELS}"
            )
        save_manifest(
            _MANIFEST,
            {
                "tool": "phynteny_transformer",
                "tool_version": installed_ver,
                "latest_bioconda_version": latest_ver,
                "models_dir": str(get_phynteny_models_dir()),
                "downloaded_at": datetime.now().isoformat(timespec="seconds"),
            },
        )
        logger.info("Phynteny models ready: %s", get_phynteny_models_dir())

    return installed_ver
