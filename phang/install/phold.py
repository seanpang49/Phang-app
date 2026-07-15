"""
Install and manage Phold using its upstream-supported installer.

Conda env : ~/.phang/envs/phold  (Python 3.12)
Database  : ~/.phang/databases/phold_db/
Manifest  : ~/.phang/databases/phold_db/DB_MANIFEST.json
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from phang.config import DB_PHOLD, DB_MANIFEST_FILENAME, ENV_PHOLD, PYTHON_VERSIONS
from phang.install.common import (
    _run_conda,
    conda_install,
    create_env,
    env_exists,
    find_conda,
    get_installed_version,
    load_manifest,
    make_conda_cmd,
    save_manifest,
)

logger = logging.getLogger(__name__)

_MANIFEST = DB_PHOLD / DB_MANIFEST_FILENAME
_INSTALL_THREADS = 8
_PHOLD_DB_SENTINELS = (
    "acrs_plddt_over_70_metadata.tsv",
    "all_phold_structures",
)
_PHOLD_DB_DIRNAMES = ("phold_db_3M16_v_1_0_0", "phold_search_db_v_1_0_0")
_PHOLD_CACHE_DIRNAMES = ("models--Rostlab--ProstT5_fp16",)
_PHOLD_ARCHIVE_NAMES = (
    "phold_db_3M16_v_1_0_0.tar.gz",
    "phold_search_db_v_1_0_0.tar.gz",
    "models--Rostlab--ProstT5_fp16.tar.gz",
)


def _is_apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _install_phold(conda: str) -> None:
    if _is_apple_silicon():
        logger.info(
            "Apple Silicon detected. The phold README suggests a Python 3.13 + pytorch-channel "
            "install for GPU usage, but the current bioconda phold solve still resolves against "
            "Python 3.12 via pyrodigal-gv. Using the working bioconda install path here and "
            "letting phold use MPS at runtime when available."
        )
    conda_install(conda, ENV_PHOLD, ["phold"])


def _install_phold_assets(conda: str, threads: int = _INSTALL_THREADS) -> None:
    """
    Use the upstream installer to fetch the ProstT5 model and the phold DB.

    phold 1.2.2 already knows the correct download locations and DB layout.
    Delegating to `phold install` avoids brittle custom Zenodo metadata logic.

    Uses _run_conda (streaming) instead of conda_run (silent buffered) so that
    phold's multi-GB download progress is visible and large stdout is not
    accumulated in memory.  This also prevents apparent hangs on slow networks.
    """
    DB_PHOLD.mkdir(parents=True, exist_ok=True)
    logger.info("Installing phold assets with upstream installer into %s", DB_PHOLD)
    _run_conda(make_conda_cmd(conda, [
        "run", "--no-capture-output", "-p", str(ENV_PHOLD),
        "phold", "install", "-d", str(DB_PHOLD), "-t", str(threads),
    ]))


def _ensure_phold_pip_deps(conda: str) -> None:
    """Ensure the tokenizer backend libs phold needs but does not pull in itself.

    ProstT5's tokenizer is a SentencePiece model (``spiece.model``).  Loading it
    with ``transformers`` requires ``sentencepiece`` (the tokenizer itself) and
    ``protobuf`` (used by the slow->fast tokenizer conversion).  When they are
    missing, ``phold install`` aborts while loading the ProstT5 model — first
    misreporting it as a missing ``tiktoken`` file, then failing on the
    SentencePiece parse.  Neither is a declared phold/transformers dependency, so
    install them explicitly.  Idempotent — pip skips whatever is already present.
    """
    _run_conda(make_conda_cmd(conda, [
        "run", "--no-capture-output", "-p", str(ENV_PHOLD),
        "pip", "install", "sentencepiece", "protobuf",
    ]))


def _phold_search_roots() -> list[Path]:
    search_roots = [DB_PHOLD]
    for desktop_db in Path.home().glob("Desktop/*/phold/db"):
        if desktop_db.is_dir():
            search_roots.append(desktop_db)
    legacy = Path.home() / "Desktop" / "phold" / "db"
    if legacy.is_dir() and legacy not in search_roots:
        search_roots.append(legacy)
    return search_roots


def _db_has_runtime_assets(candidate: Path) -> bool:
    return candidate.is_dir() and all((candidate / name).exists() for name in _PHOLD_DB_SENTINELS)


def _iter_db_candidates(root: Path):
    if root.exists():
        yield root

    for candidate_name in _PHOLD_DB_DIRNAMES:
        candidate = root / candidate_name
        if candidate.exists():
            yield candidate

    if root.exists():
        for sub in sorted(root.iterdir()):
            if sub.is_dir():
                yield sub


def _find_phold_db_dir(*, require_runtime_assets: bool) -> Path:
    for root in _phold_search_roots():
        for candidate in _iter_db_candidates(root):
            if not candidate.is_dir():
                continue
            if require_runtime_assets:
                if _db_has_runtime_assets(candidate):
                    logger.debug("Using Phold DB: %s", candidate)
                    return candidate
            elif (candidate / "acrs_plddt_over_70_metadata.tsv").exists():
                logger.debug("Found Phold DB candidate: %s", candidate)
                return candidate

    raise RuntimeError(
        "Cannot find a valid Phold DB directory with all required runtime assets. "
        f"Searched: {[str(r) for r in _phold_search_roots()]}\n"
        "Run `phang run` to trigger automatic DB installation."
    )


def _cleanup_incomplete_phold_assets() -> None:
    targets = [
        *(DB_PHOLD / name for name in _PHOLD_DB_DIRNAMES),
        *(DB_PHOLD / name for name in _PHOLD_CACHE_DIRNAMES),
        *(DB_PHOLD / name for name in _PHOLD_ARCHIVE_NAMES),
    ]
    removed_any = False
    for path in targets:
        if not path.exists():
            continue
        removed_any = True
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    if removed_any:
        logger.warning(
            "Removed incomplete Phold assets under %s before reinstalling.",
            DB_PHOLD,
        )


def ensure_phold() -> str:
    """
    Ensure Phold is installed and its database is current.

    Returns the installed Phold version string.
    """
    conda = find_conda()
    desired_python = PYTHON_VERSIONS["phold"]

    # --- Conda env ---
    if not env_exists(ENV_PHOLD):
        create_env(conda, ENV_PHOLD, desired_python)
        _install_phold(conda)
    else:
        ver_check = get_installed_version(conda, ENV_PHOLD, "phold", "--version")
        if ver_check == "unknown":
            _install_phold(conda)

    installed_ver = get_installed_version(conda, ENV_PHOLD, "phold", "--version")
    logger.info("Phold installed: %s", installed_ver)

    # --- Database / model assets ---
    manifest = load_manifest(_MANIFEST)
    try:
        existing_db = find_phold_db_dir()
        if existing_db.exists():
            logger.info("Phold DB already present: %s", existing_db)
            if manifest is None:
                save_manifest(
                    _MANIFEST,
                    {
                        "tool": "phold",
                        "tool_version": installed_ver,
                        "db_dir": str(existing_db),
                        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )
            return installed_ver
    except RuntimeError:
        try:
            partial_db = _find_phold_db_dir(require_runtime_assets=False)
        except RuntimeError:
            partial_db = None
        if partial_db is not None and DB_PHOLD in partial_db.parents:
            logger.warning(
                "Detected incomplete Phold DB at %s; removing partial assets and reinstalling.",
                partial_db,
            )
            _cleanup_incomplete_phold_assets()

    try:
        _ensure_phold_pip_deps(conda)
        _install_phold_assets(conda)
        installed_db = find_phold_db_dir()
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"phold install failed with exit code {exc.returncode}") from exc
    except Exception as exc:
        raise RuntimeError(f"Unable to install phold assets: {exc}") from exc

    save_manifest(
        _MANIFEST,
        {
            "tool": "phold",
            "tool_version": installed_ver,
            "db_dir": str(installed_db),
            "install_method": "phold install",
            "downloaded_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    logger.info("Phold DB ready: %s", installed_db)

    return installed_ver


def find_phold_db_dir() -> Path:
    """
    Return the actual phold DB subdirectory (the one containing metadata TSVs).

    Phold expects `-d` to point at the folder with `acrs_plddt_over_70_metadata.tsv`,
    not the root DB_PHOLD directory.

    Search order:
      1. ~/.phang/databases/phold_db/ (canonical location)
      2. ~/Desktop/*/phold/db/ (existing Desktop installations)
    """
    return _find_phold_db_dir(require_runtime_assets=True)
