"""
GPU auto-detection for the phang pipeline.

Checks for CUDA (NVIDIA) first, then MPS (Apple Silicon), then falls back to CPU.
"""

import logging
import platform
import subprocess
import sys

logger = logging.getLogger(__name__)


def detect_gpu() -> str:
    """
    Return 'cuda', 'mps', or 'cpu'.

    Does NOT import torch — uses lightweight subprocess / platform checks so
    this function works even when torch is not installed in the current env.
    """
    # --- CUDA (NVIDIA) — works on Linux, macOS, and Windows ---
    if _nvidia_smi_present():
        logger.debug("GPU: CUDA detected via nvidia-smi")
        return "cuda"

    # --- MPS (Apple Silicon) — macOS only ---
    if sys.platform == "darwin" and _apple_silicon():
        logger.debug("GPU: MPS detected (Apple Silicon)")
        return "mps"

    logger.debug("GPU: no GPU detected, using CPU")
    return "cpu"


def _nvidia_smi_present() -> bool:
    # nvidia-smi may not be on PATH in conda/WSL2 environments; check known locations.
    candidates = ["nvidia-smi", "/usr/lib/wsl/lib/nvidia-smi"]
    for cmd in candidates:
        try:
            subprocess.run(
                [cmd],
                check=True,
                capture_output=True,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False


def _apple_silicon() -> bool:
    """Return True if running on Apple Silicon (arm64).

    Uses the stdlib ``platform`` module instead of a ``uname`` subprocess so
    this works correctly on Windows (where ``uname`` is unavailable) and avoids
    a redundant process spawn on macOS.
    """
    return platform.machine() == "arm64"
