"""
Install PhageRBPdetect v4.

Conda env : ~/.phang/envs/rbpdetect  (Python 3.10)
Model     : downloaded from Zenodo (https://zenodo.org/records/14810759)
            stored at ~/.phang/databases/rbpdetect_model/

TODO: implement model download + inference script setup.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from itertools import chain
from datetime import datetime
from pathlib import Path
from typing import Iterable

from phang.config import DB_DIR, DB_MANIFEST_FILENAME, ENV_RBPDETECT, PHANG_HOME, PYTHON_VERSIONS
from phang.install.common import (
    _run_conda,
    create_env,
    download_file,
    env_exists,
    find_conda,
    get_torch_pip_args,
    load_manifest,
    make_conda_cmd,
    save_manifest,
)

logger = logging.getLogger(__name__)
_RBP_SCRIPT_DIR = PHANG_HOME / "tools" / "rbpdetect"
_RBP_MODEL_DIR = DB_DIR / "rbpdetect_model"
_MANIFEST = _RBP_MODEL_DIR / DB_MANIFEST_FILENAME
_MODEL_URL = "https://zenodo.org/records/14811426/files/RBPdetect_v4_ESMfine.zip"


def _bundled_script_path() -> Path:
    return Path(__file__).with_name("rbpdetect_inference.py")


def _script_ready() -> bool:
    if _bundled_script_path().exists():
        return True
    return any(_RBP_SCRIPT_DIR.rglob("*inference*.py"))


def _model_ready() -> bool:
    return (_RBP_MODEL_DIR / "RBPdetect_v4_ESMfine" / "config.json").exists()


def _candidate_search_roots() -> Iterable[Path]:
    repo_workspace = Path(__file__).resolve().parents[3]
    desktop = Path.home() / "Desktop"
    roots = [
        repo_workspace / "_installer_validation_backup_2026-03-16",
        repo_workspace,
        desktop / "Phang genomics pipeline" / "_installer_validation_backup_2026-03-16",
        desktop / "Phang genomics pipeline",
        Path.home() / ".phang" / "databases",
        desktop,
        Path.home(),
    ]
    seen: set[Path] = set()
    for root in roots:
        if root.exists() and root not in seen:
            seen.add(root)
            yield root


def _find_cached_model_dir() -> Path | None:
    target = (_RBP_MODEL_DIR / "RBPdetect_v4_ESMfine").resolve(strict=False)
    for root in _candidate_search_roots():
        direct_candidates = [
            root / "rbpdetect_model" / "RBPdetect_v4_ESMfine",
            root / "databases" / "rbpdetect_model" / "RBPdetect_v4_ESMfine",
            root / "seanpang__.phang" / "databases" / "rbpdetect_model" / "RBPdetect_v4_ESMfine",
        ]
        recursive_patterns = [
            "*/databases/rbpdetect_model/RBPdetect_v4_ESMfine",
            "*/rbpdetect_model/RBPdetect_v4_ESMfine",
            "*/RBPdetect_v4_ESMfine",
        ]
        for candidate in chain(
            direct_candidates,
            *(root.glob(pattern) for pattern in recursive_patterns),
        ):
            try:
                resolved = candidate.resolve(strict=False)
            except Exception:
                resolved = candidate
            if resolved == target:
                continue
            if (candidate / "config.json").exists():
                return candidate
    return None


def _ensure_repo() -> None:
    if _script_ready():
        return
    raise RuntimeError(f"Bundled PhageRBPdetect inference wrapper not found at {_bundled_script_path()}")


def get_rbpdetect_script() -> Path:
    """Return the preferred v4 inference script path."""
    bundled = _bundled_script_path()
    if bundled.exists():
        return bundled
    candidates = [
        _RBP_SCRIPT_DIR / "PhageRBPdetect_v4_inference.py",
        _RBP_SCRIPT_DIR / "PhageRBPdetect_v4" / "PhageRBPdetect_v4_inference.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    for candidate in _RBP_SCRIPT_DIR.rglob("PhageRBPdetect_v4_inference.py"):
        return candidate
    raise RuntimeError(f"PhageRBPdetect v4 inference script not found under {_RBP_SCRIPT_DIR}")


def get_rbpdetect_model_dir() -> Path:
    model_dir = _RBP_MODEL_DIR / "RBPdetect_v4_ESMfine"
    if (model_dir / "config.json").exists():
        return model_dir
    raise RuntimeError(
        "PhageRBPdetect model is not installed. "
        f"Expected config.json under {model_dir}"
    )


def _ensure_model() -> None:
    if _model_ready():
        if load_manifest(_MANIFEST) is None:
            save_manifest(
                _MANIFEST,
                {
                    "tool": "rbpdetect",
                    "model_dir": str(_RBP_MODEL_DIR / "RBPdetect_v4_ESMfine"),
                    "downloaded_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        return

    _RBP_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = _RBP_MODEL_DIR / "RBPdetect_v4_ESMfine.zip"
    try:
        download_file(_MODEL_URL, zip_path)
        shutil.unpack_archive(str(zip_path), str(_RBP_MODEL_DIR))
        zip_path.unlink(missing_ok=True)  # free disk space after extraction
    except Exception as exc:
        cached = _find_cached_model_dir()
        if cached is None:
            raise RuntimeError(
                "Unable to download the PhageRBPdetect model from Zenodo and no local cached "
                f"model directory was found. Last error: {exc}"
            ) from exc
        logger.warning(
            "Falling back to cached PhageRBPdetect model at %s after download failure: %s",
            cached,
            exc,
        )
        shutil.copytree(cached, _RBP_MODEL_DIR / "RBPdetect_v4_ESMfine", dirs_exist_ok=True)
    save_manifest(
        _MANIFEST,
        {
            "tool": "rbpdetect",
            "model_dir": str(_RBP_MODEL_DIR / "RBPdetect_v4_ESMfine"),
            "downloaded_at": datetime.now().isoformat(timespec="seconds"),
        },
    )


def ensure_rbpdetect() -> str:
    """Ensure PhageRBPdetect env is ready. Returns status string."""
    conda = find_conda()

    _torch_args = get_torch_pip_args()
    _pip_packages = [*_torch_args, "fair-esm", "scikit-learn", "biopython", "transformers", "pandas"]

    if not env_exists(ENV_RBPDETECT):
        create_env(conda, ENV_RBPDETECT, PYTHON_VERSIONS["rbpdetect"])
        # torch args are platform-aware: CUDA index URL on Windows for NVIDIA GPU support.
        _run_conda(make_conda_cmd(conda, [
            "run", "--no-capture-output", "-p", str(ENV_RBPDETECT),
            "pip", "install", *_pip_packages,
        ]))
    else:
        cp = subprocess.run(
            make_conda_cmd(conda, [
                "run", "--no-capture-output", "-p", str(ENV_RBPDETECT),
                "python", "-c", "import transformers, torch, Bio, pandas; print('OK')",
            ]),
            text=True,
            capture_output=True,
        )
        if cp.returncode != 0:
            _run_conda(make_conda_cmd(conda, [
                "run", "--no-capture-output", "-p", str(ENV_RBPDETECT),
                "pip", "install", *_pip_packages,
            ]))

    _ensure_repo()
    get_rbpdetect_script()
    _ensure_model()

    logger.info("PhageRBPdetect env ready: %s", ENV_RBPDETECT)
    return "ready"
