"""
Create a double-clickable desktop shortcut to launch the Phang GUI.

macOS: ~/Desktop/Phang.command (shell script, auto-opened in bash)
Windows: ~/Desktop/Phang.bat
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path


def create_desktop_shortcut() -> Path:
    """
    Create a desktop shortcut for the current platform.
    Returns the path to the created shortcut.
    """
    desktop = Path.home() / "Desktop"
    desktop.mkdir(exist_ok=True)

    phang_exe = shutil.which("phang")
    if not phang_exe:
        raise RuntimeError(
            "'phang' not found on PATH. Make sure phang is installed: pip install -e ."
        )

    if sys.platform == "darwin":
        return _create_macos_shortcut(desktop, phang_exe)
    elif sys.platform == "win32":
        return _create_windows_shortcut(desktop, phang_exe)
    else:
        return _create_linux_shortcut(desktop, phang_exe)


def _create_macos_shortcut(desktop: Path, phang_exe: str) -> Path:
    script = desktop / "Phang.command"
    script.write_text(
        f"#!/bin/bash\n"
        f"# Phang — Phage Genome Analysis Pipeline\n"
        f'"{phang_exe}" gui\n',
        encoding="utf-8",
    )
    # Make executable
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _create_windows_shortcut(desktop: Path, phang_exe: str) -> Path:
    script = desktop / "Phang.bat"
    script.write_text(
        f"@echo off\n"
        f"REM Phang — Phage Genome Analysis Pipeline\n"
        f'"{phang_exe}" gui\n'
        f"pause\n",
        encoding="utf-8",
    )
    return script


def _create_linux_shortcut(desktop: Path, phang_exe: str) -> Path:
    # If running inside WSL2, prefer a .bat on the Windows desktop so the user
    # can double-click it from Windows Explorer.
    windows_desktop = _wsl_windows_desktop()
    if windows_desktop:
        return _create_wsl_windows_bat(windows_desktop, phang_exe)

    script = desktop / "Phang.sh"
    script.write_text(
        f"#!/bin/bash\n"
        f'"{phang_exe}" gui\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _wsl_windows_desktop() -> Path | None:
    """Return the Windows Desktop path via /mnt/c/... if running inside WSL2."""
    import subprocess
    try:
        result = subprocess.run(
            ["powershell.exe", "-Command",
             "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True, text=True, timeout=5,
        )
        win_path = result.stdout.strip()  # e.g. C:\Users\sean\OneDrive\Desktop
        if not win_path:
            return None
        # Convert to WSL path: C:\Users\... -> /mnt/c/Users/...
        drive, rest = win_path[0].lower(), win_path[2:].replace("\\", "/")
        return Path(f"/mnt/{drive}{rest}")
    except Exception:
        return None


def _create_wsl_windows_bat(desktop: Path, phang_exe: str) -> Path:
    """Create a .bat on the Windows desktop that launches phang gui via WSL2."""
    desktop.mkdir(parents=True, exist_ok=True)
    script = desktop / "Phang.bat"
    script.write_text(
        "@echo off\n"
        "REM Phang — Phage Genome Analysis Pipeline\n"
        'wsl -- bash -c "export PATH=\\"$HOME/miniforge3/bin:$PATH\\" && phang gui"\n',
        encoding="utf-8",
    )
    return script
