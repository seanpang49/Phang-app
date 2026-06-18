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
"""

from __future__ import annotations

import importlib
import logging
import sys

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


def ensure_all() -> dict[str, str]:
    """
    Run ensure_*() for every tool.

    Returns a dict mapping tool name → installed version / status string.
    Raises SystemExit if a fatal tool fails to install.
    On Windows without WSL2, Bioconda-dependent tools are skipped with a warning
    rather than crashing the entire pipeline; only the native Windows tools
    (rbpdetect, deposcope) are installed.
    """
    from phang.utils.wsl import is_windows, has_wsl2, check_windows_requirements

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

    results: dict[str, str] = {}
    failed: list[str] = []

    for tool_name, module_path, func_name, is_fatal, bioconda_required in _TOOLS:
        # On Windows without WSL2, skip Bioconda tools gracefully.
        if on_windows and not wsl2_available and bioconda_required:
            results[tool_name] = "skipped (Windows — WSL2 required)"
            logger.info("  %s: skipped (Bioconda, WSL2 not available)", tool_name)
            continue

        logger.info("Checking tool: %s", tool_name)
        try:
            mod = importlib.import_module(module_path)
            func = getattr(mod, func_name)
            version = func()
            results[tool_name] = version
            logger.info("  %s: OK (%s)", tool_name, version)
        except Exception as exc:
            logger.error("  %s: FAILED — %s", tool_name, exc)
            results[tool_name] = f"FAILED: {exc}"
            if is_fatal:
                failed.append(tool_name)

    if failed:
        raise SystemExit(
            f"Fatal tool installation failed: {', '.join(failed)}. "
            "Check the log for details and re-run after fixing the issue."
        )

    return results
