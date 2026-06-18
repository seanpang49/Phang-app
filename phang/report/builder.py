"""
Report builder: assembles per-phage data from pipeline context into a
clean Python dict that the HTML template can consume directly.

All file parsing happens here. The template receives only plain dicts/lists.
"""

from __future__ import annotations

import ast
import base64
import csv
import json
import logging
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)
_VC3_CLOSEST_CACHE_VERSION = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_tsv(path: Optional[Path]) -> List[Dict[str, str]]:
    """Return rows of a TSV as list-of-dicts. Empty list if file missing."""
    if not path or not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            return list(csv.DictReader(fh, delimiter="\t"))
    except Exception as exc:
        logger.debug("Could not read TSV %s: %s", path, exc)
        return []


def _read_csv(path: Optional[Path]) -> List[Dict[str, str]]:
    """Return rows of a CSV as list-of-dicts. Empty list if file missing."""
    if not path or not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except Exception as exc:
        logger.debug("Could not read CSV %s: %s", path, exc)
        return []


def _read_table(path: Optional[Path]) -> List[Dict[str, str]]:
    """Read a small delimited file, preferring the delimiter implied by suffix."""
    if not path or not path.exists():
        return []

    readers = [_read_csv, _read_tsv] if path.suffix.lower() == ".csv" else [_read_tsv, _read_csv]
    for reader in readers:
        rows = reader(path)
        if not rows:
            continue
        if len(rows[0].keys()) > 1:
            return rows
    return []


def _has_meaningful_rows(rows: List[Dict[str, str]]) -> bool:
    """Return True if any row contains at least one non-empty, non-placeholder value."""
    placeholders = {"", "none", "nan", "n/a", "na", "no_hit", "no hits", "no_hit_found"}
    for row in rows:
        for value in row.values():
            text = (value or "").strip()
            if not text:
                continue
            if text.lower() in placeholders:
                continue
            return True
    return False


def _normalize_host_value(value: Optional[str]) -> str:
    """Normalize host no-call placeholders to a user-facing label."""
    host = (value or "").strip()
    if not host:
        return ""
    if host in {"-", "—"}:
        return "Undetermined"
    if host.lower() in {"na", "n/a", "none", "null", "unknown", "undetermined"}:
        return "Undetermined"
    return host


def _normalize_taxonomy_value(value: Optional[str]) -> str:
    label = (value or "").strip()
    if not label or label.lower() in {"nan", "none"}:
        return "—"
    if label.lower().startswith("novel_"):
        return "Unassigned"
    return label


def _is_placeholder_taxonomy_value(value: Optional[str]) -> bool:
    label = (value or "").strip()
    if not label:
        return True
    return label in {"—", "-", "Novel", "Unassigned"} or label.lower() in {"nan", "none"} or label.lower().startswith("novel_")


def _taxonomy_record_to_ranks(record: Dict[str, Any]) -> Dict[str, str]:
    lineage = {
        item.get("Rank"): item.get("ScientificName")
        for item in record.get("LineageEx", [])
        if item.get("Rank") and item.get("ScientificName")
    }
    record_rank = record.get("Rank")
    record_name = record.get("ScientificName", "—") or "—"

    order = lineage.get("order", "—") or "—"
    family = lineage.get("family", "—") or "—"
    genus = lineage.get("genus", "—") or "—"
    if record_rank == "order" and order == "—":
        order = record_name
    if record_rank == "family" and family == "—":
        family = record_name
    if record_rank == "genus" and genus == "—":
        genus = record_name

    return {
        "order": order,
        "family": family,
        "genus": genus,
        "name": record_name,
    }


def _pick_consensus_taxonomy_value(values: List[Optional[str]]) -> str:
    candidates = [
        (value or "").strip()
        for value in values
        if not _is_placeholder_taxonomy_value(value)
    ]
    if not candidates:
        return ""
    counts = Counter(candidates)
    top = counts.most_common(2)
    if len(top) > 1 and top[0][1] == top[1][1] and top[0][0] != top[1][0]:
        return ""
    return top[0][0]


def _png_to_b64(path: Optional[Path]) -> Optional[str]:
    """Return a base64-encoded PNG as a data-URI string, or None."""
    if not path or not path.exists():
        return None
    try:
        data = path.read_bytes()
        return "data:image/png;base64," + base64.b64encode(data).decode("ascii")
    except Exception as exc:
        logger.debug("Could not encode PNG %s: %s", path, exc)
        return None


_MAX_EMBED_BYTES = 20 * 1024 * 1024  # 20 MB — skip embedding files larger than this


def _file_b64(path: Optional[Path], mime: str = "text/plain") -> Optional[str]:
    """
    Return a base64 data-URI for any file (for download links).
    Returns None if file is missing or too large to embed (> 20 MB).
    """
    if not path or not path.exists():
        return None
    try:
        size = path.stat().st_size
        if size > _MAX_EMBED_BYTES:
            logger.debug("Skipping embed (too large: %d MB): %s", size // 1024 // 1024, path.name)
            return None
        data = path.read_bytes()
        return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")
    except Exception:
        return None


def _file_info(path: Optional[Path]) -> Optional[Dict]:
    """Return dict with name, size_kb, exists, and b64 data-URI (if small enough)."""
    if not path or not path.exists():
        return None
    size = path.stat().st_size
    return {
        "name":    path.name,
        "size_kb": round(size / 1024, 1),
        "b64":     _file_b64(path, _guess_mime(path.suffix)),
        "path":    str(path),
    }


def _guess_mime(suffix: str) -> str:
    return {
        ".gbk": "text/plain", ".gb": "text/plain", ".gbff": "text/plain",
        ".fasta": "text/plain", ".fa": "text/plain", ".faa": "text/plain",
        ".ffn": "text/plain", ".fna": "text/plain",
        ".gff": "text/plain", ".tbl": "text/plain",
        ".tsv": "text/tab-separated-values",
        ".csv": "text/csv",
        ".png": "image/png",
        ".json": "application/json",
        ".cyjs": "application/json",
        ".graphml": "application/xml",
        ".parquet": "application/octet-stream",
        ".log": "text/plain",
    }.get(suffix.lower(), "text/plain")


# ---------------------------------------------------------------------------
# Per-section parsers
# ---------------------------------------------------------------------------

def _parse_genome_stats(gbk_path: Optional[Path]) -> Dict[str, Any]:
    """Extract basic stats from the best available GBK."""
    if not gbk_path or not gbk_path.exists():
        return {"length": 0, "gc_percent": 0.0, "cds_count": 0, "trna_count": 0,
                "organism": "unknown", "accession": "unknown"}
    from phang.utils.gbk import get_genome_stats
    return get_genome_stats(gbk_path)


def _parse_phrog_categories(gbk_path: Optional[Path]) -> List[Dict[str, Any]]:
    """Return PHROG category counts with colours for the bar chart."""
    from phang.utils.gbk import get_phrog_category_counts
    from phang.steps.s09_genome_viz import PHROG_COLORS, _DEFAULT_COLOR

    if not gbk_path or not gbk_path.exists():
        return []

    counts = get_phrog_category_counts(gbk_path)
    result = []
    for name, count in sorted(counts.items(), key=lambda x: -x[1]):
        color = PHROG_COLORS.get(name.lower().strip(), _DEFAULT_COLOR)
        result.append({"name": name, "count": count, "color": color})
    return result


def _parse_genome_map_data(gbk_path: Optional[Path]) -> Dict[str, Any]:
    """Return feature and track data for an interactive circular genome map."""
    if not gbk_path or not gbk_path.exists():
        return {"length": 0, "gc_percent": 0.0, "features": [], "gc_content": [], "gc_skew": []}

    from Bio import SeqIO
    from Bio.SeqUtils import gc_fraction
    from phang.steps.s09_genome_viz import PHROG_COLORS, _DEFAULT_COLOR

    with open(gbk_path, encoding="utf-8") as fh:
        rec = next(SeqIO.parse(fh, "genbank"), None)
    if rec is None:
        return {"length": 0, "gc_percent": 0.0, "features": [], "gc_content": [], "gc_skew": []}

    seq = str(rec.seq).upper()
    genome_length = len(seq)
    gc_percent = round(gc_fraction(seq) * 100, 2)

    features: List[Dict[str, Any]] = []
    for feat in rec.features:
        if feat.type != "CDS":
            continue
        start = int(feat.location.start)
        end = int(feat.location.end)
        strand = feat.location.strand if feat.location.strand is not None else 1
        locus_tag = feat.qualifiers.get("locus_tag", [""])[0]
        gene = feat.qualifiers.get("gene", [""])[0]
        product = (
            feat.qualifiers.get("product", [""])[0]
            or feat.qualifiers.get("function", [""])[0]
            or "hypothetical protein"
        )
        category = (
            feat.qualifiers.get("phrog_category", [None])[0]
            or feat.qualifiers.get("function", [None])[0]
            or "unknown function"
        )
        color = PHROG_COLORS.get(str(category).lower().strip(), _DEFAULT_COLOR)
        features.append({
            "start": start,
            "end": end,
            "strand": strand,
            "color": color,
            "locus_tag": locus_tag,
            "gene": gene,
            "product": product,
            "category": category,
        })

    window = max(1000, genome_length // 200)
    step = max(500, genome_length // 300)
    gc_content_track: List[float] = []
    gc_skew_track: List[float] = []
    for pos in range(0, genome_length, step):
        w = seq[pos : pos + window]
        if len(w) < 10:
            break
        g = w.count("G")
        c = w.count("C")
        total = len(w)
        gc_content_track.append((g + c) / total if total else 0.0)
        gc_skew_track.append((g - c) / (g + c) if (g + c) > 0 else 0.0)

    return {
        "length": genome_length,
        "gc_percent": gc_percent,
        "features": features,
        "gc_content": gc_content_track,
        "gc_skew": gc_skew_track,
    }


def _find_blastn_binary() -> Optional[str]:
    candidates = [
        shutil.which("blastn"),
        str(Path.home() / ".phang" / "envs" / "cherry" / "bin" / "blastn"),
        str(Path.home() / ".phang" / "envs" / "phabox2" / "bin" / "blastn"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _run_ncbi_virus_blast(query_fasta: Path, max_hits: int = 15) -> List[Dict[str, Any]]:
    blastn = _find_blastn_binary()
    if not blastn:
        logger.debug("Closest phages lookup skipped: blastn binary not found")
        return []

    outfmt = (
        "6 saccver staxids sscinames sblastnames stitle "
        "pident length qcovs evalue bitscore"
    )
    cmd = [
        blastn,
        "-task", "megablast",
        "-query", str(query_fasta),
        "-db", "nt",
        "-remote",
        "-entrez_query", "Viruses[Organism]",
        "-max_target_seqs", str(max_hits),
        "-max_hsps", "1",
        "-outfmt", outfmt,
    ]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:
        logger.debug("Remote BLAST failed to run: %s", exc)
        return []

    if proc.returncode != 0:
        logger.debug("Remote BLAST failed: %s", proc.stderr.strip())
        return []

    hits: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 10:
            continue
        accession, staxids, sscinames, sblastnames, title, pident, aln_len, qcovs, evalue, bitscore = parts[:10]
        taxid = next((item for item in staxids.split(";") if item.isdigit()), "")
        haystack = " ".join([title, sscinames, sblastnames]).lower()
        if "phage" not in haystack:
            continue
        if accession in seen:
            continue
        seen.add(accession)
        try:
            bitscore_num = float(bitscore)
        except ValueError:
            bitscore_num = 0.0
        try:
            pident_num = float(pident)
        except ValueError:
            pident_num = 0.0
        try:
            qcovs_num = float(qcovs)
        except ValueError:
            qcovs_num = 0.0
        hits.append({
            "accession": accession,
            "taxid": taxid,
            "title": title,
            "scientific_name": sscinames,
            "blast_name": sblastnames,
            "pident": pident_num,
            "qcovs": qcovs_num,
            "alignment_length": aln_len,
            "evalue": evalue,
            "bitscore": bitscore_num,
        })
    return hits


def _fetch_ncbi_taxonomy(taxids: List[str]) -> Dict[str, Dict[str, str]]:
    if not taxids:
        return {}

    from Bio import Entrez

    Entrez.email = "phang@pipeline.local"
    taxonomy: Dict[str, Dict[str, str]] = {}
    for i in range(0, len(taxids), 20):
        batch = taxids[i:i + 20]
        try:
            handle = Entrez.efetch(db="taxonomy", id=",".join(batch), retmode="xml")
            records = Entrez.read(handle)
            handle.close()
        except Exception as exc:
            logger.debug("NCBI taxonomy fetch failed: %s", exc)
            continue

        for record in records:
            taxid = str(record.get("TaxId", ""))
            taxonomy[taxid] = _taxonomy_record_to_ranks(record)
    return taxonomy


def _fetch_ncbi_taxonomy_by_names(names: List[str]) -> Dict[str, Dict[str, str]]:
    cleaned = []
    seen = set()
    for name in names:
        label = (name or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        cleaned.append(label)
    if not cleaned:
        return {}

    from Bio import Entrez

    Entrez.email = "phang@pipeline.local"
    taxonomy: Dict[str, Dict[str, str]] = {}
    for name in cleaned:
        try:
            handle = Entrez.esearch(db="taxonomy", term=f"{name}[Scientific Name]")
            search = Entrez.read(handle)
            handle.close()
            ids = search.get("IdList") or []
            if not ids:
                continue
            handle = Entrez.efetch(db="taxonomy", id=ids[0], retmode="xml")
            records = Entrez.read(handle)
            handle.close()
            if records:
                taxonomy[name] = _taxonomy_record_to_ranks(records[0])
        except Exception as exc:
            logger.debug("NCBI taxonomy name lookup failed for %s: %s", name, exc)
    return taxonomy


def _read_vcontact3_user_row(assignments_csv: Optional[Path]) -> Dict[str, str]:
    """Return the vConTACT3 row for the user's phage."""
    if not assignments_csv or not assignments_csv.exists():
        return {}
    rows = _read_csv(assignments_csv)
    for row in rows:
        ref = row.get("Reference", "True").strip().lower()
        if ref in ("false", "0", ""):
            return row
    return {}


def _parse_closest_phages(
    assignments_csv: Optional[Path],
    vcontact3_dir: Optional[Path],
    top_n: int = 5,
) -> List[Dict]:
    """Find closest phages from the vConTACT3 protein-sharing network."""
    if not assignments_csv or not assignments_csv.exists() or not vcontact3_dir:
        return []

    graphml_path = vcontact3_dir / "exports" / "networks" / "part1.graphml"
    if not graphml_path.exists():
        return []

    cache_path = vcontact3_dir.parent / "closest_phages_vcontact3.json"
    if (
        cache_path.exists()
        and cache_path.stat().st_mtime >= graphml_path.stat().st_mtime
        and cache_path.stat().st_mtime >= assignments_csv.stat().st_mtime
    ):
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("version") != _VC3_CLOSEST_CACHE_VERSION:
                raise ValueError("stale closest-phages cache format")
            results = cached.get("results") or []
            if results:
                return results[:top_n]
        except Exception as exc:
            logger.debug("Closest phages cache read failed: %s", exc)

    user_row = _read_vcontact3_user_row(assignments_csv)
    sample_node_id = (
        (user_row.get("Genome") or "").strip()
        or (user_row.get("contig_id") or "").strip()
        or (user_row.get("label") or "").strip()
    )
    if not sample_node_id:
        return []

    try:
        key_names: Dict[str, str] = {}
        node_data: Dict[str, Dict[str, str]] = {}
        edge_rows: List[Dict[str, Any]] = []

        for _, elem in ET.iterparse(graphml_path, events=("end",)):
            tag = elem.tag.rsplit("}", 1)[-1]

            if tag == "key":
                key_id = elem.attrib.get("id", "")
                key_names[key_id] = elem.attrib.get("attr.name", key_id)
                elem.clear()
            elif tag == "node":
                node_id = elem.attrib.get("id", "")
                data: Dict[str, str] = {}
                for child in elem:
                    child_tag = child.tag.rsplit("}", 1)[-1]
                    if child_tag != "data":
                        continue
                    key = key_names.get(child.attrib.get("key", ""), child.attrib.get("key", ""))
                    data[key] = (child.text or "").strip()
                if node_id:
                    node_data[node_id] = data
                elem.clear()
            elif tag == "edge":
                source = elem.attrib.get("source", "")
                target = elem.attrib.get("target", "")
                if sample_node_id not in {source, target}:
                    elem.clear()
                    continue
                data: Dict[str, str] = {}
                for child in elem:
                    child_tag = child.tag.rsplit("}", 1)[-1]
                    if child_tag != "data":
                        continue
                    key = key_names.get(child.attrib.get("key", ""), child.attrib.get("key", ""))
                    data[key] = (child.text or "").strip()
                other_id = target if source == sample_node_id else source
                other = node_data.get(other_id, {})
                try:
                    distance = float(data.get("distance", "nan"))
                except ValueError:
                    distance = float("inf")
                try:
                    shared_genes = int(data.get("shared_genes", "0"))
                except ValueError:
                    shared_genes = 0
                edge_rows.append({
                    "genome_id": other_id,
                    "name": other.get("GenomeName") or other_id,
                    "order": _normalize_taxonomy_value(other.get("order_reference") or other.get("order_prediction")),
                    "family": _normalize_taxonomy_value(other.get("family_reference") or other.get("family_prediction")),
                    "subfamily": _normalize_taxonomy_value(other.get("subfamily_reference") or other.get("subfamily_prediction")),
                    "genus": _normalize_taxonomy_value(other.get("genus_reference") or other.get("genus_prediction")),
                    "distance": round(distance, 4) if distance != float("inf") else None,
                    "shared_genes": shared_genes,
                    "ncbi_url": f"https://www.ncbi.nlm.nih.gov/nuccore/{other_id}" if "." in other_id else "",
                })
                elem.clear()
                continue

        results = [row for row in edge_rows if row.get("genome_id")]
        results.sort(
            key=lambda row: (
                row["distance"] is None,
                float(row["distance"] or 999999.0),
                -int(row.get("shared_genes") or 0),
                row["genome_id"],
            )
        )
        final_results = results[:top_n]
        try:
            cache_path.write_text(
                json.dumps({"version": _VC3_CLOSEST_CACHE_VERSION, "results": final_results}, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("Closest phages cache write failed: %s", exc)
        return final_results
    except Exception as exc:
        logger.debug("Closest phages lookup failed: %s", exc)
        return []


def _resolve_taxonomy_with_ncbi_fallback(
    taxonomy: Dict[str, str],
    closest_phages: List[Dict[str, Any]],
) -> tuple[Dict[str, str], str]:
    source = "vConTACT3 v3.1.6 — RefSeq v230"
    if not taxonomy:
        return taxonomy, source

    genus = taxonomy.get("genus", "")
    if _is_placeholder_taxonomy_value(genus):
        return taxonomy, source

    resolved = dict(taxonomy)
    overrides: Dict[str, str] = {}
    target_ranks = ("order", "family")
    used_neighbor_consensus = False
    used_ncbi_fallback = False

    same_genus_hits = [
        row for row in closest_phages
        if (row.get("genus") or "").strip().casefold() == genus.strip().casefold()
    ]

    for rank in target_ranks:
        if _is_placeholder_taxonomy_value(resolved.get(rank)):
            consensus = _pick_consensus_taxonomy_value([row.get(rank) for row in same_genus_hits])
            if consensus:
                overrides[rank] = consensus
                used_neighbor_consensus = True

    unresolved = [
        rank for rank in target_ranks
        if _is_placeholder_taxonomy_value(resolved.get(rank)) and rank not in overrides
    ]
    if unresolved:
        lookup_names = [row.get("name", "") for row in same_genus_hits if row.get("name")] + [genus]
        taxonomy_by_name = _fetch_ncbi_taxonomy_by_names(lookup_names)
        for rank in unresolved:
            consensus = _pick_consensus_taxonomy_value([
                taxonomy_by_name.get(name, {}).get(rank)
                for name in lookup_names
            ])
            if consensus:
                overrides[rank] = consensus
                used_ncbi_fallback = True

    if not overrides:
        return resolved, source

    resolved.update(overrides)
    suffixes = []
    if used_neighbor_consensus:
        suffixes.append("vConTACT3 neighbor consensus")
    if used_ncbi_fallback:
        suffixes.append("NCBI Taxonomy fallback")
    if suffixes:
        return resolved, f"{source} + {' + '.join(suffixes)}"
    return resolved, source


def _compute_ani_pyskani(query_fasta: Path, accessions: List[str]) -> Dict[str, float]:
    """
    Download reference sequences from NCBI and compute ANI against the query
    using pyskani. Returns {accession: ani_percent}.
    """
    import tempfile, time
    from Bio import Entrez, SeqIO
    import pyskani

    Entrez.email = "phang@pipeline.local"
    ani_scores: Dict[str, float] = {}

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)

        # Download reference sequences in batches of 10
        ref_fastas: Dict[str, Path] = {}
        for i in range(0, len(accessions), 10):
            batch = accessions[i:i + 10]
            try:
                handle = Entrez.efetch(
                    db="nucleotide", id=",".join(batch),
                    rettype="fasta", retmode="text",
                )
                records = list(SeqIO.parse(handle, "fasta"))
                handle.close()
                for rec in records:
                    acc = rec.id.split(".")[0]  # strip version
                    out = tmp / f"{acc}.fasta"
                    with open(out, "w") as fh:
                        SeqIO.write(rec, fh, "fasta")
                    ref_fastas[acc] = out
                time.sleep(0.34)  # NCBI rate limit: max 3/sec
            except Exception as exc:
                logger.debug("NCBI fetch failed for batch: %s", exc)
                continue

        if not ref_fastas:
            return {}

        # Build pyskani sketch of query
        sketcher = pyskani.Sketcher(k=21)
        with open(query_fasta, encoding="utf-8") as fh:
            for rec in SeqIO.parse(fh, "fasta"):
                sketcher.add_genome(str(query_fasta), str(rec.seq).encode())
        query_db = sketcher.to_database()

        # Compute ANI for each reference
        for acc, ref_path in ref_fastas.items():
            try:
                sketcher_ref = pyskani.Sketcher(k=21)
                with open(ref_path, encoding="utf-8") as fh:
                    for rec in SeqIO.parse(fh, "fasta"):
                        sketcher_ref.add_genome(acc, str(rec.seq).encode())
                ref_db = sketcher_ref.to_database()

                hits = query_db.query_database(ref_db)
                if hits:
                    ani_scores[acc] = hits[0].identity * 100
            except Exception as exc:
                logger.debug("pyskani ANI failed for %s: %s", acc, exc)

    return ani_scores


def _parse_lifestyle(predictions_path: Optional[Path]) -> Dict[str, Any]:
    """Parse PhaStyle predictions.tsv."""
    rows = _read_tsv(predictions_path)
    if not rows:
        return {"lifestyle": "Unknown", "confidence": 0.0}

    row = rows[0]
    # PhaStyle output columns vary slightly; try common names
    lifestyle = (
        row.get("predicted_label")
        or row.get("prediction")
        or row.get("lifestyle")
        or row.get("Prediction")
        or row.get("Lifestyle")
        or "Unknown"
    )
    lifestyle_lower = lifestyle.strip().lower()
    confidence_str = (
        row.get("score")
        or row.get("confidence")
        or row.get("Score")
        or row.get("Confidence")
        or row.get(f"score_{lifestyle_lower}")
        or "0"
    )
    try:
        confidence = float(confidence_str)
    except ValueError:
        confidence = 0.0

    return {"lifestyle": lifestyle.title(), "confidence": round(confidence, 4)}


def _parse_host(host_csv: Optional[Path]) -> List[Dict[str, str]]:
    """Parse normalized PhaBOX2 host_prediction.csv (or raw CHERRY-style output)."""
    rows = _read_csv(host_csv)
    if not rows and host_csv and host_csv.suffix == ".tsv":
        rows = _read_tsv(host_csv)
    if not rows:
        return []
    results = []
    for row in rows[:5]:  # top 5 predictions
        host = _normalize_host_value(
            row.get("host")
            or row.get("Host")
            or row.get("predicted_host")
            or row.get("Host_NCBI")
            or row.get("Host_GTDB")
            or ""
        )
        score = (
            row.get("score")
            or row.get("Score")
            or row.get("confidence")
            or row.get("CHERRYScore")
            or ""
        )
        if host:
            if host == "Undetermined":
                return [{"host": "Undetermined", "score": ""}]
            results.append({"host": host, "score": score})
    if rows and not results:
        return [{"host": "Undetermined", "score": ""}]
    return results


def _parse_taxonomy(assignments_csv: Optional[Path]) -> Dict[str, str]:
    """
    Parse vConTACT3 final_assignments.csv for the user's phage taxonomy.
    Returns full hierarchy from realm down to genus.
    """
    user_row = _read_vcontact3_user_row(assignments_csv)
    if not user_row:
        return {}

    def _val(key: str) -> str:
        return _normalize_taxonomy_value(user_row.get(key, ""))

    return {
        "realm":     _val("realm_prediction"),
        "kingdom":   _val("kingdom_prediction"),
        "phylum":    _val("phylum_prediction"),
        "class_":    _val("class_prediction"),
        "order":     _val("order_prediction"),
        "family":    _val("family_prediction"),
        "subfamily": _val("subfamily_prediction"),
        "genus":     _val("genus_prediction"),
    }


def _safe_fident_pct(value: Optional[str]) -> Optional[float]:
    """Parse a fident/seqIdentity value (0..1 fraction) into a 0..100 percentage."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "n/a", "na"}:
        return None
    try:
        f = float(text)
    except ValueError:
        return None
    if f > 1.0:
        # already a percentage
        return round(f, 1)
    return round(f * 100, 1)


def _parse_pharokka_card_hit_name(hit: str) -> str:
    """Extract a short gene name from a Pharokka CARD top-hit string."""
    parts = [p for p in hit.split("|") if p]
    if len(parts) >= 4:
        last = parts[-1].split("[")[0].strip()
        if last:
            return last
    return hit.strip()[:48] or "?"


def _parse_pharokka_vfdb_hit_name(hit: str) -> str:
    """Extract a short gene name from a Pharokka VFDB top-hit string.

    Format example: ``VFG043761(gb|CAA47852) (slt-IIcA) shiga-like toxin ...``
    Returns the first parenthesised alphabetic token after the VFG identifier.
    """
    import re
    m = re.search(r"\)\s*\(\s*([A-Za-z][^)]*)\)", hit)
    if m:
        return m.group(1).strip()
    return hit.strip()[:48] or "?"


def _parse_therapy_safety(
    phold_card_tsv: Optional[Path],
    phold_vfdb_tsv: Optional[Path],
    phold_gbk: Optional[Path] = None,
    pharokka_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Scan Pharokka + Phold outputs for red-flag hits.

    AMR/virulence are considered absent only when both Pharokka and Phold are
    negative. phold writes one TSV per sub-database (``card_cds_predictions.tsv``
    and ``vfdb_cds_predictions.tsv``) — there is no unified file, so each is
    consumed by name.

    Returns dict with the three safety bools (``no_amr``, ``no_virulence``,
    ``no_integrase``) plus two non-bool detail lists (``_amr_hits``,
    ``_vf_hits``) carrying gene name, % sequence identity, e-value, and
    detection source so the template can surface structural homologs by name.
    """
    amr_hits: List[Dict[str, Any]] = []
    vf_hits: List[Dict[str, Any]] = []

    for row in _read_tsv(phold_card_tsv):
        name = (
            row.get("CARD Short Name")
            or row.get("ARO Name")
            or row.get("Model Name")
            or "?"
        ).strip()
        amr_hits.append({
            "name": name,
            "identity_pct": _safe_fident_pct(row.get("fident")),
            "evalue": (row.get("evalue") or "").strip(),
            "source": "phold (foldseek 3D)",
            "drug_class": (row.get("Drug Class") or "").strip(),
            "mechanism": (row.get("Resistance Mechanism") or "").strip(),
        })

    for row in _read_tsv(phold_vfdb_tsv):
        name = (
            row.get("short_name")
            or row.get("vf_name")
            or "?"
        ).strip()
        vf_hits.append({
            "name": name,
            "identity_pct": _safe_fident_pct(row.get("fident")),
            "evalue": (row.get("evalue") or "").strip(),
            "source": "phold (foldseek 3D)",
            "description": (row.get("description") or "").strip(),
            "species": (row.get("species") or "").strip(),
        })

    if pharokka_dir and pharokka_dir.exists():
        for row in _read_tsv(pharokka_dir / "top_hits_card.tsv"):
            hit = (row.get("card_hit") or "").strip()
            if not hit or hit.lower() in {"none", "nan"}:
                continue
            amr_hits.append({
                "name": _parse_pharokka_card_hit_name(hit),
                "identity_pct": _safe_fident_pct(row.get("card_seqIdentity")),
                "evalue": "",
                "aln_score": (row.get("card_alnScore") or "").strip(),
                "source": "pharokka (MMseqs2)",
                "drug_class": "",
                "mechanism": "",
            })

        for row in _read_tsv(pharokka_dir / "top_hits_vfdb.tsv"):
            hit = (row.get("vfdb_hit") or "").strip()
            if not hit or hit.lower() in {"none", "nan"}:
                continue
            vf_hits.append({
                "name": _parse_pharokka_vfdb_hit_name(hit),
                "identity_pct": _safe_fident_pct(row.get("vfdb_seqIdentity")),
                "evalue": "",
                "aln_score": (row.get("vfdb_alnScore") or "").strip(),
                "source": "pharokka (MMseqs2)",
                "description": "",
                "species": "",
            })

        # Defensive: catch hits surfaced only in the merged output (different schema).
        if not amr_hits or not vf_hits:
            merged_rows = _read_tsv(pharokka_dir / "pharokka_cds_final_merged_output.tsv")
            for row in merged_rows:
                if not amr_hits:
                    card_hit = (row.get("CARD_hit") or row.get("card_hit") or "").strip()
                    if card_hit and card_hit.lower() not in {"none", "nan"}:
                        amr_hits.append({
                            "name": _parse_pharokka_card_hit_name(card_hit),
                            "identity_pct": _safe_fident_pct(
                                row.get("CARD_seqIdentity") or row.get("card_seqIdentity")
                            ),
                            "evalue": "",
                            "aln_score": (row.get("CARD_alnScore") or row.get("card_alnScore") or "").strip(),
                            "source": "pharokka (merged)",
                            "drug_class": "",
                            "mechanism": "",
                        })
                if not vf_hits:
                    vfdb_hit = (row.get("vfdb_hit") or "").strip()
                    if vfdb_hit and vfdb_hit.lower() not in {"none", "nan"}:
                        vf_hits.append({
                            "name": _parse_pharokka_vfdb_hit_name(vfdb_hit),
                            "identity_pct": _safe_fident_pct(row.get("vfdb_seqIdentity")),
                            "evalue": "",
                            "aln_score": (row.get("vfdb_alnScore") or "").strip(),
                            "source": "pharokka (merged)",
                            "description": "",
                            "species": "",
                        })
                if amr_hits and vf_hits:
                    break

    has_amr = bool(amr_hits)
    has_vf = bool(vf_hits)

    has_integrase = False
    if phold_gbk and phold_gbk.exists():
        try:
            from Bio import SeqIO

            with open(phold_gbk, encoding="utf-8") as fh:
                for rec in SeqIO.parse(fh, "genbank"):
                    for feat in rec.features:
                        if feat.type != "CDS":
                            continue
                        text = " ".join(
                            feat.qualifiers.get("product", [])
                            + feat.qualifiers.get("function", [])
                            + feat.qualifiers.get("note", [])
                        ).lower()
                        if (
                            "integrase" in text
                            or "excisionase" in text
                            or "recombinase" in text
                        ):
                            has_integrase = True
                            break
                    if has_integrase:
                        break
        except Exception as exc:
            logger.debug("Could not scan phold GBK for mobility genes %s: %s", phold_gbk, exc)

    return {
        "no_amr":       not has_amr,
        "no_virulence": not has_vf,
        "no_integrase": not has_integrase,
        "_amr_hits":    amr_hits,
        "_vf_hits":     vf_hits,
    }


def _parse_netflax_from_gbk(gbk_path: Optional[Path]) -> List[Dict[str, str]]:
    """Keep the phold note-based NetFlax placeholder until a dedicated tool replaces it."""
    if not gbk_path or not gbk_path.exists():
        return []

    netflax = []
    try:
        from Bio import SeqIO

        with open(gbk_path, encoding="utf-8") as fh:
            for rec in SeqIO.parse(fh, "genbank"):
                for feat in rec.features:
                    if feat.type != "CDS":
                        continue
                    note = " ".join(feat.qualifiers.get("note", [])).lower()
                    if "netflax" in note or "anti-toxin" in note or "anti-ta" in note:
                        locus = feat.qualifiers.get("locus_tag", ["?"])[0]
                        netflax.append({"protein": locus, "note": note[:80]})
    except Exception as exc:
        logger.debug("NetFlax parsing failed for %s: %s", gbk_path, exc)

    return netflax


def _parse_phold_acr(phold_dir: Optional[Path]) -> List[Dict[str, str]]:
    """Parse phold's foldseek-based anti-CRISPR predictions (sub_db_tophits/acr_cds_predictions.tsv)."""
    if not phold_dir:
        return []
    acr_tsv = phold_dir / "sub_db_tophits" / "acr_cds_predictions.tsv"
    rows = _read_tsv(acr_tsv)
    parsed: List[Dict[str, str]] = []
    for row in rows:
        cds = (row.get("cds_id") or "").strip()
        family = (row.get("Family") or "").strip()
        if not cds and not family:
            continue
        anti_type = (row.get("Anti_type") or "").strip()
        subtype = f"targets CRISPR-{anti_type}" if anti_type else (row.get("anti_CRISPR_id") or "").strip()
        parsed.append({
            "protein": cds,
            "gene_name": family,
            "type": "anti_crispr",
            "subtype": subtype,
            "activity": "Antidefense",
            "score": (row.get("bitscore") or "").strip(),
            "evalue": (row.get("evalue") or "").strip(),
            "source": "phold",
        })
    return parsed


def _parse_phold_defensefinder(phold_dir: Optional[Path]) -> List[Dict[str, str]]:
    """Parse phold's foldseek-based defensefinder predictions (sub_db_tophits/defensefinder_cds_predictions.tsv)."""
    if not phold_dir:
        return []
    df_tsv = phold_dir / "sub_db_tophits" / "defensefinder_cds_predictions.tsv"
    rows = _read_tsv(df_tsv)
    parsed: List[Dict[str, str]] = []
    for row in rows:
        cds = (row.get("cds_id") or "").strip()
        gene_name = (row.get("gene_name") or "").strip()
        if not cds and not gene_name:
            continue
        # `type` in phold's TSV is often "na"; fall back to System when so.
        raw_type = (row.get("type") or "").strip()
        system = (row.get("System") or "").strip()
        type_value = system if raw_type.lower() in ("", "na", "n/a") else raw_type
        parsed.append({
            "protein": cds,
            "gene_name": gene_name,
            "type": type_value,
            "subtype": (row.get("subtype") or "").strip(),
            "activity": "Antidefense",
            "score": (row.get("bitscore") or "").strip(),
            "evalue": (row.get("evalue") or "").strip(),
            "source": "phold",
        })
    return parsed


def _parse_defence(
    gbk_path: Optional[Path],
    defensefinder_systems: Optional[Path],
    defensefinder_genes: Optional[Path],
    phold_dir: Optional[Path] = None,
) -> Dict[str, List]:
    """Parse DefenseFinder systems/genes plus phold's foldseek-based sub-DBs."""
    systems_rows = _read_tsv(defensefinder_systems)
    genes_rows = _read_tsv(defensefinder_genes)

    acr = []
    defence_systems = []
    defence_genes = []

    for row in genes_rows:
        gene = {
            "protein": row.get("hit_id") or "",
            "gene_name": row.get("gene_name") or "",
            "type": row.get("type") or "",
            "subtype": row.get("subtype") or "",
            "activity": row.get("activity") or "",
            "score": row.get("hit_score") or "",
            "evalue": row.get("hit_i_eval") or "",
            "source": "DefenseFinder",
        }
        if (gene["type"] or "").lower() == "anti_crispr":
            acr.append(gene)
        else:
            defence_genes.append(gene)

    for row in systems_rows:
        system = {
            "system_id": row.get("sys_id") or "",
            "type": row.get("type") or "",
            "subtype": row.get("subtype") or "",
            "activity": row.get("activity") or "",
            "proteins": row.get("protein_in_syst") or "",
            "genes_count": row.get("genes_count") or "",
            "source": "DefenseFinder",
        }
        if (system["type"] or "").lower() != "anti_crispr":
            defence_systems.append(system)

    # Merge phold's foldseek-based ACR + DefenseFinder sub-DB hits.
    acr.extend(_parse_phold_acr(phold_dir))
    defence_genes.extend(_parse_phold_defensefinder(phold_dir))

    return {
        "acr": acr,
        "defence_finder": defence_systems,
        "defence_finder_genes": defence_genes,
        "netflax": _parse_netflax_from_gbk(gbk_path),
    }


def _parse_rbp(rbp_csv: Optional[Path]) -> List[Dict[str, Any]]:
    """Parse PhageRBPdetect rbp_predictions.csv — return top RBP hits."""
    rows = _read_csv(rbp_csv)
    results = []
    for row in rows:
        score_str = row.get("rbp_score") or row.get("score") or row.get("Score") or "0"
        try:
            score = float(score_str)
        except ValueError:
            score = 0.0
        if score >= 0.5:
            results.append({
                "protein": row.get("protein_id") or row.get("id") or "",
                "score":   round(score, 4),
                "length":  row.get("length") or row.get("Length") or "",
            })
    return sorted(results, key=lambda x: -x["score"])


_DEPOSCOPE_DOMAIN_LABELS = {
    1: "beta-helix",
    2: "beta-propeller",
    3: "triple-helix",
}


def _parse_deposcope_token_labels(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        values = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return []
    labels: List[int] = []
    for value in values:
        try:
            label = int(float(value))
        except (TypeError, ValueError):
            continue
        labels.append(label)
    return labels


def _infer_deposcope_domain(raw_labels: Optional[str]) -> Dict[str, str]:
    labels = _parse_deposcope_token_labels(raw_labels)
    non_zero = [label for label in labels if label > 0]
    if not non_zero:
        return {"domain_type": "", "domain_start": "", "domain_end": ""}

    dominant_label = Counter(non_zero).most_common(1)[0][0]
    positions = [idx + 1 for idx, label in enumerate(labels) if label == dominant_label]
    if not positions:
        return {"domain_type": "", "domain_start": "", "domain_end": ""}

    return {
        "domain_type": _DEPOSCOPE_DOMAIN_LABELS.get(dominant_label, f"Domain {dominant_label}"),
        "domain_start": str(positions[0]),
        "domain_end": str(positions[-1]),
    }


def _parse_deposcope(depo_results: Optional[Path], depo_tokens: Optional[Path]) -> List[Dict[str, Any]]:
    """Parse DepoScope result CSV plus token labels into report rows."""
    rows = _read_table(depo_results)
    token_rows = _read_tsv(depo_tokens)
    token_domains = {
        (row.get("protein_id") or row.get("id") or "").strip(): _infer_deposcope_domain(row.get("token_labels"))
        for row in token_rows
        if (row.get("protein_id") or row.get("id") or "").strip()
    }
    results = []
    for row in rows:
        score_str = row.get("dep_score") or row.get("scores_DepoScope") or row.get("score") or "0"
        try:
            score = float(score_str)
        except ValueError:
            score = 0.0
        protein_id = (row.get("protein_id") or row.get("gene_ID") or row.get("id") or "").strip()
        raw_is_depo = (row.get("is_depolymerase") or row.get("depolymerase") or "").strip().lower()
        is_depo = raw_is_depo in ("true", "yes", "1") or (not raw_is_depo and score >= 0.5)
        domain_type = row.get("domain_type") or row.get("fold") or ""
        domain_start = row.get("domain_start") or ""
        domain_end = row.get("domain_end") or ""
        if protein_id and (not domain_type or not domain_start or not domain_end):
            inferred = token_domains.get(protein_id) or {}
            domain_type = domain_type or inferred.get("domain_type", "")
            domain_start = domain_start or inferred.get("domain_start", "")
            domain_end = domain_end or inferred.get("domain_end", "")
        results.append({
            "protein":     protein_id,
            "score":       round(score, 4),
            "is_depo":     is_depo,
            "domain_type": domain_type,
            "domain_start": domain_start,
            "domain_end":   domain_end,
        })
    return sorted(results, key=lambda x: -x["score"])


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_report_data(stem: str, per: Dict[str, Any], ncbi_ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the full data dict for one phage report card.

    *stem*    : phage name (folder stem)
    *per*     : ctx['results'][stem]
    *ncbi_ctx*: top-level ctx keys (ncbi_multifasta, ncbi_features_tbl, etc.)
    """
    best_gbk: Optional[Path] = (
        per.get("phynteny_gbk")
        or per.get("phold_gbk")
        or per.get("pharokka_gbk")
    )
    phold_gbk: Optional[Path] = per.get("phold_gbk")
    sample_dir: Optional[Path] = None
    for key in ("vcontact3_dir", "pharokka_dir", "phold_dir", "phynteny_dir", "rbpdetect_dir", "deposcope_dir"):
        path = per.get(key)
        if path:
            sample_dir = Path(path).parent
            break
    if sample_dir is None:
        for key in ("phynteny_gbk", "phold_gbk", "pharokka_gbk"):
            path = per.get(key)
            if path:
                sample_dir = Path(path).parent.parent
                break

    genome_stats    = _parse_genome_stats(best_gbk)
    genome_map      = _parse_genome_map_data(best_gbk)
    phrog_cats      = _parse_phrog_categories(best_gbk)
    lifestyle       = _parse_lifestyle(per.get("phastyle_predictions"))
    hosts           = _parse_host(per.get("cherry_host_prediction"))
    closest_phages  = _parse_closest_phages(
        per.get("vcontact3_overview"),
        per.get("vcontact3_dir"),
    )
    taxonomy, taxonomy_source = _resolve_taxonomy_with_ncbi_fallback(
        _parse_taxonomy(per.get("vcontact3_overview")),
        closest_phages,
    )
    therapy_safety  = _parse_therapy_safety(
        per.get("phold_card_tsv"),
        per.get("phold_vfdb_tsv"),
        phold_gbk,
        per.get("pharokka_dir"),
    )
    defence         = _parse_defence(
        phold_gbk or best_gbk,
        per.get("defensefinder_systems"),
        per.get("defensefinder_genes"),
        per.get("phold_dir"),
    )
    rbp_hits        = _parse_rbp(per.get("rbp_predictions"))
    depo_hits       = _parse_deposcope(per.get("deposcope_results"), per.get("deposcope_tokens"))

    # Therapy suitability: lytic + all safety bools pass. Underscore-prefixed
    # keys carry detail lists for the template and are excluded from the gate.
    is_lytic      = lifestyle["lifestyle"].lower() in ("lytic",)
    safety_bools  = [v for k, v in therapy_safety.items() if not k.startswith("_")]
    therapy_ok    = is_lytic and all(safety_bools)

    # Genome map as embedded base64 PNG
    genome_map_b64 = _png_to_b64(per.get("genome_map_png"))

    def _fi(path_key: str) -> Optional[Dict]:
        return _file_info(per.get(path_key))

    def _fi_direct(path: Optional[Path]) -> Optional[Dict]:
        return _file_info(path)

    # vConTACT3 derived paths
    vc3_dir: Optional[Path] = per.get("vcontact3_dir")
    vc3_exports = vc3_dir / "exports" if vc3_dir else None
    vc3_networks = vc3_exports / "networks" if vc3_exports else None

    return {
        "name":           stem,
        "genome":         genome_stats,
        "genome_map":     genome_map,
        "phrog_cats":     phrog_cats,
        "lifestyle":      lifestyle,
        "hosts":          hosts,
        "taxonomy":        taxonomy,
        "taxonomy_source": taxonomy_source,
        "closest_phages":  closest_phages,
        "therapy": {
            "suitable":      therapy_ok,
            "strictly_lytic": is_lytic,
            **therapy_safety,
        },
        "defence":        defence,
        "rbp":            rbp_hits,
        "deposcope":      depo_hits,
        "genome_map_b64": genome_map_b64,
        # Downloads — grouped by tool
        "downloads": {
            # Annotation GBKs
            "pharokka_gbk":       _fi("pharokka_gbk"),
            "phold_gbk":          _fi("phold_gbk"),
            "phynteny_gbk":       _fi("phynteny_gbk"),
            # Sequence files
            "pharokka_faa":       _fi("pharokka_faa"),
            "pharokka_ffn":       _fi("pharokka_ffn"),
            "pharokka_gff":       _fi("pharokka_gff"),
            "pharokka_tbl":       _fi("pharokka_tbl"),
            # Pharokka TSV annotations
            "pharokka_cds_tsv":   _fi_direct(per.get("pharokka_dir") and per["pharokka_dir"] / "pharokka_cds_final_merged_output.tsv"),
            # Genome map
            "genome_map_png":     _fi("genome_map_png"),
            # PhaStyle
            "phastyle_tsv":       _fi("phastyle_predictions"),
            # CHERRY
            "cherry_csv":         _fi("cherry_host_prediction"),
            # DefenseFinder
            "defensefinder_systems_tsv": _fi("defensefinder_systems"),
            "defensefinder_genes_tsv": _fi("defensefinder_genes"),
            "defensefinder_hmmer_tsv": _fi("defensefinder_hmmer"),
            # vConTACT3
            "vcontact3_assignments": _fi_direct(vc3_exports / "final_assignments.csv" if vc3_exports else None),
            "vcontact3_metrics":     _fi_direct(vc3_exports / "performance_metrics.csv" if vc3_exports else None),
            "vcontact3_cyjs":        _fi_direct(vc3_networks / "part1.cyjs" if vc3_networks else None),
            "vcontact3_graphml":     _fi_direct(vc3_networks / "part1.graphml" if vc3_networks else None),
            # RBPdetect
            "rbp_predictions_csv":   _fi("rbp_predictions"),
            "rbp_candidates_faa":    _fi("rbp_candidates_faa"),
            # DepoScope
            "deposcope_results_csv": _fi("deposcope_results"),
            "deposcope_tokens_tsv":  _fi("deposcope_tokens"),
            # NCBI submission
            "ncbi_fasta":    _fi_direct(ncbi_ctx.get("ncbi_multifasta")),
            "ncbi_tbl":      _fi_direct(ncbi_ctx.get("ncbi_features_tbl")),
        },
    }
