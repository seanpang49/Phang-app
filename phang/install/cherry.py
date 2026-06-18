"""
Install and manage PhaBOX2 for Step 5 host prediction.

This keeps the legacy module/function name for compatibility, but the actual
runtime is PhaBOX2's maintained `--task cherry` workflow.

Conda env : ~/.phang/envs/phabox2
Database  : ~/.phang/databases/phabox_db_v2_1/
"""

from __future__ import annotations

import logging
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from phang.config import DB_CHERRY, DB_MANIFEST_FILENAME, ENV_CHERRY, PHANG_HOME, PYTHON_VERSIONS
from phang.install.common import (
    conda_install,
    create_env,
    download_file,
    env_exists,
    find_conda,
    get_installed_version,
    load_manifest,
    save_manifest,
)

logger = logging.getLogger(__name__)

_PHABOX_VERSION = "2.1.13"
_CORE_PACKAGES = [
    "diamond",
    "blast",
    "mcl",
    "prodigal-gv",
    "openjdk",
    "git",
    "kcounter",
]
_PY_PACKAGES = [
    "numpy",
    "pandas",
    "biopython",
    "tqdm",
    "datasets",
    "pyarrow",
    "torch",
    "transformers",
    "networkx",
    "matplotlib",
    "seaborn",
    "joblib",
    "scipy",
    "scikit-learn",
]
_DB_URL = "https://github.com/KennthShang/PhaBOX/releases/download/v2/phabox_db_v2_1.zip"
_DB_ARCHIVE = DB_CHERRY.parent / "phabox_db_v2_1.zip"
_MANIFEST = DB_CHERRY / DB_MANIFEST_FILENAME
_PHABOX_REPO = PHANG_HOME / "tools" / "phabox2"
_REPO_URL = "https://github.com/KennthShang/PhaBOX.git"
_REQUIRED_DB_PATHS = [
    "RefVirus.csv",
    "RefVirus.dmnd",
    "RefVirus.faa",
    "database_aai.tsv",
    "crispr_db",
    "cherry",
    "CRT1.2-CLI.jar",
]


def _missing_commands(conda: str, commands: Iterable[str]) -> List[str]:
    missing: List[str] = []
    script = (
        "import shutil, sys; "
        "cmd = sys.argv[1]; "
        "sys.exit(0 if shutil.which(cmd) else 1)"
    )
    for command in commands:
        cp = subprocess.run(
            [conda, "run", "--no-capture-output", "-p", str(ENV_CHERRY), "python", "-c", script, command],
            text=True,
            capture_output=True,
        )
        if cp.returncode != 0:
            missing.append(command)
    return missing


def _missing_python_modules(conda: str, modules: Iterable[str]) -> List[str]:
    missing: List[str] = []
    script = (
        "import importlib.util, sys; "
        "module = sys.argv[1]; "
        "sys.exit(0 if importlib.util.find_spec(module) else 1)"
    )
    for module in modules:
        cp = subprocess.run(
            [conda, "run", "--no-capture-output", "-p", str(ENV_CHERRY), "python", "-c", script, module],
            text=True,
            capture_output=True,
        )
        if cp.returncode != 0:
            missing.append(module)
    return missing


def _verify_install(conda: str) -> bool:
    try:
        cp = subprocess.run(
            [
                conda,
                "run",
                "--no-capture-output",
                "-p",
                str(ENV_CHERRY),
                "python",
                "-c",
                "import kcounter; import phabox2; import phabox2.phabox2; print(phabox2.phabox2.__version__)",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return False
    return bool(cp.stdout.strip())


def _installed_version(conda: str) -> str:
    for package_name in ("phabox2", "phabox"):
        version = get_installed_version(conda, ENV_CHERRY, package_name)
        if version != "unknown":
            return version
    return _PHABOX_VERSION if _verify_install(conda) else "unknown"


def _ensure_cli_tools(conda: str) -> None:
    tool_packages = {
        "diamond": "diamond",
        "blastn": "blast",
        "makeblastdb": "blast",
        "mcxload": "mcl",
        "mcl": "mcl",
        "prodigal-gv": "prodigal-gv",
        "java": "openjdk",
        "git": "git",
    }
    missing = _missing_commands(conda, tool_packages.keys())
    if not missing:
        return

    packages = sorted({tool_packages[name] for name in missing})
    logger.info("Installing missing PhaBOX2 CLI dependencies: %s", ", ".join(packages))
    conda_install(conda, ENV_CHERRY, packages)


def _clone_or_update_repo() -> None:
    if (_PHABOX_REPO / "src" / "phabox2" / "phabox2.py").exists():
        logger.info("PhaBOX2 repo already present: %s", _PHABOX_REPO)
        return

    _PHABOX_REPO.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Cloning PhaBOX2 repository → %s", _PHABOX_REPO)
    subprocess.run(["git", "clone", _REPO_URL, str(_PHABOX_REPO)], check=True)


def _install_python_runtime(conda: str) -> None:
    logger.info("Installing PhaBOX2 Python runtime into %s", ENV_CHERRY)
    subprocess.run(
        [conda, "run", "--no-capture-output", "-p", str(ENV_CHERRY), "python", "-m", "pip", "install", "--upgrade", "pip"],
        check=True,
    )
    subprocess.run(
        [conda, "run", "--no-capture-output", "-p", str(ENV_CHERRY), "python", "-m", "pip", "install", *_PY_PACKAGES],
        check=True,
    )
    subprocess.run(
        [conda, "run", "--no-capture-output", "-p", str(ENV_CHERRY), "python", "-m", "pip", "install", "."],
        cwd=str(_PHABOX_REPO),
        check=True,
    )


def _db_ready() -> bool:
    return DB_CHERRY.exists() and all((DB_CHERRY / rel).exists() for rel in _REQUIRED_DB_PATHS)


def _extract_db_archive() -> None:
    logger.info("Extracting PhaBOX2 database: %s", _DB_ARCHIVE.name)
    DB_CHERRY.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(_DB_ARCHIVE) as zf:
        zf.extractall(DB_CHERRY.parent)


def _rebuild_refvirus_diamond(conda: str) -> None:
    ref_faa = DB_CHERRY / "RefVirus.faa"
    if not ref_faa.exists():
        raise RuntimeError(f"PhaBOX2 DB is missing {ref_faa}")

    logger.info("Rebuilding RefVirus.dmnd with the local Diamond version for compatibility.")
    subprocess.run(
        [
            conda,
            "run",
            "--no-capture-output",
            "-p",
            str(ENV_CHERRY),
            "diamond",
            "makedb",
            "--in",
            str(ref_faa),
            "-d",
            str(DB_CHERRY / "RefVirus"),
            "--quiet",
        ],
        check=True,
    )


def _ensure_db(installed_ver: str) -> None:
    manifest = load_manifest(_MANIFEST)

    if _db_ready():
        if not (manifest or {}).get("diamond_refreshed"):
            _rebuild_refvirus_diamond(find_conda())
        if manifest is None:
            save_manifest(
                _MANIFEST,
                {
                    "tool": "phabox2",
                    "tool_version": installed_ver,
                    "db_dir": str(DB_CHERRY),
                    "archive": str(_DB_ARCHIVE),
                    "diamond_refreshed": True,
                    "prepared_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        elif not manifest.get("diamond_refreshed"):
            manifest["diamond_refreshed"] = True
            manifest["prepared_at"] = datetime.now().isoformat(timespec="seconds")
            save_manifest(_MANIFEST, manifest)
        return

    DB_CHERRY.parent.mkdir(parents=True, exist_ok=True)
    download_file(_DB_URL, _DB_ARCHIVE)
    _extract_db_archive()

    if not _db_ready():
        raise RuntimeError(
            f"PhaBOX2 database extraction completed but required files are missing in {DB_CHERRY}"
        )

    _rebuild_refvirus_diamond(find_conda())
    save_manifest(
        _MANIFEST,
        {
            "tool": "phabox2",
            "tool_version": installed_ver,
            "db_dir": str(DB_CHERRY),
            "archive": str(_DB_ARCHIVE),
            "diamond_refreshed": True,
            "prepared_at": datetime.now().isoformat(timespec="seconds"),
        },
    )


def ensure_cherry() -> str:
    """Ensure PhaBOX2 host-prediction env and DB are ready. Returns version."""
    conda = find_conda()

    if not env_exists(ENV_CHERRY):
        create_env(conda, ENV_CHERRY, PYTHON_VERSIONS["cherry"])
        conda_install(conda, ENV_CHERRY, _CORE_PACKAGES)
    else:
        _ensure_cli_tools(conda)
        if _missing_python_modules(conda, ["kcounter"]):
            logger.info("Installing missing PhaBOX2 conda runtime packages into %s", ENV_CHERRY)
            conda_install(conda, ENV_CHERRY, _CORE_PACKAGES)

    _clone_or_update_repo()
    if not _verify_install(conda):
        _install_python_runtime(conda)
    _ensure_cli_tools(conda)
    installed_ver = _installed_version(conda)
    _ensure_db(installed_ver)

    logger.info("PhaBOX2 ready: %s (DB: %s)", installed_ver, DB_CHERRY)
    return installed_ver
