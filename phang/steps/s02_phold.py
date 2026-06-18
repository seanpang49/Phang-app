"""
Step 2: Phold — structure-informed re-annotation.

For each phage that has a Pharokka GenBank output, runs:
    phold run -i <pharokka.gbk> -o <output>/<phage>/phold/ -d <db> -t <threads> [-f] [--cpu]

Key outputs per phage (in <output>/<phage>/phold/):
    phold.gbk                                — re-annotated GenBank → consumed by Step 3
    sub_db_tophits/card_cds_predictions.tsv  — foldseek AMR hits → consumed by Report (therapy tab)
    sub_db_tophits/vfdb_cds_predictions.tsv  — foldseek VF hits  → consumed by Report (therapy tab)
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from phang.config import ENV_PHOLD
from phang.install.common import find_conda
from phang.install.phold import find_phold_db_dir
from phang.utils.gpu import detect_gpu
from phang.utils.process import run_streaming

logger = logging.getLogger(__name__)


def _outputs_present(outdir: Path) -> bool:
    return (outdir / "phold.gbk").exists()


def _run_single(
    conda: str,
    gbk: Path,
    outdir: Path,
    db_dir: Path,
    threads: int,
    force: bool,
    gpu: str,
    log_path: Path,
) -> bool:
    """Run Phold on one GenBank file. Returns True on success."""
    if outdir.exists() and force:
        shutil.rmtree(outdir)

    outdir.parent.mkdir(parents=True, exist_ok=True)

    if not force and _outputs_present(outdir):
        logger.info("  [SKIP] %s — phold outputs already present.", gbk.parent.parent.name)
        return True

    needs_safe_workspace = " " in str(gbk) or " " in str(outdir)

    def _build_cmd(input_gbk: Path, output_dir: Path) -> list[str]:
        cmd = [
            conda, "run", "--no-capture-output", "-p", str(ENV_PHOLD),
            "phold", "run",
            "-i", str(input_gbk),
            "-o", str(output_dir),
            "-d", str(db_dir),
            "-t", str(threads),
            "-f",
        ]
        if gpu == "cpu" and detect_gpu() != "mps":
            cmd.append("--cpu")
        return cmd

    if needs_safe_workspace:
        with tempfile.TemporaryDirectory(prefix="phang-phold-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            safe_gbk = tmp_root / gbk.name.replace(" ", "_")
            safe_outdir = tmp_root / "phold_out"
            shutil.copy2(gbk, safe_gbk)

            rc = run_streaming(_build_cmd(safe_gbk, safe_outdir), log_path=log_path)
            if rc != 0:
                return False

            outdir.mkdir(parents=True, exist_ok=True)
            for child in safe_outdir.iterdir():
                dest = outdir / child.name
                if child.is_dir():
                    shutil.copytree(child, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(child, dest)
            return True

    rc = run_streaming(_build_cmd(gbk, outdir), log_path=log_path)
    return rc == 0


def run_phold(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 2 entry point.

    Reads from ctx : results[stem].pharokka_gbk, output_path, threads, gpu, force
    Writes to ctx['results'][stem] : phold_dir, phold_gbk, phold_card_tsv, phold_vfdb_tsv
    """
    output_path: Path = ctx["output_path"]
    threads: int = ctx["threads"]
    gpu: str = ctx["gpu"]
    force: bool = ctx["force"]

    conda = find_conda()
    use_mps_workaround = gpu == "cpu" and detect_gpu() == "mps"
    if use_mps_workaround:
        logger.warning(
            "Phold CPU mode is unstable on Apple Silicon; using MPS for this step instead of --cpu."
        )

    try:
        db_dir = find_phold_db_dir()
    except RuntimeError as exc:
        logger.error("Cannot locate Phold DB: %s", exc)
        raise

    ok = 0
    skipped = 0

    for stem, per in ctx["results"].items():
        gbk: Path = per.get("pharokka_gbk")  # type: ignore[assignment]
        if not gbk or not gbk.exists():
            logger.warning("  [SKIP] %s — pharokka.gbk not found.", stem)
            skipped += 1
            continue

        outdir = output_path / stem / "phold"
        log_path = output_path / "_logs" / f"{stem}.phold.log"

        logger.info("  Phold ← %s", gbk.name)

        success = _run_single(
            conda=conda,
            gbk=gbk,
            outdir=outdir,
            db_dir=db_dir,
            threads=threads,
            force=force,
            gpu=gpu,
            log_path=log_path,
        )

        if success:
            ok += 1
            per["phold_dir"] = outdir
            per["phold_gbk"] = outdir / "phold.gbk"
            # phold writes one TSV per sub-database; there is no unified file.
            per["phold_card_tsv"] = outdir / "sub_db_tophits" / "card_cds_predictions.tsv"
            per["phold_vfdb_tsv"] = outdir / "sub_db_tophits" / "vfdb_cds_predictions.tsv"
        else:
            logger.error("  [FAIL] Phold failed for %s", stem)

    total = len(ctx["results"])
    logger.info("Phold: %d/%d succeeded (%d skipped)", ok, total - skipped, skipped)
    return ctx
