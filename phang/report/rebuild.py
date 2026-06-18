"""
Rebuild report_card.html files from an existing pipeline output directory.

Walks `<output>/<stem>/` for each phage, reconstructs the per-phage path dict
by probing for known files, then re-renders the HTML report. No pipeline steps
are re-executed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from phang.report.builder import build_report_data
from phang.report.template import render_report
from phang.steps.s11_report import _attach_download_hrefs

logger = logging.getLogger(__name__)


def _exists(p: Path) -> Optional[Path]:
    return p if p.exists() else None


def _find_pharokka_faa(pharokka_dir: Path) -> Optional[Path]:
    for name in ("phanotate.faa", "pharokka.faa"):
        p = pharokka_dir / name
        if p.exists():
            return p
    return None


def _find_pharokka_ffn(pharokka_dir: Path) -> Optional[Path]:
    for name in ("phanotate.ffn", "pharokka.ffn"):
        p = pharokka_dir / name
        if p.exists():
            return p
    return None


def reconstruct_per(stem_dir: Path) -> Dict[str, Any]:
    """Reconstruct the per-phage path dict from an existing output tree."""
    per: Dict[str, Any] = {}

    pharokka_dir = stem_dir / "pharokka"
    if pharokka_dir.exists():
        per["pharokka_dir"] = pharokka_dir
        per["pharokka_gbk"] = _exists(pharokka_dir / "pharokka.gbk")
        per["pharokka_tbl"] = _exists(pharokka_dir / "pharokka.tbl")
        per["pharokka_gff"] = _exists(pharokka_dir / "pharokka.gff")
        per["pharokka_faa"] = _find_pharokka_faa(pharokka_dir)
        per["pharokka_ffn"] = _find_pharokka_ffn(pharokka_dir)

    phold_dir = stem_dir / "phold"
    if phold_dir.exists():
        per["phold_dir"] = phold_dir
        per["phold_gbk"] = _exists(phold_dir / "phold.gbk")
        # phold writes one TSV per sub-database; there is no unified file.
        per["phold_card_tsv"] = _exists(phold_dir / "sub_db_tophits" / "card_cds_predictions.tsv")
        per["phold_vfdb_tsv"] = _exists(phold_dir / "sub_db_tophits" / "vfdb_cds_predictions.tsv")

    phynteny_dir = stem_dir / "phynteny"
    if phynteny_dir.exists():
        per["phynteny_dir"] = phynteny_dir
        gbk = phynteny_dir / "phynteny.gbk"
        if not gbk.exists():
            matches = sorted(phynteny_dir.glob("*.gbk"))
            gbk = matches[0] if matches else gbk
        per["phynteny_gbk"] = _exists(gbk)

    phastyle_dir = stem_dir / "phastyle"
    if phastyle_dir.exists():
        per["phastyle_dir"] = phastyle_dir
        per["phastyle_predictions"] = _exists(phastyle_dir / "predictions.tsv")

    cherry_dir = stem_dir / "cherry"
    if cherry_dir.exists():
        per["cherry_dir"] = cherry_dir
        per["cherry_host_prediction"] = _exists(cherry_dir / "host_prediction.csv")

    vcontact3_dir = stem_dir / "vcontact3"
    if vcontact3_dir.exists():
        per["vcontact3_dir"] = vcontact3_dir
        per["vcontact3_overview"] = _exists(vcontact3_dir / "exports" / "final_assignments.csv")

    defensefinder_dir = stem_dir / "defensefinder"
    if defensefinder_dir.exists():
        per["defensefinder_dir"] = defensefinder_dir
        per["defensefinder_systems"] = _exists(defensefinder_dir / "defense_finder_systems.tsv")
        per["defensefinder_genes"] = _exists(defensefinder_dir / "defense_finder_genes.tsv")
        per["defensefinder_hmmer"] = _exists(defensefinder_dir / "defense_finder_hmmer.tsv")

    rbpdetect_dir = stem_dir / "rbpdetect"
    if rbpdetect_dir.exists():
        per["rbpdetect_dir"] = rbpdetect_dir
        per["rbp_predictions"] = _exists(rbpdetect_dir / "rbp_predictions.csv")
        per["rbp_candidates_faa"] = _exists(rbpdetect_dir / "rbp_candidates.faa")
        per["rbp_candidates_ffn"] = _exists(rbpdetect_dir / "rbp_candidates.ffn")

    deposcope_dir = stem_dir / "deposcope"
    if deposcope_dir.exists():
        per["deposcope_dir"] = deposcope_dir
        per["deposcope_results"] = _exists(deposcope_dir / "deposcope_results.csv")
        per["deposcope_tokens"] = _exists(deposcope_dir / "deposcope_tokens.tsv")

    per["genome_map_png"] = _exists(stem_dir / "genome_map.png")

    return per


def _discover_phage_dirs(output_root: Path) -> List[Path]:
    """Find per-phage subdirectories under an output root."""
    if not output_root.exists() or not output_root.is_dir():
        return []
    phage_dirs: List[Path] = []
    for child in sorted(output_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith((".", "_")):
            continue
        # A phage dir is one that contains a recognised tool subdir.
        if any((child / sub).is_dir() for sub in ("pharokka", "phold", "defensefinder")):
            phage_dirs.append(child)
    return phage_dirs


def rebuild_reports(output_root: Path) -> int:
    """
    Rebuild report_card.html for every phage under `output_root`.

    Walks the directory tree to find phage subdirectories (identified by the
    presence of a `pharokka/`, `phold/`, or `defensefinder/` subdir). Handles
    nested batch layouts like `<batch>/<group>/<phage>/` by recursing one
    level if no phages found at the top.

    Returns the number of reports successfully rebuilt.
    """
    output_root = output_root.expanduser().resolve()
    phage_dirs = _discover_phage_dirs(output_root)

    if not phage_dirs:
        # Try one level deeper for batch outputs that group phages by sample.
        for child in sorted(output_root.iterdir()):
            if child.is_dir() and not child.name.startswith((".", "_")):
                phage_dirs.extend(_discover_phage_dirs(child))

    if not phage_dirs:
        logger.error("No phage directories found under %s", output_root)
        return 0

    logger.info("Rebuilding %d report card(s) under %s", len(phage_dirs), output_root)

    ok = 0
    for stem_dir in phage_dirs:
        stem = stem_dir.name
        out_html = stem_dir / "report_card.html"
        # NCBI artifacts live alongside the per-phage dirs at the batch level.
        batch_root = stem_dir.parent
        ncbi_ctx = {
            "ncbi_multifasta": _exists(batch_root / "ncbi" / "bankit_multi.fasta"),
            "ncbi_features_tbl": _exists(batch_root / "ncbi" / "bankit_features.tbl"),
        }
        try:
            per = reconstruct_per(stem_dir)
            data = build_report_data(stem, per, ncbi_ctx)
            _attach_download_hrefs(data, out_html.parent)
            html = render_report(data)
            out_html.write_text(html, encoding="utf-8")
            size_kb = out_html.stat().st_size // 1024
            logger.info("  ✓ %s — %d KB", stem, size_kb)
            ok += 1
        except Exception as exc:
            logger.error("  ✗ %s — %s", stem, exc)

    logger.info("Rebuild complete: %d/%d succeeded", ok, len(phage_dirs))
    return ok
