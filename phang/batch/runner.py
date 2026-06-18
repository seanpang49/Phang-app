"""Batch runner -- processes all phages from a markdown list sequentially."""

import logging
from pathlib import Path

from phang.batch.parser import parse_batch_list
from phang.pipeline import run_pipeline

logger = logging.getLogger(__name__)


def run_batch(
    list_file: Path,
    input_dir: Path,
    output_root: Path,
    verbose: bool = False,
    threads: int = 8,
    gpu_mode: str = "auto",
    force: bool = False,
) -> dict:
    """
    Parse the batch list and run each phage through the pipeline.

    Returns a dict with keys: completed, skipped, failed -- each a list of phage names.
    """
    entries = parse_batch_list(list_file)
    total = len(entries)
    logger.info("Batch: %d phages parsed from %s", total, list_file.name)

    completed = []
    skipped = []
    failed = []

    for i, entry in enumerate(entries, 1):
        phage_output = output_root / entry.name
        fasta_path = input_dir / entry.source_file

        # EXEC-03: Skip if output directory already exists
        if phage_output.exists():
            logger.info("[%d/%d] Skipping %s -- output already exists", i, total, entry.name)
            skipped.append(entry.name)
            continue

        logger.info("[%d/%d] Running %s ...", i, total, entry.name)
        print(f"[{i}/{total}] Running {entry.name}...")

        try:
            run_pipeline(
                input_path=fasta_path,
                output_path=phage_output,
                threads=threads,
                gpu_mode=gpu_mode,
                force=force,
            )
            completed.append(entry.name)
            logger.info("[%d/%d] Completed %s", i, total, entry.name)
        except Exception as exc:
            failed.append(entry.name)
            logger.error("[%d/%d] FAILED %s: %s", i, total, entry.name, exc)

    return {"completed": completed, "skipped": skipped, "failed": failed}
