"""
WSL2 detection and helper utilities for running phang on Windows.

Most bioinformatics tools in phang (pharokka, phold, phynteny, vcontact3,
defensefinder) are distributed via Bioconda which only supports Linux and
macOS.  On Windows, these tools must run inside WSL2 (Windows Subsystem for
Linux 2), which provides a full Linux kernel and can pass NVIDIA CUDA through
to the Linux guest via the NVIDIA CUDA on WSL driver.

The ML-only steps (rbpdetect, deposcope) use pip-installable PyTorch and can
run natively on Windows with CUDA support.

This module provides:
- is_windows()         — True when running on Windows
- has_wsl2()           — True when wsl.exe is present and a Linux distro is available
- wsl_cmd(cmd)         — Wrap a command list for execution in WSL2
- wsl_path(win_path)   — Translate a Windows path to its /mnt/... WSL2 equivalent
- check_windows_requirements() — Raise if Windows + no WSL2
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath

logger = logging.getLogger(__name__)


def is_windows() -> bool:
    """Return True when phang is running on Windows (not inside WSL2)."""
    return sys.platform == "win32"


def has_wsl2() -> bool:
    """Return True if wsl.exe is in PATH and at least one Linux distribution is registered."""
    if not is_windows():
        return False
    if not shutil.which("wsl.exe") and not shutil.which("wsl"):
        return False
    try:
        cp = subprocess.run(
            ["wsl", "--list", "--quiet"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        # Output contains installed distro names; non-empty = at least one present.
        output = (cp.stdout + cp.stderr).strip()
        return bool(output) and cp.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def wsl_path(windows_path: Path) -> str:
    """Convert a Windows absolute path to its WSL2 /mnt/<drive>/... equivalent.

    Example: ``C:\\Users\\alice\\data`` → ``/mnt/c/Users/alice/data``
    """
    p = PureWindowsPath(windows_path.resolve())
    drive = p.drive.rstrip(":").lower()
    parts = list(p.parts[1:])  # skip the drive letter part
    return "/mnt/" + drive + "/" + "/".join(parts).replace("\\", "/")


def wsl_cmd(cmd: list[str], *, cwd: Path | None = None) -> list[str]:
    """Wrap *cmd* so it executes inside WSL2 from Windows.

    Optionally sets the working directory to *cwd* (translated to WSL2 path).
    """
    base = ["wsl", "--"]
    if cwd is not None:
        wsl_cwd = wsl_path(cwd)
        base = ["wsl", "--cd", wsl_cwd, "--"]
    return base + cmd


def check_windows_requirements() -> None:
    """Raise a descriptive RuntimeError if Windows is detected but WSL2 is absent.

    Call this before attempting to install or run any Bioconda-distributed tool.
    """
    if not is_windows():
        return
    if has_wsl2():
        logger.info("Windows detected — WSL2 is available. Bioconda tools will run via WSL2.")
        return

    raise RuntimeError(
        "phang requires WSL2 (Windows Subsystem for Linux 2) on Windows because "
        "core bioinformatics tools (pharokka, phold, phynteny, etc.) are only "
        "available via Bioconda for Linux/macOS.\n\n"
        "To set up WSL2:\n"
        "  1. Open PowerShell as Administrator and run:\n"
        "       wsl --install\n"
        "  2. Restart your computer.\n"
        "  3. Open the Ubuntu app and create a user account.\n"
        "  4. Inside WSL2 Ubuntu, install Miniforge:\n"
        "       wget -O Miniforge3.sh https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh\n"
        "       bash Miniforge3.sh\n"
        "  5. Install phang inside WSL2:\n"
        "       pip install -e /mnt/c/path/to/phang\n"
        "  6. For NVIDIA GPU support in WSL2, install the NVIDIA WSL2 driver:\n"
        "       https://developer.nvidia.com/cuda/wsl\n\n"
        "The ML-only steps (RBPdetect, DepoScope) can run natively on Windows "
        "with CUDA; those will be handled automatically."
    )


def gpu_in_wsl2() -> bool:
    """Return True if the WSL2 guest can see an NVIDIA GPU (CUDA passthrough)."""
    if not has_wsl2():
        return False
    try:
        cp = subprocess.run(
            ["wsl", "--", "nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return cp.returncode == 0 and bool(cp.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
