"""
Subprocess utilities: run external commands with live streaming to terminal
and simultaneous capture to a log file.
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def run_streaming(
    cmd: List[str],
    log_path: Optional[Path] = None,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> int:
    """
    Run *cmd*, stream combined stdout/stderr live to the terminal, and
    optionally write everything to *log_path*.

    *env*, when given, replaces the child process environment (pass a copy of
    os.environ with your overrides). When None the parent environment is
    inherited unchanged.

    Returns the process exit code.
    """
    cmd_str = " ".join(str(c) for c in cmd)
    logger.debug("$ %s", cmd_str)

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_path, "w", encoding="utf-8")
        log_fh.write(f"$ {cmd_str}\n\n")
        log_fh.flush()
    else:
        log_fh = None

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(cwd) if cwd else None,
            env=env,
        )
        assert proc.stdout is not None

        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            if log_fh is not None:
                log_fh.write(line)
                log_fh.flush()

        return proc.wait()
    finally:
        if log_fh is not None:
            log_fh.close()


def run_silent(cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    """
    Run *cmd* without streaming output. Captures stdout and stderr.
    Raises subprocess.CalledProcessError on non-zero exit.
    """
    logger.debug("$ %s", " ".join(str(c) for c in cmd))
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        capture_output=True,
        cwd=str(cwd) if cwd else None,
    )
