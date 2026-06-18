"""
phang.install.bootstrap — idempotent first-run orchestrator.

Brings a fresh machine to a ready state in one call. Invoked by the Mac .pkg
post-install script and the Windows launcher:

  1. verify a conda/mamba (miniforge) is reachable
  2. ensure all tool envs are installed via manager.ensure_all_detailed() — each
     tool's ensure_*() also downloads its own database, so this is the eager
     "download everything at install time" step
  3. write a top-level manifest (PHANG_HOME/DB_MANIFEST.json) recording the
     outcome, so a rerun is a fast no-op

Because every tool already knows its own DB download location, this module does
not re-list any URLs; it orchestrates ensure_all_detailed() and records the
result.
"""

from __future__ import annotations

import json
import logging
import platform
from datetime import datetime
from typing import Dict, Optional

from phang.config import (
    DB_DIR,
    DB_MANIFEST_FILENAME,
    ENVS_DIR,
    PHANG_HOME,
    VERSION,
)

logger = logging.getLogger(__name__)

# Top-level manifest marking a completed bootstrap. Distinct from the per-DB
# manifests each tool writes inside its own database directory.
BOOTSTRAP_MANIFEST = PHANG_HOME / DB_MANIFEST_FILENAME


def is_bootstrapped() -> bool:
    """Return True if a previous bootstrap completed (top-level manifest exists)."""
    return BOOTSTRAP_MANIFEST.exists()


def load_bootstrap_manifest() -> Optional[Dict]:
    """Return the parsed bootstrap manifest, or None if missing/corrupt."""
    if not BOOTSTRAP_MANIFEST.exists():
        return None
    try:
        return json.loads(BOOTSTRAP_MANIFEST.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read bootstrap manifest %s: %s", BOOTSTRAP_MANIFEST, exc)
        return None


def _verify_conda() -> str:
    """Verify a conda/mamba is reachable; return its path. Raises if missing."""
    from phang.install.common import find_conda

    conda = find_conda()
    logger.info("Using conda: %s", conda)
    return conda


def bootstrap(force: bool = False) -> Dict:
    """
    Idempotent first-run setup: verify conda, install all tools + databases,
    and record a manifest. Safe to call repeatedly — each tool's ensure_*()
    skips work that is already done.

    Parameters
    ----------
    force : bool
        Re-run even if a previous bootstrap manifest is present. Individual
        tools remain idempotent regardless of this flag.

    Returns
    -------
    dict
        The bootstrap manifest that was written, or the existing one when the
        bootstrap was already complete and *force* is False.

    Raises
    ------
    RuntimeError
        If no conda/mamba is found on PATH.
    SystemExit
        If a fatal tool (pharokka) fails to install (propagated from
        ensure_all_detailed()).
    """
    PHANG_HOME.mkdir(parents=True, exist_ok=True)

    if is_bootstrapped() and not force:
        existing = load_bootstrap_manifest()
        if existing is not None:
            logger.info(
                "phang already bootstrapped (%s). Pass force=True to re-run.",
                BOOTSTRAP_MANIFEST,
            )
            return existing
        logger.warning("Bootstrap manifest unreadable — re-running bootstrap.")

    conda = _verify_conda()

    logger.info("Bootstrapping phang %s into %s", VERSION, PHANG_HOME)
    logger.info("  envs:      %s", ENVS_DIR)
    logger.info("  databases: %s", DB_DIR)

    from phang.install.manager import ensure_all_detailed

    statuses = ensure_all_detailed()  # installs envs + eagerly stages every DB

    manifest = {
        "phang_version": VERSION,
        "phang_home": str(PHANG_HOME),
        "envs_dir": str(ENVS_DIR),
        "db_dir": str(DB_DIR),
        "conda": conda,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "bootstrapped_at": datetime.now().isoformat(timespec="seconds"),
        "tools": {
            name: {
                "state": st.state,
                "version": st.version,
                "message": st.message,
            }
            for name, st in statuses.items()
        },
    }

    BOOTSTRAP_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    logger.info("Bootstrap complete. Manifest: %s", BOOTSTRAP_MANIFEST)

    skipped = [n for n, st in statuses.items() if st.state == "skipped"]
    failed = [n for n, st in statuses.items() if st.state == "failed"]
    if skipped:
        logger.warning("Tools skipped: %s", ", ".join(skipped))
    if failed:
        logger.warning("Non-fatal tools failed: %s", ", ".join(failed))

    return manifest
