"""
Install and manage ProkBERT PhaStyle.

Strategy: git clone the PhaStyle repository into ~/.phang/tools/phastyle/,
then create a conda env at ~/.phang/envs/phastyle with ProkBERT + dependencies.

No separate database — HuggingFace model weights are downloaded on first inference.

Conda env : ~/.phang/envs/phastyle  (Python 3.12)
Repo dir  : ~/.phang/tools/phastyle/
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from phang.config import PHANG_HOME, ENV_PHASTYLE, PYTHON_VERSIONS
from phang.install.common import (
    _run_conda,
    conda_install,
    create_env,
    env_exists,
    find_conda,
    load_manifest,
    make_conda_cmd,
    save_manifest,
)

logger = logging.getLogger(__name__)

_REPO_URL = "https://github.com/nbrg-ppcu/PhaStyle/"
_TOOLS_DIR = PHANG_HOME / "tools"
_PHASTYLE_DIR = _TOOLS_DIR / "phastyle"
_MANIFEST = ENV_PHASTYLE.parent / "phastyle_manifest.json"
_WORKSPACE_PHASTYLE_DIR = Path(__file__).resolve().parents[3] / "PhaStyle"


def _git_available() -> bool:
    return shutil.which("git") is not None


def _clone_or_update_repo() -> None:
    """Clone PhaStyle repo, or skip if already present."""
    _TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    if (_PHASTYLE_DIR / "bin" / "PhaStyle.py").exists():
        logger.info("PhaStyle repo already cloned at %s — skipping clone.", _PHASTYLE_DIR)
        return

    if (_WORKSPACE_PHASTYLE_DIR / "bin" / "PhaStyle.py").exists():
        logger.info("Copying bundled PhaStyle repo → %s", _PHASTYLE_DIR)
        shutil.copytree(_WORKSPACE_PHASTYLE_DIR, _PHASTYLE_DIR, dirs_exist_ok=True)
        return

    if not _git_available():
        raise RuntimeError(
            "git is not available on PATH. "
            "Install git to allow PhaStyle repository cloning."
        )

    logger.info("Cloning PhaStyle repository → %s", _PHASTYLE_DIR)
    subprocess.run(
        ["git", "clone", _REPO_URL, str(_PHASTYLE_DIR)],
        check=True,
    )


def _install_python_deps(conda: str) -> None:
    """Install ProkBERT and its dependencies into the phastyle env via pip.

    prokbert is installed from its GitHub source via a git+https URL, which
    requires git to be available inside the conda environment.  We ensure git
    is present in the env before attempting the pip install.
    """
    logger.info("Installing ProkBERT and dependencies…")
    # Ensure git is available in the env so pip can clone the prokbert repo.
    conda_install(conda, ENV_PHASTYLE, ["git"])
    # transformers>=5.0.0 removed the `tokenizer` kwarg from Trainer.__init__,
    # which PhaStyle.py still uses.  Pin <5.0.0 until upstream is updated.
    for pkg in [
        "git+https://github.com/nbrg-ppcu/prokbert.git",
        "transformers<5.0.0",
        "datasets",
    ]:
        _run_conda(make_conda_cmd(conda, [
            "run", "--no-capture-output", "-p", str(ENV_PHASTYLE),
            "pip", "install", pkg,
        ]))


def _patch_phastyle_script() -> None:
    """Patch known upstream script issues needed for non-interactive CLI use."""
    script = get_phastyle_script()
    text = script.read_text(encoding="utf-8")
    if "import argparse" not in text:
        text = "import argparse\n" + text
        script.write_text(text, encoding="utf-8")
        logger.info("Patched PhaStyle.py to add missing argparse import: %s", script)


def _verify_install(conda: str) -> bool:
    """Return True if core packages are importable inside the phastyle env."""
    try:
        result = subprocess.run(
            make_conda_cmd(conda, [
                "run", "--no-capture-output", "-p", str(ENV_PHASTYLE),
                "python", "-c",
                "import prokbert; import transformers; import datasets; print('OK')",
            ]),
            check=True, capture_output=True, text=True,
        )
        return "OK" in result.stdout
    except subprocess.CalledProcessError:
        return False


def ensure_phastyle() -> str:
    """
    Ensure PhaStyle repo is cloned and its conda env is ready.

    Returns a status string (no versioned package — using git HEAD).
    """
    conda = find_conda()

    # --- Repo ---
    _clone_or_update_repo()
    _patch_phastyle_script()

    # --- Conda env ---
    if not env_exists(ENV_PHASTYLE):
        create_env(conda, ENV_PHASTYLE, PYTHON_VERSIONS["phastyle"])
        _install_python_deps(conda)
    else:
        if not _verify_install(conda):
            _install_python_deps(conda)

    # --- Verify ---
    ok = _verify_install(conda)
    if not ok:
        raise RuntimeError(
            "PhaStyle installation verification failed — "
            "prokbert/transformers/datasets not importable in phastyle env."
        )

    save_manifest(
        _MANIFEST,
        {
            "tool": "phastyle",
            "repo_url": _REPO_URL,
            "repo_dir": str(_PHASTYLE_DIR),
            "env_dir": str(ENV_PHASTYLE),
            "installed_at": datetime.now().isoformat(timespec="seconds"),
        },
    )

    logger.info("PhaStyle ready. Repo: %s", _PHASTYLE_DIR)
    return "git-head"


def get_phastyle_script() -> Path:
    """Return path to the PhaStyle.py inference script."""
    candidates = [
        _PHASTYLE_DIR / "bin" / "PhaStyle.py",
        _PHASTYLE_DIR / "PhaStyle.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise RuntimeError(
        f"PhaStyle.py script not found in {_PHASTYLE_DIR}. "
        "Was the repository cloned correctly?"
    )
