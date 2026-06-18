"""
FASTA utilities: discovery, validation, and streaming reads.
"""

import logging
from pathlib import Path
from typing import Iterator, List, Tuple

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord

from phang.config import FASTA_EXTENSIONS

logger = logging.getLogger(__name__)


def find_fasta_files(path: Path) -> List[Path]:
    """
    Given *path*:
    - If it is a file with a recognised FASTA extension, return [path].
    - If it is a directory, return all FASTA files (non-recursive, sorted).
    - If it is a multi-record FASTA file, return [path] (split handled elsewhere).
    """
    if path.is_file():
        if path.suffix.lower() in FASTA_EXTENSIONS:
            return [path]
        raise ValueError(f"File does not have a recognised FASTA extension: {path}")

    if path.is_dir():
        files = sorted(
            p for p in path.iterdir()
            if p.is_file() and p.suffix.lower() in FASTA_EXTENSIONS
        )
        if not files:
            raise ValueError(f"No FASTA files found in directory: {path}")
        return files

    raise ValueError(f"Input path does not exist: {path}")


def count_records(fasta_path: Path) -> int:
    """Return the number of records in a FASTA file (streaming, low memory)."""
    count = 0
    with open(fasta_path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith(">"):
                count += 1
    return count


def iter_records(fasta_path: Path) -> Iterator[SeqRecord]:
    """Stream records from a FASTA file one at a time."""
    with open(fasta_path, encoding="utf-8") as fh:
        yield from SeqIO.parse(fh, "fasta")


def validate_fasta(fasta_path: Path) -> Tuple[int, int]:
    """
    Basic validation: check the file is parseable and all sequences use
    IUPAC nucleotide characters (A/T/G/C/N + ambiguity codes).

    Returns (record_count, total_bp).
    Raises ValueError on the first invalid record.
    """
    valid_chars = set("ACGTNacgtnRYSWKMBDHVryswkmbdhv")
    record_count = 0
    total_bp = 0

    for rec in iter_records(fasta_path):
        record_count += 1
        seq_str = str(rec.seq)
        invalid = set(seq_str) - valid_chars
        if invalid:
            raise ValueError(
                f"Record '{rec.id}' in {fasta_path} contains unexpected characters: "
                f"{', '.join(sorted(invalid))}"
            )
        total_bp += len(seq_str)

    if record_count == 0:
        raise ValueError(f"No records found in FASTA file: {fasta_path}")

    logger.debug("Validated %s: %d record(s), %d bp total", fasta_path.name, record_count, total_bp)
    return record_count, total_bp


def split_multifasta(fasta_path: Path, output_dir: Path) -> List[Path]:
    """
    Split a multi-record FASTA into individual single-record files.
    Each file is named after the record ID.
    Returns list of created file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    created: List[Path] = []

    for rec in iter_records(fasta_path):
        safe_id = rec.id.replace("/", "_").replace(" ", "_")
        out_path = output_dir / f"{safe_id}.fasta"
        with open(out_path, "w", encoding="utf-8") as fh:
            SeqIO.write(rec, fh, "fasta")
        created.append(out_path)
        logger.debug("Split record '%s' → %s", rec.id, out_path.name)

    logger.info("Split %d records from %s", len(created), fasta_path.name)
    return created
