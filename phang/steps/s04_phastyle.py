"""
Step 4: PhaStyle — lifestyle prediction (Lytic / Lysogenic / Temperate).

Runs:
    python PhaStyle.py --fastain <phage>.fasta --out <output>/<phage>/phastyle/predictions.tsv
                       --ftmodel neuralbioinfo/PhaStyle-mini --per_device_eval_batch_size 196

Input  : original phage FASTA (no DB needed — weights from HuggingFace on first run)
Output : predictions.tsv  →  consumed by Report Card (Therapy tab)
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict

from phang.config import ENV_PHASTYLE
from phang.install.common import find_conda
from phang.install.phastyle import get_phastyle_script
from phang.utils.process import run_streaming

logger = logging.getLogger(__name__)

_PHASTYLE_MODEL = "neuralbioinfo/PhaStyle-mini"
_BATCH_SIZE = 196


def _outputs_present(outdir: Path) -> bool:
    return (outdir / "predictions.tsv").exists()


def _run_single(
    conda: str,
    fasta: Path,
    outdir: Path,
    script: Path,
    force: bool,
    log_path: Path,
) -> bool:
    """Run PhaStyle on one FASTA. Returns True on success."""
    if outdir.exists() and force:
        shutil.rmtree(outdir)

    outdir.mkdir(parents=True, exist_ok=True)

    if not force and _outputs_present(outdir):
        logger.info("  [SKIP] %s — phastyle outputs already present.", fasta.stem)
        return True

    cmd = [
        conda, "run", "--no-capture-output", "-p", str(ENV_PHASTYLE),
        "python", str(script),
        "--fastain", str(fasta),
        "--out", str(outdir / "predictions.tsv"),
        "--ftmodel", _PHASTYLE_MODEL,
        "--batch-size", str(_BATCH_SIZE),
    ]

    # cwd=outdir: PhaStyle writes ./prokbert_inference_output to the current
    # working directory via a relative path. Under a double-clicked .app the CWD
    # is "/" (read-only) → OSError Errno 30. Point the child at the writable
    # per-phage output dir instead (HANDOFF BUG #1).
    rc = run_streaming(cmd, log_path=log_path, cwd=outdir)
    return rc == 0


def run_phastyle(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 4 entry point.

    Reads from ctx : results[stem].fasta, output_path, force
    Writes to ctx['results'][stem] : phastyle_dir, phastyle_predictions
    """
    output_path: Path = ctx["output_path"]
    force: bool = ctx["force"]

    conda = find_conda()
    script: Path | None = None  # resolved lazily (only needed if outputs are missing)
    ok = 0

    for stem, per in ctx["results"].items():
        fasta: Path = per.get("fasta")  # type: ignore[assignment]
        if not fasta or not fasta.exists():
            logger.warning("  [SKIP] %s — input FASTA not found.", stem)
            continue

        outdir = output_path / stem / "phastyle"
        log_path = output_path / "_logs" / f"{stem}.phastyle.log"

        if not force and _outputs_present(outdir):
            logger.info("  [SKIP] %s — phastyle outputs already present.", stem)
            ok += 1
            per["phastyle_dir"]         = outdir
            per["phastyle_predictions"] = outdir / "predictions.tsv"
            continue

        # Only resolve script path when we actually need to run
        if script is None:
            try:
                script = get_phastyle_script()
            except RuntimeError as exc:
                logger.error("PhaStyle script not found — skipping all remaining phages: %s", exc)
                break

        logger.info("  PhaStyle ← %s", fasta.name)

        success = _run_single(
            conda=conda,
            fasta=fasta,
            outdir=outdir,
            script=script,
            force=force,
            log_path=log_path,
        )

        if success:
            ok += 1
            per["phastyle_dir"]         = outdir
            per["phastyle_predictions"] = outdir / "predictions.tsv"
        else:
            logger.error("  [FAIL] PhaStyle failed for %s", stem)

    logger.info("PhaStyle: %d/%d succeeded", ok, len(ctx["results"]))
    return ctx
