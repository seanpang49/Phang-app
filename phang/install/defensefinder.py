"""
Install DefenseFinder for antidefense-system detection.

Conda env : ~/.phang/envs/defensefinder
Models    : ~/.phang/databases/defensefinder_models/
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path

from phang.config import (
    DB_DEFENSEFINDER_MODELS,
    DB_MANIFEST_FILENAME,
    ENV_DEFENSEFINDER,
    PYTHON_VERSIONS,
)
from phang.install.common import (
    conda_install,
    create_env,
    env_exists,
    find_conda,
    get_installed_version,
    load_manifest,
    save_manifest,
)

logger = logging.getLogger(__name__)

_CORE_PACKAGES = ["hmmer", "prodigal", "git"]
_MANIFEST = DB_DEFENSEFINDER_MODELS / DB_MANIFEST_FILENAME
_INSTALL_SPEC = "git+https://github.com/mdmparis/defense-finder.git"


def _models_ready() -> bool:
    return (
        (DB_DEFENSEFINDER_MODELS / "defense-finder-models").exists()
        and (DB_DEFENSEFINDER_MODELS / "CasFinder").exists()
    )


def _verify_cli(conda: str) -> bool:
    try:
        subprocess.run(
            [
                conda,
                "run",
                "--no-capture-output",
                "-p",
                str(ENV_DEFENSEFINDER),
                "defense-finder",
                "version",
            ],
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return False
    return True


def _install_package(conda: str) -> None:
    logger.info("Installing DefenseFinder from GitHub into %s", ENV_DEFENSEFINDER)
    subprocess.run(
        [
            conda,
            "run",
            "--no-capture-output",
            "-p",
            str(ENV_DEFENSEFINDER),
            "python",
            "-m",
            "pip",
            "install",
            _INSTALL_SPEC,
        ],
        check=True,
    )


def _update_models(conda: str) -> None:
    logger.info("Downloading DefenseFinder models into %s", DB_DEFENSEFINDER_MODELS)
    subprocess.run(
        [
            conda,
            "run",
            "--no-capture-output",
            "-p",
            str(ENV_DEFENSEFINDER),
            "defense-finder",
            "update",
            "--models-dir",
            str(DB_DEFENSEFINDER_MODELS),
        ],
        check=True,
    )


def ensure_defensefinder() -> str:
    """Ensure DefenseFinder env and models are ready. Returns version."""
    conda = find_conda()

    if not env_exists(ENV_DEFENSEFINDER):
        create_env(conda, ENV_DEFENSEFINDER, PYTHON_VERSIONS["defensefinder"])
        conda_install(conda, ENV_DEFENSEFINDER, _CORE_PACKAGES)

    if not _verify_cli(conda):
        _install_package(conda)

    if not _models_ready():
        _update_models(conda)

    version = get_installed_version(conda, ENV_DEFENSEFINDER, "mdmparis-defense-finder")
    manifest = load_manifest(_MANIFEST)
    if manifest is None or manifest.get("tool_version") != version:
        save_manifest(
            _MANIFEST,
            {
                "tool": "defensefinder",
                "tool_version": version,
                "models_dir": str(DB_DEFENSEFINDER_MODELS),
                "prepared_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    logger.info("DefenseFinder ready: %s (models: %s)", version, DB_DEFENSEFINDER_MODELS)
    return version
