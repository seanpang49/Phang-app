"""
Step 1: Pharokka — gene annotation.

For each phage FASTA, runs:
    pharokka.py -i <phage>.fasta -o <output>/<phage>/pharokka/ -d <db> -t <threads> -f

Key outputs per phage (in <output>/<phage>/pharokka/):
    pharokka.gbk    — annotated GenBank  → consumed by Step 2 (Phold)
    pharokka.tbl    — 5-column feature table → consumed by Step 10 (NCBI)
    pharokka.gff    — GFF3 annotations
    pharokka.faa /
    phanotate.faa   — protein sequences  → consumed by Steps 6, 7
                      (filename depends on Pharokka version; both are tried)
    pharokka.ffn /
    phanotate.ffn   — CDS nucleotide sequences
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from phang.config import DB_PHAROKKA, ENV_PHAROKKA
from phang.install.common import find_conda
from phang.utils.process import run_streaming

logger = logging.getLogger(__name__)


def _find_faa(outdir: Path) -> Path:
    """
    Return the protein FAA path, trying version-dependent filenames.
    Newer Pharokka → pharokka.faa; older → phanotate.faa.
    Returns the path regardless of existence (caller checks .exists()).
    """
    for name in ("pharokka.faa", "phanotate.faa"):
        p = outdir / name
        if p.exists():
            return p
    return outdir / "pharokka.faa"  # default fallback


def _find_ffn(outdir: Path) -> Path:
    """Same version-fallback logic for the CDS nucleotide FAA."""
    for name in ("pharokka.ffn", "phanotate.ffn"):
        p = outdir / name
        if p.exists():
            return p
    return outdir / "pharokka.ffn"


def _outputs_present(outdir: Path) -> bool:
    """Return True if Pharokka already produced its key output files."""
    gbk_ok = (outdir / "pharokka.gbk").exists()
    faa_ok = (outdir / "pharokka.faa").exists() or (outdir / "phanotate.faa").exists()
    return gbk_ok and faa_ok


def _run_single(
    conda: str,
    fasta: Path,
    outdir: Path,
    threads: int,
    force: bool,
    log_path: Path,
) -> bool:
    """Run Pharokka on one FASTA. Returns True on success."""
    if outdir.exists() and force:
        shutil.rmtree(outdir)

    outdir.mkdir(parents=True, exist_ok=True)

    if not force and _outputs_present(outdir):
        logger.info("  [SKIP] %s — outputs already present (use --force to rerun).", fasta.stem)
        return True

    needs_safe_workspace = " " in str(fasta) or " " in str(outdir)

    if needs_safe_workspace:
        with tempfile.TemporaryDirectory(prefix="phang-pharokka-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            safe_fasta = tmp_root / fasta.name.replace(" ", "_")
            safe_outdir = tmp_root / "pharokka_out"
            shutil.copy2(fasta, safe_fasta)

            cmd = [
                conda, "run", "--no-capture-output", "-p", str(ENV_PHAROKKA),
                "pharokka.py",
                "-i", str(safe_fasta),
                "-o", str(safe_outdir),
                "-d", str(DB_PHAROKKA),
                "-t", str(threads),
                "-f",
            ]
            rc = run_streaming(cmd, log_path=log_path)
            if rc != 0:
                return False

            for child in safe_outdir.iterdir():
                dest = outdir / child.name
                if child.is_dir():
                    shutil.copytree(child, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(child, dest)
            return True

    cmd = [
        conda, "run", "--no-capture-output", "-p", str(ENV_PHAROKKA),
        "pharokka.py",
        "-i", str(fasta),
        "-o", str(outdir),
        "-d", str(DB_PHAROKKA),
        "-t", str(threads),
        "-f",   # Pharokka's own overwrite flag
    ]

    rc = run_streaming(cmd, log_path=log_path)
    return rc == 0


def run_pharokka(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 1 entry point.

    Reads from ctx : fasta_files, output_path, threads, force
    Writes to ctx['results'][stem] : pharokka_dir, pharokka_gbk, pharokka_tbl,
                                     pharokka_faa, pharokka_ffn, pharokka_gff, fasta
    """
    fasta_files: List[Path] = ctx["fasta_files"]
    output_path: Path = ctx["output_path"]
    threads: int = ctx["threads"]
    force: bool = ctx["force"]

    conda = find_conda()
    ok = 0
    failed: List[str] = []

    for fasta in fasta_files:
        stem = fasta.stem
        outdir = output_path / stem / "pharokka"
        log_path = output_path / "_logs" / f"{stem}.pharokka.log"

        logger.info("  Pharokka ← %s", fasta.name)

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
            per = ctx["results"].setdefault(stem, {})
            per["fasta"]        = fasta
            per["pharokka_dir"] = outdir
            per["pharokka_gbk"] = outdir / "pharokka.gbk"
            per["pharokka_tbl"] = outdir / "pharokka.tbl"
            per["pharokka_faa"] = _find_faa(outdir)
            per["pharokka_ffn"] = _find_ffn(outdir)
            per["pharokka_gff"] = outdir / "pharokka.gff"
        else:
            failed.append(stem)
            logger.error("  [FAIL] Pharokka failed for %s", stem)

    logger.info("Pharokka: %d/%d succeeded", ok, len(fasta_files))

    if ok == 0:
        raise RuntimeError(
            f"Pharokka failed for all {len(fasta_files)} input(s). "
            f"Check logs in: {output_path / '_logs'}"
        )

    if failed:
        logger.warning("Pharokka failed for: %s", ", ".join(failed))

    return ctx
