"""
Auto-detect organism prefix and phage name from FASTA headers.

Ported from bankit_multifasta.py — centralised here so both the NCBI step
and the CLI can reuse it.
"""

import re
from pathlib import Path
from typing import Optional, Tuple


# Ordered list of (genus, regex_prefix_pattern) for known phage naming conventions.
# Add more genera here as needed.
_KNOWN_GENUS_PATTERNS = [
    ("Acinetobacter", re.compile(r"^acinetobacter[_ ]phage[_ ]", re.IGNORECASE)),
    ("Pseudomonas",   re.compile(r"^pseudomonas[_ ]phage[_ ]",   re.IGNORECASE)),
    ("Klebsiella",    re.compile(r"^klebsiella[_ ]phage[_ ]",     re.IGNORECASE)),
    ("Staphylococcus",re.compile(r"^staphylococcus[_ ]phage[_ ]",re.IGNORECASE)),
    ("Escherichia",   re.compile(r"^escherichia[_ ]phage[_ ]",    re.IGNORECASE)),
    ("Salmonella",    re.compile(r"^salmonella[_ ]phage[_ ]",     re.IGNORECASE)),
    ("Mycobacterium", re.compile(r"^mycobacterium[_ ]phage[_ ]",  re.IGNORECASE)),
]

_GENERIC_PHAGE_PATTERN = re.compile(r"^phage[_ ]", re.IGNORECASE)


def extract_organism_and_name(header: str, fallback_stem: str = "") -> Tuple[str, str]:
    """
    Parse a FASTA header and return (organism_prefix, phage_name).

    Examples
    --------
    "Acinetobacter_phage_ButterPeanut ..."  → ("Acinetobacter phage", "ButterPeanut")
    "phage_ButterPeanut"                    → ("phage", "ButterPeanut")
    "random_header"                         → ("phage", "random_header")  or uses fallback_stem
    """
    first_token = header.strip().split()[0]

    for genus, pattern in _KNOWN_GENUS_PATTERNS:
        if pattern.match(first_token):
            phage_name = pattern.sub("", first_token).strip("_").strip()
            if phage_name:
                return f"{genus} phage", phage_name

    if _GENERIC_PHAGE_PATTERN.match(first_token):
        phage_name = _GENERIC_PHAGE_PATTERN.sub("", first_token).strip("_").strip()
        if phage_name:
            return "phage", phage_name

    # Search anywhere in the full header for "phage <Name>"
    m = re.search(r"\bphage[_ ]+([A-Za-z0-9_.:#*\-]+)", header, re.IGNORECASE)
    if m:
        candidate = m.group(1)
        # Try to detect genus from text before "phage"
        genus_match = re.search(r"(\b[A-Z][a-z]+)[_ ]phage[_ ]", header)
        genus = genus_match.group(1) if genus_match else ""
        prefix = f"{genus} phage".strip() if genus else "phage"
        return prefix, candidate

    # No pattern matched — use the first token (or fallback stem) as the name
    name = first_token or fallback_stem or "unknown"
    return "phage", name


def organism_prefix_from_fasta(fasta_path: Path) -> Tuple[str, str]:
    """
    Read the first FASTA header from *fasta_path* and return
    (organism_prefix, phage_name).
    """
    with open(fasta_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(">"):
                header = line[1:].strip()
                return extract_organism_and_name(header, fasta_path.stem)

    # Empty / headerless file
    return "phage", fasta_path.stem
