"""
Main pipeline orchestrator.

Calls each step in order and tracks progress. If a non-critical step fails
it logs the error and continues; only a Pharokka failure is treated as fatal.
"""

import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

from phang.utils.fasta import find_fasta_files, count_records, split_multifasta
from phang.utils.gpu import detect_gpu

logger = logging.getLogger(__name__)

TOTAL_STEPS = 12


def _step_header(n: int, label: str) -> None:
    logger.info("[%d/%d] %s", n, TOTAL_STEPS, label)


def _resolve_gpu(gpu_mode: str) -> str:
    """Return 'cuda', 'mps', or 'cpu' based on the requested mode."""
    if gpu_mode == "cpu":
        return "cpu"
    if gpu_mode == "force_gpu":
        detected = detect_gpu()
        if detected == "cpu":
            logger.warning("--gpu requested but no GPU detected; continuing on CPU.")
        return detected
    # auto
    return detect_gpu()


def _safe_stem(name: str) -> str:
    """Replace spaces and other shell-unsafe characters with underscores."""
    return re.sub(r"[^\w.\-]", "_", name)


def _collect_fasta_inputs(input_path: Path, output_path: Path) -> List[Path]:
    """
    Resolve the user-supplied input path to a flat list of single-record
    FASTA files, splitting multi-record files if necessary.

    Any FASTA whose absolute path contains spaces (or other characters that
    break tools like phanotate) is copied to a safe subdirectory so that
    downstream tools never receive a path with spaces.
    """
    raw_files = find_fasta_files(input_path)

    resolved: List[Path] = []
    for fasta in raw_files:
        n = count_records(fasta)
        if n == 1:
            resolved.append(fasta)
        else:
            logger.info(
                "Multi-record FASTA detected (%d records): splitting %s",
                n, fasta.name,
            )
            split_dir = output_path / "_split_inputs"
            split_files = split_multifasta(fasta, split_dir)
            resolved.extend(split_files)

    # Copy any FASTA whose path contains spaces to a safe location.
    # Tools like phanotate (called internally by Pharokka) do not handle
    # spaces in paths and return exit code 2.
    safe_dir = output_path / "_safe_inputs"
    sanitized: List[Path] = []
    for fasta in resolved:
        if " " in str(fasta):
            safe_dir.mkdir(parents=True, exist_ok=True)
            safe_name = _safe_stem(fasta.stem) + fasta.suffix
            safe_path = safe_dir / safe_name
            if not safe_path.exists():
                shutil.copy2(fasta, safe_path)
                logger.info(
                    "Copied '%s' to '%s' (path contained spaces — incompatible with some tools)",
                    fasta.name, safe_path.name,
                )
            sanitized.append(safe_path)
        else:
            sanitized.append(fasta)

    logger.info("Phage genomes to process: %d", len(sanitized))
    return sanitized


def run_pipeline(
    input_path: Path,
    output_path: Path,
    threads: int,
    gpu_mode: str,
    force: bool,
) -> None:
    """
    Run the full phang pipeline.

    Parameters
    ----------
    input_path : Path
        Single FASTA, directory of FASTAs, or multi-record FASTA.
    output_path : Path
        Root output directory.
    threads : int
        CPU thread count for parallelisable tools.
    gpu_mode : str
        One of 'auto', 'force_gpu', 'cpu'.
    force : bool
        Overwrite existing outputs when True.
    """
    gpu = _resolve_gpu(gpu_mode)
    logger.info("Effective GPU device: %s", gpu)

    # --- Pre-flight: install / verify all tools ---
    logger.info("Checking tool installations…")
    from phang.install.manager import ensure_all_detailed
    tool_status_detailed = ensure_all_detailed()
    tool_status = {name: st.legacy for name, st in tool_status_detailed.items()}

    fasta_files = _collect_fasta_inputs(input_path, output_path)

    # Context carries all paths and settings between steps.
    # Steps populate it with their output paths for downstream consumption.
    ctx: Dict[str, Any] = {
        "fasta_files": fasta_files,
        "output_path": output_path,
        "threads": threads,
        "gpu": gpu,
        "force": force,
        "tool_status": tool_status,
        "tool_status_detailed": tool_status_detailed,
        "results": {},   # keyed by phage stem → per-phage output dict
    }

    # --- Step 1: Pharokka (fatal if fails) ---
    _step_header(1, "Pharokka — gene annotation")
    try:
        from phang.steps.s01_pharokka import run_pharokka
        ctx = run_pharokka(ctx)
    except Exception as exc:
        logger.error("Pharokka failed — cannot continue: %s", exc)
        raise SystemExit(1) from exc

    # --- Step 2: Phold ---
    _step_header(2, "Phold — structure-informed re-annotation")
    try:
        from phang.steps.s02_phold import run_phold
        ctx = run_phold(ctx)
    except Exception as exc:
        logger.error("Phold failed (non-fatal): %s", exc)

    # --- Step 3: Phynteny ---
    _step_header(3, "Phynteny — synteny-aware re-annotation")
    try:
        from phang.steps.s03_phynteny import run_phynteny
        ctx = run_phynteny(ctx)
    except Exception as exc:
        logger.error("Phynteny failed (non-fatal): %s", exc)

    # --- Step 4: PhaStyle ---
    _step_header(4, "PhaStyle — lifestyle prediction")
    try:
        from phang.steps.s04_phastyle import run_phastyle
        ctx = run_phastyle(ctx)
    except Exception as exc:
        logger.error("PhaStyle failed (non-fatal): %s", exc)

    # --- Step 5: PhaBOX2 ---
    _step_header(5, "PhaBOX2 — host prediction")
    try:
        from phang.steps.s05_cherry import run_cherry
        ctx = run_cherry(ctx)
    except Exception as exc:
        logger.error("PhaBOX2 host prediction failed (non-fatal): %s", exc)

    # --- Step 6: vConTACT3 ---
    _step_header(6, "vConTACT3 — taxonomy prediction")
    try:
        from phang.steps.s06_vcontact3 import run_vcontact3
        ctx = run_vcontact3(ctx)
    except Exception as exc:
        logger.error("vConTACT3 failed (non-fatal): %s", exc)

    # --- Step 7: DefenseFinder ---
    _step_header(7, "DefenseFinder — antidefense systems")
    try:
        from phang.steps.s07_defensefinder import run_defensefinder
        ctx = run_defensefinder(ctx)
    except Exception as exc:
        logger.error("DefenseFinder failed (non-fatal): %s", exc)

    # --- Step 8: PhageRBPdetect ---
    _step_header(8, "PhageRBPdetect — receptor-binding protein identification")
    try:
        from phang.steps.s07_rbpdetect import run_rbpdetect
        ctx = run_rbpdetect(ctx)
    except Exception as exc:
        logger.error("PhageRBPdetect failed (non-fatal): %s", exc)

    # --- Step 9: DepoScope ---
    _step_header(9, "DepoScope — depolymerase detection")
    try:
        from phang.steps.s08_deposcope import run_deposcope
        ctx = run_deposcope(ctx)
    except Exception as exc:
        logger.error("DepoScope failed (non-fatal): %s", exc)

    # --- Step 10: Genome visualisation ---
    _step_header(10, "Genome visualisation — circular genome map")
    try:
        from phang.steps.s09_genome_viz import run_genome_viz
        ctx = run_genome_viz(ctx)
    except Exception as exc:
        logger.error("Genome visualisation failed (non-fatal): %s", exc)

    # --- Step 11: NCBI BankIt package ---
    _step_header(11, "NCBI BankIt — multifasta + feature table")
    try:
        from phang.steps.s10_ncbi import run_ncbi
        ctx = run_ncbi(ctx)
    except Exception as exc:
        logger.error("NCBI package generation failed (non-fatal): %s", exc)

    # --- Step 12: Report card ---
    _step_header(12, "Report card — HTML summary")
    try:
        from phang.steps.s11_report import run_report
        ctx = run_report(ctx)
    except Exception as exc:
        logger.error("Report card generation failed (non-fatal): %s", exc)

    logger.info("Pipeline complete. Results in: %s", output_path)
