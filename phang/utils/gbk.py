"""
GenBank parsing helpers used across multiple pipeline steps.
"""

import logging
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from Bio import SeqIO
from Bio.SeqRecord import SeqRecord

logger = logging.getLogger(__name__)


def iter_gbk(gbk_path: Path) -> Iterator[SeqRecord]:
    """Stream records from a GenBank file."""
    with open(gbk_path, encoding="utf-8") as fh:
        yield from SeqIO.parse(fh, "genbank")


def find_gbk(directory: Path) -> Optional[Path]:
    """
    Find the primary GenBank file in *directory*.

    Checks common Pharokka/Phold output filenames first, then falls back to
    any *.gbk / *.gbff / *.gb file.
    """
    for name in ["pharokka.gbk", "pharokka.gbff", "pharokka.gb",
                 "phold.gbk", "phold.gbff", "phold.gb"]:
        candidate = directory / name
        if candidate.exists():
            return candidate

    for pattern in ("*.gbk", "*.gbff", "*.gb"):
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0]

    return None


def get_genome_stats(gbk_path: Path) -> Dict[str, object]:
    """
    Extract basic genome statistics from a GenBank file.

    Returns a dict with keys: length, gc_percent, cds_count, trna_count,
    organism, accession.
    """
    stats: Dict[str, object] = {
        "length": 0,
        "gc_percent": 0.0,
        "cds_count": 0,
        "trna_count": 0,
        "organism": "unknown",
        "accession": "unknown",
    }

    for rec in iter_gbk(gbk_path):
        seq_str = str(rec.seq).upper()
        stats["length"] = len(seq_str)
        g = seq_str.count("G")
        c = seq_str.count("C")
        stats["gc_percent"] = round((g + c) / len(seq_str) * 100, 2) if seq_str else 0.0
        stats["accession"] = rec.id
        stats["organism"] = rec.annotations.get("organism", "unknown")

        for feat in rec.features:
            if feat.type == "CDS":
                stats["cds_count"] = int(stats["cds_count"]) + 1  # type: ignore[arg-type]
            elif feat.type == "tRNA":
                stats["trna_count"] = int(stats["trna_count"]) + 1  # type: ignore[arg-type]

        # Only process first record
        break

    return stats


def get_phrog_category_counts(gbk_path: Path) -> Dict[str, int]:
    """
    Count CDS features grouped by PHROG functional category.

    Looks for the 'phrog_category' or 'function' qualifier on CDS features.
    Returns a dict mapping category name → count.
    """
    counts: Dict[str, int] = {}

    for rec in iter_gbk(gbk_path):
        for feat in rec.features:
            if feat.type != "CDS":
                continue
            category = (
                feat.qualifiers.get("phrog_category", [None])[0]
                or feat.qualifiers.get("function", ["unknown"])[0]
                or "unknown"
            )
            counts[category] = counts.get(category, 0) + 1

    return counts
