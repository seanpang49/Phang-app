"""
Shared helpers for all tool installers.

Covers:
- conda detection and env management
- version querying (bioconda search, installed version)
- Zenodo API + file download
- DB manifest read/write
- tar.gz extraction
"""

from __future__ import annotations

import json
import logging
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Zenodo's CDN blocks browser-spoofed UAs from non-browser HTTP clients.
# Using a python-requests-style UA is accepted and does not trigger bot-detection.
_USER_AGENT = "python-requests/2.31.0"
_CONDA_CHANNELS = ["-c", "conda-forge", "-c", "bioconda"]

# Socket idle timeout (seconds) — not total download time.
# Large model files can be several GB; 300s covers slow connections between chunks.
_DOWNLOAD_TIMEOUT = 300
_DOWNLOAD_MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Conda helpers
# ---------------------------------------------------------------------------

def find_conda() -> str:
    """Return path to conda executable, preferring conda over mamba.

    On Windows, prefer .exe variants so subprocess can invoke them directly
    without needing cmd.exe /c; mamba can trigger macOS codesigning errors.
    """
    if sys.platform == "win32":
        candidates = ("conda.exe", "conda", "mamba.exe", "mamba")
    else:
        candidates = ("conda", "mamba")

    for name in candidates:
        path = shutil.which(name)
        if path:
            logger.debug("Using conda executable: %s", path)
            return path
    raise RuntimeError(
        "Neither 'conda' nor 'mamba' was found on PATH.\n"
        "Install Miniconda or Miniforge and ensure it is on PATH before running phang."
    )


def make_conda_cmd(conda: str, args: List[str]) -> List[str]:
    """Build the full conda invocation for the current platform.

    On Windows, .bat/.cmd conda wrappers cannot be executed directly by
    subprocess without shell=True.  Wrap them through cmd.exe instead.
    """
    if sys.platform == "win32" and conda.lower().endswith((".bat", ".cmd")):
        return ["cmd", "/c", conda] + args
    return [conda] + args


def get_torch_pip_args(prefer_cuda: bool = True) -> List[str]:
    """Return pip install args for PyTorch suited to the current platform.

    - macOS  : default PyPI wheel (includes MPS support automatically).
    - Windows: CUDA 12.1 index URL so the GPU-enabled wheel is fetched
               instead of the CPU-only fallback that pip may choose otherwise.
    - Linux  : default PyPI wheel (bundles CUDA runtime for x86-64).
    """
    system = platform.system()
    if system == "Windows" and prefer_cuda:
        return [
            "torch",
            "--index-url", "https://download.pytorch.org/whl/cu121",
        ]
    return ["torch"]


def env_exists(env_path: Path) -> bool:
    """Return True only if a COMPLETE conda env exists.

    Checks for ``conda-meta/history`` (the marker conda itself uses) rather than
    just the ``conda-meta`` directory. An interrupted ``conda create`` leaves a
    partial prefix with ``conda-meta/`` but no ``history``, which conda rejects as
    "not a conda environment". Treating that as absent lets create_env recreate it
    instead of every subsequent ``conda run`` failing against the broken prefix.
    """
    return (env_path / "conda-meta" / "history").exists()


def create_env(conda: str, env_path: Path, python_version: str) -> None:
    """Create a new conda env at *env_path* with the given Python version.

    If the directory already exists but is not a valid conda env (e.g. a prior
    ``conda create`` was interrupted, leaving a partial prefix), remove it first
    so ``conda create`` doesn't fail with "prefix already exists".
    """
    if env_path.exists() and not env_exists(env_path):
        logger.warning("Removing partial/invalid env prefix before recreating: %s", env_path)
        shutil.rmtree(env_path, ignore_errors=True)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Creating conda env: %s (Python %s)", env_path, python_version)
    _run_conda(make_conda_cmd(conda, [
        "create", "-p", str(env_path),
        *_CONDA_CHANNELS,
        f"python={python_version}",
        "-y",
    ]))


def conda_install(conda: str, env_path: Path, packages: List[str]) -> None:
    """Install or update *packages* into an existing conda env."""
    logger.info("Installing into %s: %s", env_path.name, " ".join(packages))
    _run_conda(make_conda_cmd(conda, [
        "install", "-p", str(env_path),
        *_CONDA_CHANNELS,
        *packages,
        "-y",
    ]))


def conda_run(conda: str, env_path: Path, cmd: List[str]) -> subprocess.CompletedProcess:
    """Run *cmd* inside a conda env, capturing stdout/stderr."""
    full_cmd = make_conda_cmd(conda, ["run", "--no-capture-output", "-p", str(env_path), *cmd])
    logger.debug("$ %s", " ".join(full_cmd))
    return subprocess.run(full_cmd, check=True, text=True, capture_output=True)


def get_installed_version(
    conda: str,
    env_path: Path,
    package_name: str,
    version_flag: str = "--version",
) -> str:  # noqa: E501
    """
    Get installed version of *package_name* inside *env_path*.

    Tries (in order):
    1. `<package> --version`
    2. `python -c "import importlib.metadata; print(importlib.metadata.version('<package>'))"`)
    3. `conda list --json` output

    Returns "unknown" if all methods fail.
    """
    # Method 1: CLI --version flag
    try:
        cp = conda_run(conda, env_path, [package_name, version_flag])
        text = (cp.stdout + cp.stderr).strip()
        m = re.search(r"v?(\d+\.\d+(?:\.\d+)*)", text)
        if m:
            return m.group(1)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Method 2: importlib.metadata
    try:
        cp = conda_run(conda, env_path, [
            "python", "-c",
            f"import importlib.metadata; print(importlib.metadata.version('{package_name}'))",
        ])
        v = cp.stdout.strip()
        if v:
            return v
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Method 3: conda list --json
    try:
        cp = subprocess.run(
            make_conda_cmd(conda, ["list", "-p", str(env_path), "--json"]),
            check=True, text=True, capture_output=True,
        )
        pkgs = json.loads(cp.stdout)
        for pkg in pkgs:
            if pkg.get("name") == package_name:
                return pkg.get("version", "unknown")
    except Exception:
        pass

    return "unknown"


def get_latest_bioconda_version(conda: str, package_name: str) -> str:
    """Query bioconda for the latest available version of *package_name*."""
    try:
        cp = subprocess.run(
            make_conda_cmd(conda, ["search", *_CONDA_CHANNELS, "--json", package_name]),
            check=True, text=True, capture_output=True,
        )
        data = json.loads(cp.stdout)
        records = data.get(package_name, [])
        versions = sorted(
            {r.get("version", "") for r in records if r.get("version")},
            key=_parse_semver,
        )
        return versions[-1] if versions else "unknown"
    except Exception as exc:
        logger.debug("Could not query bioconda for %s: %s", package_name, exc)
        return "unknown"


def _parse_semver(v: str):
    nums = re.findall(r"\d+", v)
    return tuple(int(x) for x in nums) if nums else (0,)


def _run_conda(cmd: List[str]) -> None:
    """Run a conda command, streaming output live."""
    logger.debug("$ %s", " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    rc = proc.wait()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)


# ---------------------------------------------------------------------------
# DB manifest helpers
# ---------------------------------------------------------------------------

def load_manifest(manifest_path: Path) -> Optional[Dict]:
    """Return parsed manifest JSON, or None if missing/corrupt."""
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read manifest %s: %s", manifest_path, exc)
        return None


def save_manifest(manifest_path: Path, manifest: Dict) -> None:
    """Write *manifest* as formatted JSON to *manifest_path*."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    logger.debug("Manifest written: %s", manifest_path)


def manifest_is_current(manifest: Optional[Dict], tool_version: str) -> bool:
    """Return True if *manifest* records the same tool version currently installed."""
    if manifest is None:
        return False
    return manifest.get("tool_version") == tool_version


# ---------------------------------------------------------------------------
# Zenodo helpers
# ---------------------------------------------------------------------------

def zenodo_record_metadata(record_id: str) -> Dict:
    """Fetch the Zenodo API record metadata for *record_id*."""
    url = f"https://zenodo.org/api/records/{record_id}"
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def zenodo_needs_update(record_files: List[Dict], manifest: Optional[Dict]) -> bool:
    """
    Compare Zenodo file checksums against saved manifest.
    Returns True if any file differs or manifest is absent.
    """
    if manifest is None:
        return True
    saved = manifest.get("files", {})
    for f in record_files:
        key = f.get("key") or f.get("filename", "")
        checksum = f.get("checksum", "")
        if not key or not checksum:
            return True
        if saved.get(key) != checksum:
            return True
    return False


# ---------------------------------------------------------------------------
# File download
# ---------------------------------------------------------------------------

def download_file(
    url: str,
    out_path: Path,
    expected_size: Optional[int] = None,
    *,
    max_retries: int = _DOWNLOAD_MAX_RETRIES,
) -> None:
    """
    Download *url* to *out_path* with browser-like headers and progress reporting.

    - Skips download if the file already exists with the correct size.
    - Uses a .part temp file to avoid partial downloads corrupting the target.
    - Only appends ?download=1 for Zenodo URLs (Zenodo CDN requires it; GitHub does not).
    - Retries up to *max_retries* times with exponential backoff on transient errors.
    - Uses a generous socket idle timeout (_DOWNLOAD_TIMEOUT) suited for large model files.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and expected_size and out_path.stat().st_size == expected_size:
        logger.info("Already downloaded: %s (%d bytes) — skipping", out_path.name, expected_size)
        return

    # ?download=1 is a Zenodo CDN directive; adding it to GitHub or other URLs
    # is harmless in most cases but can confuse some CDN redirect chains.
    if "zenodo.org" in url and "download=1" not in url:
        dl_url = url + ("?" if "?" not in url else "&") + "download=1"
    else:
        dl_url = url

    logger.info("Downloading: %s", out_path.name)
    logger.debug("  URL: %s", dl_url)

    tmp = out_path.with_suffix(out_path.suffix + ".part")
    last_exc: Exception = RuntimeError("No download attempt made")

    for attempt in range(max_retries):
        if attempt > 0:
            wait = 5 * (2 ** (attempt - 1))  # 5 s, 10 s, 20 s …
            logger.warning(
                "Download failed (attempt %d/%d): %s. Retrying in %ds…",
                attempt, max_retries, last_exc, wait,
            )
            time.sleep(wait)

        try:
            req = Request(dl_url, headers={"User-Agent": _USER_AGENT})
            with urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
                total = resp.headers.get("Content-Length")
                total_bytes = int(total) if total else expected_size

                downloaded = 0
                start = time.time()
                with open(tmp, "wb") as fh:
                    while True:
                        chunk = resp.read(1024 * 1024)  # 1 MB chunks
                        if not chunk:
                            break
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if total_bytes:
                            pct = 100.0 * downloaded / total_bytes
                            elapsed = time.time() - start
                            rate = downloaded / elapsed / (1024 * 1024) if elapsed > 0 else 0
                            sys.stdout.write(
                                f"\r  {downloaded / (1024**2):.1f}/{total_bytes / (1024**2):.1f} MB "
                                f"({pct:.0f}%)  {rate:.1f} MB/s"
                            )
                        else:
                            sys.stdout.write(f"\r  {downloaded / (1024**2):.1f} MB downloaded")
                        sys.stdout.flush()

            sys.stdout.write("\n")
            sys.stdout.flush()

            # BUG FIX: cache actual_size BEFORE unlinking tmp, then use it in the
            # error message.  Previously tmp.stat() was called after tmp.unlink()
            # which always raised FileNotFoundError, hiding the real error.
            actual_size = tmp.stat().st_size
            if expected_size and actual_size != expected_size:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Size mismatch for {out_path.name}: "
                    f"got {actual_size:,} bytes, expected {expected_size:,} bytes"
                )

            tmp.replace(out_path)
            logger.info("Saved: %s", out_path.name)
            return  # success

        except (HTTPError, URLError, RuntimeError, OSError) as exc:
            tmp.unlink(missing_ok=True)
            last_exc = exc
            if isinstance(exc, HTTPError) and exc.code in (400, 401, 403, 404):
                # Non-retryable HTTP errors
                raise RuntimeError(
                    f"HTTP {exc.code} downloading {dl_url}: {exc.reason}"
                ) from exc

    raise RuntimeError(
        f"Failed to download {out_path.name} after {max_retries} attempts. "
        f"Last error: {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# Archive extraction
# ---------------------------------------------------------------------------

def extract_tar_gz(tar_path: Path, dest_dir: Path) -> None:
    """Extract a .tar.gz archive to *dest_dir*."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Extracting %s → %s", tar_path.name, dest_dir)
    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(path=dest_dir)
    logger.debug("Extraction complete: %s", tar_path.name)
