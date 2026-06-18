"""
Step 5: PhaBOX2 host prediction using the maintained CHERRY workflow.

Runs:
    phabox2 --task cherry --contigs <phage>.fasta --outpth <output>/<phage>/cherry/ \
            --dbdir <db> --threads <n> --len 0

Outputs:
    final_prediction/cherry_prediction.tsv  — raw PhaBOX2 output
    host_prediction.csv                     — normalized file used by the report
"""

from __future__ import annotations

import csv
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from phang.config import DB_CHERRY, ENV_CHERRY
from phang.install.common import find_conda
from phang.utils.process import run_streaming

logger = logging.getLogger(__name__)

_RAW_PREDICTION = Path("final_prediction") / "cherry_prediction.tsv"


def _outputs_present(outdir: Path) -> bool:
    return (outdir / "host_prediction.csv").exists() and (outdir / _RAW_PREDICTION).exists()


def _normalize_predictions(raw_tsv: Path, out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with raw_tsv.open(newline="", encoding="utf-8") as src, out_csv.open(
        "w", newline="", encoding="utf-8"
    ) as dst:
        reader = csv.DictReader(src, delimiter="\t")
        writer = csv.DictWriter(
            dst,
            fieldnames=["accession", "length", "host", "score", "method"],
        )
        writer.writeheader()
        for row in reader:
            writer.writerow(
                {
                    "accession": row.get("Accession", ""),
                    "length": row.get("Length", ""),
                    "host": row.get("Host") or row.get("Host_NCBI") or row.get("Host_GTDB") or "",
                    "score": row.get("CHERRYScore") or row.get("Score") or "",
                    "method": row.get("Method", ""),
                }
            )


def _run_single(
    conda: str,
    fasta: Path,
    outdir: Path,
    threads: int,
    force: bool,
    log_path: Path,
) -> bool:
    """Run PhaBOX2 host prediction on one FASTA. Returns True on success."""
    if outdir.exists() and force:
        shutil.rmtree(outdir)

    outdir.mkdir(parents=True, exist_ok=True)

    if not force and _outputs_present(outdir):
        logger.info("  [SKIP] %s — PhaBOX2 host-prediction outputs already present.", fasta.stem)
        return True

    def _build_cmd(input_fasta: Path, output_dir: Path) -> list[str]:
        return [
            conda, "run", "--no-capture-output", "-p", str(ENV_CHERRY),
            "phabox2",
            "--task", "cherry",
            "--contigs", str(input_fasta),
            "--outpth", str(output_dir),
            "--dbdir", str(DB_CHERRY),
            "--threads", str(max(1, threads)),
            "--len", "0",
        ]

    needs_safe_workspace = " " in str(fasta) or " " in str(outdir)
    if needs_safe_workspace:
        with tempfile.TemporaryDirectory(prefix="phang-phabox2-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            safe_fasta = tmp_root / fasta.name.replace(" ", "_")
            safe_outdir = tmp_root / "phabox2_cherry"
            shutil.copy2(fasta, safe_fasta)

            rc = run_streaming(_build_cmd(safe_fasta, safe_outdir), log_path=log_path)
            if rc != 0:
                return False

            raw_prediction = safe_outdir / _RAW_PREDICTION
            if not raw_prediction.exists() or raw_prediction.stat().st_size == 0:
                return False

            for child in safe_outdir.iterdir():
                dest = outdir / child.name
                if child.is_dir():
                    shutil.copytree(child, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(child, dest)
    else:
        rc = run_streaming(_build_cmd(fasta, outdir), log_path=log_path)
        if rc != 0:
            return False

    raw_prediction = outdir / _RAW_PREDICTION
    if not raw_prediction.exists() or raw_prediction.stat().st_size == 0:
        return False

    _normalize_predictions(raw_prediction, outdir / "host_prediction.csv")
    return (outdir / "host_prediction.csv").exists()


def run_cherry(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 5 entry point.

    Reads from ctx : results[stem].fasta, output_path, force, threads
    Writes to ctx['results'][stem] : cherry_dir, cherry_host_prediction
    """
    output_path: Path = ctx["output_path"]
    force: bool = ctx["force"]
    threads: int = ctx.get("threads", 1)

    conda = find_conda()
    ok = 0

    for stem, per in ctx["results"].items():
        fasta: Optional[Path] = per.get("fasta")
        if not fasta or not fasta.exists():
            logger.warning("  [SKIP] %s — input FASTA not found.", stem)
            continue

        outdir = output_path / stem / "cherry"
        log_path = output_path / "_logs" / f"{stem}.cherry.log"

        if not force and _outputs_present(outdir):
            logger.info("  [SKIP] %s — PhaBOX2 host-prediction outputs already present.", stem)
            ok += 1
            per["cherry_dir"] = outdir
            per["cherry_host_prediction"] = outdir / "host_prediction.csv"
            continue

        logger.info("  PhaBOX2/CHERRY ← %s", fasta.name)

        success = _run_single(
            conda=conda,
            fasta=fasta,
            outdir=outdir,
            threads=threads,
            force=force,
            log_path=log_path,
        )

        if success:
            ok += 1
            per["cherry_dir"] = outdir
            per["cherry_host_prediction"] = outdir / "host_prediction.csv"
        else:
            logger.error("  [FAIL] PhaBOX2 host prediction failed for %s", stem)

    logger.info("PhaBOX2 host prediction: %d/%d succeeded", ok, len(ctx["results"]))
    return ctx
