"""
Install manager: ensures all tools are installed before the pipeline runs.

Called once at pipeline startup. Each tool's ensure_*() function is idempotent —
it checks version stamps and skips work that's already done.

Windows note
------------
Most Bioconda tools (pharokka, phold, phynteny, defensefinder, vcontact3)
are Linux/macOS-only.  On Windows, ``check_windows_requirements()`` is called
first; if WSL2 is absent a descriptive error is raised.

The ML-only tools (rbpdetect, deposcope) use pip-installable PyTorch and can
run natively on Windows with CUDA GPU support.

Status API
----------
``ensure_all_detailed()`` returns structured :class:`ToolStatus` objects so
callers (the GUI, the first-run bootstrap) can distinguish *ok* / *skipped* /
*failed* without string-parsing.  ``ensure_all()`` is kept as a thin
backward-compatible wrapper that returns the legacy ``{tool: status_string}``
mapping older consumers (cli.py, the step modules) still rely on.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Maps tool name → (module_path, ensure_func, is_fatal, bioconda_required)
# bioconda_required=True means the tool needs Linux/macOS (via WSL2 on Windows).
_TOOLS = [
    ("pharokka",      "phang.install.pharokka",      "ensure_pharokka",      True,  True),
    ("phold",         "phang.install.phold",         "ensure_phold",         False, True),
    ("phynteny",      "phang.install.phynteny",      "ensure_phynteny",      False, True),
    ("phastyle",      "phang.install.phastyle",      "ensure_phastyle",      False, True),
    ("phabox2",       "phang.install.cherry",        "ensure_cherry",        False, True),
    ("defensefinder", "phang.install.defensefinder", "ensure_defensefinder", False, True),
    ("vcontact3",     "phang.install.vcontact3",     "ensure_vcontact3",     False, True),
    ("rbpdetect",     "phang.install.rbpdetect",     "ensure_rbpdetect",     False, False),
    ("deposcope",     "phang.install.deposcope",     "ensure_deposcope",     False, False),
]


@dataclass
class ToolStatus:
    """Structured per-tool install outcome (consumed by the GUI / bootstrap)."""

    name: str
    state: str            # "ok" | "skipped" | "failed"
    version: str = ""     # installed version when state == "ok"
    message: str = ""     # skip reason or error text
    fatal: bool = False   # whether a failure here aborts the pipeline

    @property
    def ok(self) -> bool:
        return self.state == "ok"

    @property
    def legacy(self) -> str:
        """Backward-compatible status string (older consumers parse this).

        - "ok"      → the version string
        - "skipped" → the skip reason
        - "failed"  → "FAILED: <error>"  (matched via str.startswith elsewhere)
        """
        if self.state == "ok":
            return self.version
        if self.state == "skipped":
            return self.message or "skipped"
        return f"FAILED: {self.message}"


def ensure_all_detailed() -> dict[str, "ToolStatus"]:
    """
    Run ensure_*() for every tool and return structured per-tool status.

    Returns a dict mapping tool name → :class:`ToolStatus`.
    Raises SystemExit if a fatal tool (pharokka) fails to install.
    On Windows without WSL2, Bioconda-dependent tools are reported as
    ``skipped`` rather than crashing the entire pipeline; only the native
    Windows tools (rbpdetect, deposcope) are installed.
    """
    from phang.utils.wsl import is_windows, has_wsl2

    on_windows = is_windows()
    wsl2_available = has_wsl2() if on_windows else False

    if on_windows and not wsl2_available:
        logger.warning(
            "Running on Windows without WSL2. "
            "Bioconda tools (pharokka, phold, phynteny, phastyle, phabox2, "
            "defensefinder, vcontact3) cannot be installed natively. "
            "Only ML-native tools (rbpdetect, deposcope) will be set up. "
            "Install WSL2 and re-run for the full pipeline."
        )

    results: dict[str, ToolStatus] = {}
    failed: list[str] = []

    for tool_name, module_path, func_name, is_fatal, bioconda_required in _TOOLS:
        # On Windows without WSL2, skip Bioconda tools gracefully.
        if on_windows and not wsl2_available and bioconda_required:
            results[tool_name] = ToolStatus(
                name=tool_name,
                state="skipped",
                message="skipped (Windows — WSL2 required)",
            )
            logger.info("  %s: skipped (Bioconda, WSL2 not available)", tool_name)
            continue

        logger.info("Checking tool: %s", tool_name)
        try:
            mod = importlib.import_module(module_path)
            func = getattr(mod, func_name)
            version = func()
            results[tool_name] = ToolStatus(
                name=tool_name, state="ok", version=str(version),
            )
            logger.info("  %s: OK (%s)", tool_name, version)
        except Exception as exc:
            logger.error("  %s: FAILED — %s", tool_name, exc)
            results[tool_name] = ToolStatus(
                name=tool_name, state="failed", message=str(exc), fatal=is_fatal,
            )
            if is_fatal:
                failed.append(tool_name)

    if failed:
        raise SystemExit(
            f"Fatal tool installation failed: {', '.join(failed)}. "
            "Check the log for details and re-run after fixing the issue."
        )

    return results


def ensure_all() -> dict[str, str]:
    """
    Backward-compatible wrapper around :func:`ensure_all_detailed`.

    Returns a dict mapping tool name → legacy status string (the installed
    version on success, ``"FAILED: …"`` on error, or the skip reason). Existing
    consumers (cli.py, the step modules) string-match these values, so the
    format is preserved.
    """
    return {name: status.legacy for name, status in ensure_all_detailed().items()}
