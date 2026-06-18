"""
Step 3: Phynteny — synteny-aware re-annotation.

For each phage that has a Phold GenBank output, runs:
    phynteny_transformer <phold.gbk> -o <output>/<phage>/phynteny/ --prefix <stem> -m <models> -f

Key outputs per phage (in <output>/<phage>/phynteny/):
    <stem>.gbk       — most comprehensive GenBank ⭐ consumed by Step 9 (genome viz), Report
    <stem>.plot.png  — phynteny genome plot

Phynteny supplements existing annotations with predicted functional categories
(PHROG-based, ≥0.8 confidence). It does NOT replace annotations.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from phang.config import ENV_PHYNTENY
from phang.install.common import find_conda
from phang.install.phynteny import get_phynteny_models_dir
from phang.utils.process import run_streaming

logger = logging.getLogger(__name__)


def _find_phynteny_gbk(outdir: Path, stem: str) -> Optional[Path]:
    """
    Phynteny may name its output phynteny.gbk or <stem>.gbk depending on version.
    Return whichever exists, preferring phynteny.gbk.
    """
    for name in ("phynteny.gbk", f"{stem}.gbk"):
        p = outdir / name
        if p.exists():
            return p
    return None


def _outputs_present(outdir: Path, stem: str) -> bool:
    return _find_phynteny_gbk(outdir, stem) is not None


def _run_single(
    conda: str,
    gbk: Path,
    outdir: Path,
    stem: str,
    models_dir: Path,
    force: bool,
    log_path: Path,
) -> bool:
    """Run Phynteny on one GenBank file. Returns True on success."""
    if outdir.exists() and force:
        shutil.rmtree(outdir)

    outdir.mkdir(parents=True, exist_ok=True)

    if not force and _outputs_present(outdir, stem):
        logger.info("  [SKIP] %s — phynteny outputs already present.", stem)
        return True

    # Phynteny uses the Python binary directly (not a console script)
    python = ENV_PHYNTENY / "bin" / "python"
    phynteny_bin = ENV_PHYNTENY / "bin" / "phynteny_transformer"

    cmd = [
        conda, "run", "--no-capture-output", "-p", str(ENV_PHYNTENY),
        str(python), str(phynteny_bin),
        str(gbk),
        "-o", str(outdir),
        "--prefix", stem,
        "-m", str(models_dir),
        "-f",
    ]

    rc = run_streaming(cmd, log_path=log_path)
    return rc == 0


def run_phynteny(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 3 entry point.

    Reads from ctx : results[stem].phold_gbk, output_path, force
    Writes to ctx['results'][stem] : phynteny_dir, phynteny_gbk, phynteny_plot
    """
    output_path: Path = ctx["output_path"]
    force: bool = ctx["force"]

    conda = find_conda()
    ok = 0
    skipped = 0

    for stem, per in ctx["results"].items():
        # Prefer phold.gbk; fall back to pharokka.gbk if phold didn't run
        gbk: Path = per.get("phold_gbk") or per.get("pharokka_gbk")  # type: ignore[assignment]
        if not gbk or not gbk.exists():
            logger.warning("  [SKIP] %s — no input GBK found for Phynteny.", stem)
            skipped += 1
            continue

        outdir = output_path / stem / "phynteny"
        log_path = output_path / "_logs" / f"{stem}.phynteny.log"

        logger.info("  Phynteny ← %s", gbk.name)

        success = _run_single(
            conda=conda,
            gbk=gbk,
            outdir=outdir,
            stem=stem,
            models_dir=get_phynteny_models_dir(),
            force=force,
            log_path=log_path,
        )

        if success:
            ok += 1
            per["phynteny_dir"]  = outdir
            per["phynteny_gbk"]  = _find_phynteny_gbk(outdir, stem) or outdir / "phynteny.gbk"
            per["phynteny_plot"] = outdir / f"{stem}.plot.png"
        else:
            logger.error("  [FAIL] Phynteny failed for %s", stem)

    total = len(ctx["results"])
    logger.info("Phynteny: %d/%d succeeded (%d skipped)", ok, total - skipped, skipped)
    return ctx
