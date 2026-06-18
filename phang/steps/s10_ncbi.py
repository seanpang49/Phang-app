"""
Step 10: NCBI BankIt package generation.

Produces two files in <output>/ncbi/:

  bankit_multi.fasta   — combined BankIt-ready multifasta
                         headers: >Seq1 [organism=Acinetobacter phage ButterPeanut]

  bankit_mapping.tsv   — SeqID <-> InputFile <-> OldHeader <-> OrganismField

  bankit_features.tbl  — combined 5-column feature table
                         (relabeled from Pharokka .tbl using mapping above)

Design note (from CLAUDE.md):
  Feature table uses Pharokka's raw .tbl — BankIt expects that format.
  All richer annotations (Phold/Phynteny) are used only in the report card.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from phang.utils.organism import extract_organism_and_name

logger = logging.getLogger(__name__)

_WRAP_WIDTH = 80


# ---------------------------------------------------------------------------
# FASTA helpers (pure Python — no Biopython, avoids loading full records)
# ---------------------------------------------------------------------------

def _iter_fasta_records(path: Path) -> Iterator[Tuple[str, str]]:
    """Yield (header_without_>, sequence) for each record in a FASTA file."""
    header: Optional[str] = None
    seq_chunks: List[str] = []

    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(seq_chunks)
                header = line[1:].strip()
                seq_chunks = []
            else:
                seq_chunks.append(line.replace(" ", "").upper())

    if header is not None:
        yield header, "".join(seq_chunks)


def _wrap(seq: str, width: int = _WRAP_WIDTH) -> str:
    return "\n".join(seq[i : i + width] for i in range(0, len(seq), width))


# ---------------------------------------------------------------------------
# 10a: Multifasta
# ---------------------------------------------------------------------------

def _build_multifasta(
    fasta_files: List[Path],
    out_fasta: Path,
    out_mapping: Path,
) -> List[Tuple[str, str, str, str]]:
    """
    Combine all FASTA files into a single BankIt-ready multifasta.

    Returns list of (seqid, inputfile_name, old_header, organism_field) rows.
    """
    out_fasta.parent.mkdir(parents=True, exist_ok=True)
    out_mapping.parent.mkdir(parents=True, exist_ok=True)

    mapping_rows: List[Tuple[str, str, str, str]] = []
    seq_counter = 0

    with open(out_fasta, "w", encoding="utf-8") as fh:
        for fasta in fasta_files:
            for old_header, seq in _iter_fasta_records(fasta):
                if not seq:
                    continue

                seq_counter += 1
                seqid = f"Seq{seq_counter}"

                org_prefix, phage_name = extract_organism_and_name(old_header, fasta.stem)
                organism_field = f"{org_prefix} {phage_name}".strip()

                fh.write(f">{seqid} [organism={organism_field}]\n")
                fh.write(_wrap(seq) + "\n\n")

                mapping_rows.append((seqid, fasta.name, old_header, organism_field))

    # Write mapping TSV
    with open(out_mapping, "w", encoding="utf-8") as mh:
        mh.write("SeqID\tInputFile\tOldHeader\tOrganismField\n")
        for seqid, infile, old_header, organism_field in mapping_rows:
            mh.write(f"{seqid}\t{infile}\t{old_header}\t{organism_field}\n")

    logger.info("BankIt multifasta: %d sequence(s) → %s", seq_counter, out_fasta.name)
    return mapping_rows


# ---------------------------------------------------------------------------
# 10b: Feature table
# ---------------------------------------------------------------------------

def _load_mapping_tsv(mapping_path: Path) -> Dict[str, str]:
    """
    Parse mapping TSV and return {InputFile -> SeqID}.
    InputFile is the bare filename (e.g. 'PhageX.fasta').
    """
    lines = mapping_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"Mapping TSV is empty: {mapping_path}")

    header = lines[0].split("\t")
    try:
        idx_seqid = header.index("SeqID")
        idx_input = header.index("InputFile")
    except ValueError as exc:
        raise ValueError(
            f"Mapping TSV must contain 'SeqID' and 'InputFile' columns: {mapping_path}"
        ) from exc

    result: Dict[str, str] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) <= max(idx_seqid, idx_input):
            continue
        seqid = parts[idx_seqid].strip()
        infile = parts[idx_input].strip()
        if seqid and infile:
            result[infile] = seqid

    return result


def _rewrite_tbl_seqid(tbl_text: str, seqid: str) -> str:
    """
    Replace the first line of a Pharokka .tbl with '>Feature <seqid>'.
    Pharokka already emits the 5-column NCBI format; we only need to
    swap the sequence identifier on the header line.
    """
    lines = tbl_text.splitlines()
    if not lines:
        return f">Feature {seqid}\n"
    lines[0] = f">Feature {seqid}"
    return "\n".join(lines).rstrip() + "\n"


def _build_feature_table(
    results: Dict[str, Any],
    mapping_rows: List[Tuple[str, str, str, str]],
    out_tbl: Path,
) -> int:
    """
    Build the combined BankIt feature table from per-phage pharokka.tbl files.

    mapping_rows is the list returned by _build_multifasta:
        (seqid, inputfile_name, old_header, organism_field)

    Returns the number of feature tables included.
    """
    # Build lookup: inputfile_name -> seqid
    file_to_seqid: Dict[str, str] = {row[1]: row[0] for row in mapping_rows}

    out_tbl.parent.mkdir(parents=True, exist_ok=True)
    blocks: List[str] = []
    missing_tbl: List[str] = []
    missing_map: List[str] = []

    for stem, per in results.items():
        tbl_path: Optional[Path] = per.get("pharokka_tbl")
        fasta: Optional[Path] = per.get("fasta")

        if not tbl_path or not tbl_path.exists():
            missing_tbl.append(stem)
            continue

        # Look up SeqID using the input FASTA filename
        fasta_name = fasta.name if fasta else f"{stem}.fasta"
        seqid = file_to_seqid.get(fasta_name)
        if not seqid:
            missing_map.append(fasta_name)
            continue

        tbl_text = tbl_path.read_text(encoding="utf-8")
        blocks.append(_rewrite_tbl_seqid(tbl_text, seqid))

    if missing_tbl:
        logger.warning("pharokka.tbl not found for: %s", ", ".join(missing_tbl))
    if missing_map:
        logger.warning(
            "No SeqID mapping for these files: %s\n"
            "  Tip: InputFile in mapping must match the input FASTA filename exactly.",
            ", ".join(missing_map),
        )

    if not blocks:
        raise RuntimeError(
            "No feature table blocks were generated. "
            "Check that pharokka.tbl files exist and mapping TSV is correct."
        )

    out_tbl.write_text("".join(blocks), encoding="utf-8")
    logger.info("BankIt feature table: %d block(s) → %s", len(blocks), out_tbl.name)
    return len(blocks)


# ---------------------------------------------------------------------------
# Step entry point
# ---------------------------------------------------------------------------

def run_ncbi(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 10 entry point.

    Reads from ctx : fasta_files, results (per-phage pharokka_tbl + fasta paths), output_path
    Writes to ctx  : ncbi_dir, ncbi_multifasta, ncbi_mapping, ncbi_features_tbl
    """
    fasta_files: List[Path] = ctx["fasta_files"]
    output_path: Path = ctx["output_path"]
    results: Dict[str, Any] = ctx["results"]

    ncbi_dir = output_path / "ncbi"
    out_fasta = ncbi_dir / "bankit_multi.fasta"
    out_mapping = ncbi_dir / "bankit_mapping.tsv"
    out_tbl = ncbi_dir / "bankit_features.tbl"

    # 10a — multifasta
    logger.info("  Building BankIt multifasta…")
    mapping_rows = _build_multifasta(
        fasta_files=fasta_files,
        out_fasta=out_fasta,
        out_mapping=out_mapping,
    )

    # 10b — feature table
    logger.info("  Building BankIt feature table…")
    _build_feature_table(
        results=results,
        mapping_rows=mapping_rows,
        out_tbl=out_tbl,
    )

    ctx["ncbi_dir"] = ncbi_dir
    ctx["ncbi_multifasta"] = out_fasta
    ctx["ncbi_mapping"] = out_mapping
    ctx["ncbi_features_tbl"] = out_tbl

    logger.info("NCBI BankIt package ready: %s", ncbi_dir)
    return ctx
