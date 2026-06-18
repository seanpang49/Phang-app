"""
Install DepoScope.

Conda env : ~/.phang/envs/deposcope  (Python 3.10)
Model     : downloaded from Zenodo (https://zenodo.org/records/10957073)
            stored at ~/.phang/databases/deposcope_model/

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

from phang.config import (
    DB_DIR,
    DB_MANIFEST_FILENAME,
    ENV_DEPOSCOPE,
    ENV_PHANOTATE,
    PHANG_HOME,
    PYTHON_VERSIONS,
)
from phang.install.common import (
    _run_conda,
    conda_install,
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
_DEPOSCOPE_SCRIPT_DIR = PHANG_HOME / "tools" / "deposcope"
_DEPOSCOPE_MODEL_DIR = DB_DIR / "deposcope_model"
_MANIFEST = _DEPOSCOPE_MODEL_DIR / DB_MANIFEST_FILENAME
_REPO_URL = "https://github.com/dimiboeckaerts/DepoScope.git"
_MODEL_URLS = {
    "esm2_t12_finetuned_depolymerases.zip": "https://zenodo.org/records/10957073/files/esm2_t12_finetuned_depolymerases.zip",
    "Deposcope.esm2_t12_35M_UR50D.2203.full.model": "https://zenodo.org/records/10957073/files/Deposcope.esm2_t12_35M_UR50D.2203.full.model",
}


def _script_ready() -> bool:
    return (_DEPOSCOPE_SCRIPT_DIR / "deposcope-predict.py").exists()


def _model_ready() -> bool:
    checkpoint_dir = (
        _DEPOSCOPE_MODEL_DIR
        / "esm2_t12_35M_UR50D__fulltrain__finetuneddepolymerase.2103.4_labels"
        / "checkpoint-2255"
    )
    model_file = _DEPOSCOPE_MODEL_DIR / "Deposcope.esm2_t12_35M_UR50D.2203.full.model"
    return checkpoint_dir.exists() and model_file.exists()


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


def _find_cached_model_root() -> Path | None:
    target = _DEPOSCOPE_MODEL_DIR.resolve(strict=False)
    checkpoint_rel = (
        "esm2_t12_35M_UR50D__fulltrain__finetuneddepolymerase.2103.4_labels/checkpoint-2255"
    )
    model_name = "Deposcope.esm2_t12_35M_UR50D.2203.full.model"
    for root in _candidate_search_roots():
        direct_candidates = [
            root / "deposcope_model",
            root / "databases" / "deposcope_model",
            root / "seanpang__.phang" / "databases" / "deposcope_model",
        ]
        recursive_patterns = [
            "*/databases/deposcope_model",
            "*/deposcope_model",
            "*/Deposcope*",
        ]
        for candidate in chain(
            direct_candidates,
            *(root.glob(pattern) for pattern in recursive_patterns),
        ):
            if not candidate.is_dir():
                continue
            try:
                resolved = candidate.resolve(strict=False)
            except Exception:
                resolved = candidate
            if resolved == target:
                continue
            if (candidate / checkpoint_rel).exists() and (candidate / model_name).exists():
                return candidate
    return None


def _ensure_repo() -> None:
    if _script_ready():
        return
    if not shutil.which("git"):
        raise RuntimeError(
            "git is not available on PATH. "
            "Install git (https://git-scm.com/downloads) and re-run phang."
        )
    _DEPOSCOPE_SCRIPT_DIR.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", _REPO_URL, str(_DEPOSCOPE_SCRIPT_DIR)], check=True)


def get_deposcope_model_paths() -> tuple[Path, Path]:
    esm2_parent = (
        _DEPOSCOPE_MODEL_DIR
        / "esm2_t12_35M_UR50D__fulltrain__finetuneddepolymerase.2103.4_labels"
    )
    esm2_dir = esm2_parent
    if esm2_parent.exists():
        for child in sorted(esm2_parent.iterdir()):
            if child.is_dir() and (child / "vocab.txt").exists():
                esm2_dir = child
                break

    dpo_model = _DEPOSCOPE_MODEL_DIR / "Deposcope.esm2_t12_35M_UR50D.2203.full.model"
    if not esm2_dir.exists() or not dpo_model.exists():
        raise RuntimeError(
            "DepoScope model assets are not installed. "
            f"Expected ESM2 checkpoint under {esm2_parent} and classifier at {dpo_model}"
        )
    return esm2_dir, dpo_model


def _ensure_model() -> None:
    if _model_ready():
        if load_manifest(_MANIFEST) is None:
            save_manifest(
                _MANIFEST,
                {
                    "tool": "deposcope",
                    "model_dir": str(_DEPOSCOPE_MODEL_DIR),
                    "downloaded_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        return

    _DEPOSCOPE_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for filename, url in _MODEL_URLS.items():
            out_path = _DEPOSCOPE_MODEL_DIR / filename
            download_file(url, out_path)
            if filename.endswith(".zip"):
                shutil.unpack_archive(str(out_path), str(_DEPOSCOPE_MODEL_DIR))
                out_path.unlink(missing_ok=True)  # free disk space after extraction
    except Exception as exc:
        cached = _find_cached_model_root()
        if cached is None:
            raise RuntimeError(
                "Unable to download the DepoScope model files from Zenodo and no local cached "
                f"model directory was found. Last error: {exc}"
            ) from exc
        logger.warning(
            "Falling back to cached DepoScope model directory at %s after download failure: %s",
            cached,
            exc,
        )
        shutil.copytree(cached, _DEPOSCOPE_MODEL_DIR, dirs_exist_ok=True)
    save_manifest(
        _MANIFEST,
        {
            "tool": "deposcope",
            "model_dir": str(_DEPOSCOPE_MODEL_DIR),
            "downloaded_at": datetime.now().isoformat(timespec="seconds"),
        },
    )


def _phanotate_works(conda: str) -> bool:
    """True if phanotate's C-extensions import in the dedicated env (right arch)."""
    try:
        cp = subprocess.run(
            make_conda_cmd(conda, [
                "run", "--no-capture-output", "-p", str(ENV_PHANOTATE),
                "python", "-c", "import fastpathz, fastpath",
            ]),
            text=True, capture_output=True,
        )
        return cp.returncode == 0
    except Exception:
        return False


def _ensure_phanotate_env(conda: str) -> None:
    """
    Create a dedicated phanotate env (bioconda, native arch).

    DepoScope's vendored predict script shells out to ``phanotate.py``. The only
    native-arm64 phanotate build is bioconda's py3.9 package, which is
    incompatible with the py3.10 deposcope env, so phanotate gets its own env and
    is placed on PATH at run time (see steps/s08_deposcope.py).
    """
    if env_exists(ENV_PHANOTATE) and _phanotate_works(conda):
        logger.info("phanotate env already present: %s", ENV_PHANOTATE)
        return
    if not env_exists(ENV_PHANOTATE):
        create_env(conda, ENV_PHANOTATE, PYTHON_VERSIONS["phanotate"])
    conda_install(conda, ENV_PHANOTATE, ["phanotate"])


def _purge_broken_phanotate(conda: str) -> None:
    """
    Remove any phanotate pip-installed into the deposcope env.

    Older installs pip-installed phanotate (plus its fastpathz/fastpath
    C-extensions) directly into the deposcope env; on Apple Silicon those wheels
    are x86_64 and fail to import, so phanotate.py exits 1 with empty output. We
    now use the dedicated arm64 phanotate env (placed on PATH at run time), but
    ``conda run -p deposcope`` resolves the deposcope env's bin first — so a
    phanotate.py left there would shadow the good one. Remove it. No-op if absent.

    Detection is by the bin script, not an import check: phanotate's import
    package is ``phanotate_modules`` (not ``phanotate``), so importlib would miss it.
    """
    script = ENV_DEPOSCOPE / "bin" / "phanotate.py"
    if not script.exists():
        return
    logger.info("Removing x86_64 phanotate from the deposcope env (using the dedicated env now).")
    subprocess.run(
        make_conda_cmd(conda, [
            "run", "--no-capture-output", "-p", str(ENV_DEPOSCOPE),
            "pip", "uninstall", "-y", "phanotate", "fastpathz", "fastpath",
        ]),
        text=True, capture_output=True,
    )
    # Belt-and-suspenders: drop any console scripts pip left behind.
    for leftover in ("phanotate.py", "phanotate"):
        try:
            (ENV_DEPOSCOPE / "bin" / leftover).unlink()
        except FileNotFoundError:
            pass


def ensure_deposcope() -> str:
    """Ensure DepoScope env is ready. Returns status string."""
    conda = find_conda()

    _torch_args = get_torch_pip_args()
    # NOTE: phanotate is intentionally NOT installed here — its fastpathz/fastpath
    # C-extensions have no arm64 wheel, so a pip install yields x86_64 binaries
    # that fail to import on Apple Silicon. phanotate lives in its own env
    # (_ensure_phanotate_env) and is put on PATH at run time instead.
    _pip_packages = [
        *_torch_args,
        "fair-esm", "biopython",
        "transformers", "tqdm", "pandas", "scikit-learn",
        "setuptools<72", "protobuf", "sentencepiece",
    ]

    if not env_exists(ENV_DEPOSCOPE):
        create_env(conda, ENV_DEPOSCOPE, PYTHON_VERSIONS["deposcope"])
        # Core deps + setuptools<72 (pkg_resources removed in >=72, needed by phanotate)
        # + protobuf + sentencepiece (needed by ESM-2 tokenizer)
        # torch args are platform-aware: CUDA index URL on Windows for NVIDIA GPU support.
        _run_conda(make_conda_cmd(conda, [
            "run", "--no-capture-output", "-p", str(ENV_DEPOSCOPE),
            "pip", "install", *_pip_packages,
        ]))
    else:
        cp = subprocess.run(
            make_conda_cmd(conda, [
                "run", "--no-capture-output", "-p", str(ENV_DEPOSCOPE),
                "python", "-c", "import transformers, torch, Bio, pandas; print('OK')",
            ]),
            text=True,
            capture_output=True,
        )
        if cp.returncode != 0:
            _run_conda(make_conda_cmd(conda, [
                "run", "--no-capture-output", "-p", str(ENV_DEPOSCOPE),
                "pip", "install", *_pip_packages,
            ]))

    _ensure_phanotate_env(conda)
    _purge_broken_phanotate(conda)
    _ensure_repo()
    _ensure_model()

    logger.info("DepoScope env ready: %s", ENV_DEPOSCOPE)
    return "ready"
