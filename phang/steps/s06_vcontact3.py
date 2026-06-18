"""
Step 6: vConTACT3 — taxonomy prediction via protein-sharing network.

Uses --nucleotide mode (simplest, enables ANI export):
  vcontact3 run --nucleotide <phage.fasta> --db-domain prokaryotes \
                --db-path <db_dir> --output <outdir> \
                --exports cytoscape graphml ani

vClust must be installed in the vcontact3 env for ANI export.

Outputs (in <output>/<phage>/vcontact3/exports/):
  final_assignments.csv     — full taxonomy (realm → genus) for user + all references
  performance_metrics.csv   — clustering accuracy metrics
  part1.cyjs                — Cytoscape network
  part1.graphml             — GraphML network
  ani/<family>_ani.tsv      — ANI values between user genome and reference genomes
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from phang.config import DB_VCONTACT3, ENV_VCONTACT3
from phang.install.common import find_conda
from phang.utils.process import run_streaming

logger = logging.getLogger(__name__)


def _find_db_path() -> Optional[Path]:
    """
    Return the --db-path for vConTACT3.
    Must point to the parent dir containing both v230/ AND 230.json.
    """
    if not DB_VCONTACT3.exists():
        return None
    jsons = list(DB_VCONTACT3.glob("*.json"))
    if jsons:
        return DB_VCONTACT3
    parent = DB_VCONTACT3.parent
    if list(parent.glob("*.json")):
        return parent
    return None


def _outputs_present(outdir: Path) -> bool:
    return (outdir / "exports" / "final_assignments.csv").exists()


def _run_single(
    conda: str,
    fasta: Path,
    outdir: Path,
    stem: str,
    force: bool,
    log_path: Path,
) -> bool:
    """Run vConTACT3 in nucleotide mode. Returns True on success."""
    if outdir.exists() and force:
        shutil.rmtree(outdir)

    outdir.mkdir(parents=True, exist_ok=True)

    if not force and _outputs_present(outdir):
        logger.info("  [SKIP] %s — vcontact3 outputs already present.", stem)
        return True

    db_path = _find_db_path()
    if db_path is None:
        logger.error("vConTACT3 DB not found at %s — skipping.", DB_VCONTACT3)
        return False

    def _build_cmd(input_fasta: Path, output_dir: Path) -> list[str]:
        return [
            conda, "run", "--no-capture-output", "-p", str(ENV_VCONTACT3),
            "vcontact3", "run",
            "--nucleotide", str(input_fasta),
            "--db-domain", "prokaryotes",
            "--db-path", str(db_path),
            "--output", str(output_dir),
            "--exports", "cytoscape", "graphml", "ani",
        ]

    needs_safe_workspace = " " in str(fasta) or " " in str(outdir)
    if needs_safe_workspace:
        with tempfile.TemporaryDirectory(prefix="phang-vcontact3-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            safe_fasta = tmp_root / fasta.name.replace(" ", "_")
            safe_outdir = tmp_root / "vcontact3_out"
            shutil.copy2(fasta, safe_fasta)

            rc = run_streaming(_build_cmd(safe_fasta, safe_outdir), log_path=log_path)
            if rc != 0:
                return False

            for child in safe_outdir.iterdir():
                dest = outdir / child.name
                if child.is_dir():
                    shutil.copytree(child, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(child, dest)
            return True

    rc = run_streaming(_build_cmd(fasta, outdir), log_path=log_path)
    return rc == 0


def run_vcontact3(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 6 entry point.

    Reads from ctx : results[stem].fasta, output_path, force
    Writes to ctx['results'][stem] : vcontact3_dir, vcontact3_overview
    """
    output_path: Path = ctx["output_path"]
    force: bool = ctx["force"]

    conda = find_conda()
    ok = 0

    for stem, per in ctx["results"].items():
        fasta: Optional[Path] = per.get("fasta")
        if not fasta or not fasta.exists():
            logger.warning("  [SKIP] %s — input FASTA not found.", stem)
            continue

        outdir   = output_path / stem / "vcontact3"
        log_path = output_path / "_logs" / f"{stem}.vcontact3.log"

        logger.info("  vConTACT3 ← %s", fasta.name)

        success = _run_single(
            conda=conda,
            fasta=fasta,
            outdir=outdir,
            stem=stem,
            force=force,
            log_path=log_path,
        )

        if success:
            ok += 1
            per["vcontact3_dir"]      = outdir
            per["vcontact3_overview"] = outdir / "exports" / "final_assignments.csv"
        else:
            logger.error("  [FAIL] vConTACT3 failed for %s", stem)

    logger.info("vConTACT3: %d/%d succeeded", ok, len(ctx["results"]))
    return ctx
