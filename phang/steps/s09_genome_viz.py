"""
Step 9: Circular genome visualisation using pyCirclize.

Reads the Phynteny GenBank (most comprehensive annotation) and produces:
    <output>/<phage>/genome_map.png  — circular genome map

Tracks rendered (outer → inner):
  1. Forward-strand CDS arrows, coloured by PHROG category
  2. Reverse-strand CDS arrows, coloured by PHROG category
  3. GC content ring
  4. GC skew ring (+green / −purple)

Consumed by Report Card (Genome tab) as an embedded base64 PNG.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# PHROG category → hex colour (matches the prototype)
PHROG_COLORS: Dict[str, str] = {
    "unknown function":                               "#9CA3AF",
    "other":                                          "#22D3EE",
    "transcription regulation":                       "#FACC15",
    "dna, rna and nucleotide metabolism":             "#E879F9",
    "lysis":                                          "#2563EB",
    "moron, auxiliary metabolic gene and host takeover": "#7C3AED",
    "integration and excision":                       "#F0ABFC",
    "head and packaging":                             "#EC4899",
    "connector":                                      "#57534E",
    "tail":                                           "#4ADE80",
    "other function":                                 "#22D3EE",
}
_DEFAULT_COLOR = "#9CA3AF"


def _phrog_color(category: Optional[str]) -> str:
    if not category:
        return _DEFAULT_COLOR
    return PHROG_COLORS.get(category.lower().strip(), _DEFAULT_COLOR)


def _parse_gbk_features(
    gbk_path: Path,
) -> Tuple[int, float, List[Dict], List[float], List[float]]:
    """
    Parse a GenBank file and return:
        genome_length, gc_percent, features, gc_content_track, gc_skew_track

    features: list of dicts with keys start, end, strand, color
    gc_content_track / gc_skew_track: lists of float per window
    """
    from Bio import SeqIO
    from Bio.SeqUtils import gc_fraction

    with open(gbk_path, encoding="utf-8") as fh:
        rec = next(SeqIO.parse(fh, "genbank"), None)

    if rec is None:
        raise ValueError(f"No records found in {gbk_path}")

    seq = str(rec.seq).upper()
    genome_length = len(seq)
    gc_percent = round(gc_fraction(seq) * 100, 2)

    features: List[Dict] = []
    for feat in rec.features:
        if feat.type not in ("CDS",):
            continue
        start = int(feat.location.start)
        end = int(feat.location.end)
        strand = feat.location.strand if feat.location.strand is not None else 1

        category = (
            feat.qualifiers.get("phrog_category", [None])[0]
            or feat.qualifiers.get("function", [None])[0]
        )
        color = _phrog_color(category)
        features.append({"start": start, "end": end, "strand": strand, "color": color})

    # GC content and GC skew in sliding windows
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

    return genome_length, gc_percent, features, gc_content_track, gc_skew_track


def _draw_genome_map(
    genome_length: int,
    features: List[Dict],
    gc_content: List[float],
    gc_skew: List[float],
    out_png: Path,
) -> None:
    """Render the circular genome map using pyCirclize and save to *out_png*."""
    # Force the headless Agg backend BEFORE importing pyplot/pyCirclize. The
    # pipeline can run on a worker thread (GUI), where matplotlib's default Tk
    # backend tries to spin up a GUI off the main thread and wedges the Phang
    # window blank (HANDOFF BUG #2). Agg writes straight to PNG with no GUI, so
    # it is thread-safe. (Belt-and-suspenders to MPLBACKEND=Agg set in the GUI.)
    import matplotlib
    matplotlib.use("Agg")
    from pycirclize import Circos
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    fig = plt.figure(figsize=(10, 10), facecolor="#020617")
    ax = fig.add_subplot(111, facecolor="#020617")

    # We draw everything manually on a polar-like axes using matplotlib
    # since pyCirclize's API varies by version. Direct matplotlib gives
    # us exact control over the dark-theme design from the prototype.
    ax.set_aspect("equal")
    ax.axis("off")

    cx, cy = 0.0, 0.0

    def bp_to_angle(bp: int) -> float:
        """Convert base-pair position to angle in radians (start at top, clockwise)."""
        return (bp / genome_length) * 2 * math.pi - math.pi / 2

    # --- Track radii ---
    r_fwd_outer, r_fwd_inner = 0.80, 0.72
    r_rev_outer, r_rev_inner = 0.70, 0.62
    r_gc_center, r_gc_amp    = 0.52, 0.07
    r_skew_center, r_skew_amp = 0.40, 0.06

    # --- Draw guide circles ---
    for r, lw, color in [
        (r_fwd_outer, 0.6, "#334155"),
        (r_rev_inner, 0.4, "#1e293b"),
        (r_gc_center, 0.4, "#1e293b"),
        (r_skew_center, 0.4, "#1e293b"),
    ]:
        circle = plt.Circle((cx, cy), r, fill=False, edgecolor=color, linewidth=lw)
        ax.add_patch(circle)

    # --- Draw CDS features ---
    n_points = 60  # arc resolution per feature
    for feat in features:
        s, e, strand = feat["start"], feat["end"], feat["strand"]
        color = feat["color"]
        r_out = r_fwd_outer if strand == 1 else r_rev_outer
        r_in  = r_fwd_inner if strand == 1 else r_rev_inner

        a_start = bp_to_angle(s)
        a_end   = bp_to_angle(e)
        if a_end < a_start:
            a_end += 2 * math.pi

        angles = [a_start + (a_end - a_start) * i / n_points for i in range(n_points + 1)]
        xs_out = [cx + r_out * math.cos(a) for a in angles]
        ys_out = [cy + r_out * math.sin(a) for a in angles]
        xs_in  = [cx + r_in  * math.cos(a) for a in reversed(angles)]
        ys_in  = [cy + r_in  * math.sin(a) for a in reversed(angles)]

        xs = xs_out + xs_in
        ys = ys_out + ys_in
        poly = plt.Polygon(list(zip(xs, ys)), closed=True,
                           facecolor=color, edgecolor="#020617",
                           linewidth=0.2, alpha=0.9)
        ax.add_patch(poly)

    # --- GC content ring ---
    n_gc = len(gc_content)
    if n_gc > 1:
        mean_gc = sum(gc_content) / n_gc
        for i in range(n_gc):
            a1 = -math.pi / 2 + (i / n_gc) * 2 * math.pi
            a2 = -math.pi / 2 + ((i + 1) / n_gc) * 2 * math.pi
            val = gc_content[i] - mean_gc
            r = r_gc_center + val * r_gc_amp * 5
            r = max(r_gc_center - r_gc_amp, min(r_gc_center + r_gc_amp, r))
            color = "#334155" if val >= 0 else "#1e293b"
            angles = [a1 + (a2 - a1) * j / 8 for j in range(9)]
            xs_out = [cx + (r_gc_center + abs(val) * r_gc_amp * 4) * math.cos(a) for a in angles]
            ys_out = [cy + (r_gc_center + abs(val) * r_gc_amp * 4) * math.sin(a) for a in angles]
            xs_in  = [cx + r_gc_center * math.cos(a) for a in reversed(angles)]
            ys_in  = [cy + r_gc_center * math.sin(a) for a in reversed(angles)]
            poly = plt.Polygon(list(zip(xs_out + xs_in, ys_out + ys_in)),
                               closed=True, facecolor=color, edgecolor="none", alpha=0.7)
            ax.add_patch(poly)

    # --- GC skew ring ---
    n_skew = len(gc_skew)
    if n_skew > 1:
        for i in range(n_skew):
            a1 = -math.pi / 2 + (i / n_skew) * 2 * math.pi
            a2 = -math.pi / 2 + ((i + 1) / n_skew) * 2 * math.pi
            val = gc_skew[i]
            color = "#22c55e" if val >= 0 else "#a855f7"
            r_edge = r_skew_center + val * r_skew_amp * 3
            r_edge = max(r_skew_center - r_skew_amp, min(r_skew_center + r_skew_amp, r_edge))
            angles = [a1 + (a2 - a1) * j / 8 for j in range(9)]
            xs_out = [cx + r_edge * math.cos(a) for a in angles]
            ys_out = [cy + r_edge * math.sin(a) for a in angles]
            xs_in  = [cx + r_skew_center * math.cos(a) for a in reversed(angles)]
            ys_in  = [cy + r_skew_center * math.sin(a) for a in reversed(angles)]
            poly = plt.Polygon(list(zip(xs_out + xs_in, ys_out + ys_in)),
                               closed=True, facecolor=color, edgecolor="none", alpha=0.5)
            ax.add_patch(poly)

    # --- Tick marks & kb labels ---
    tick_step_kb = max(5, round(genome_length / 8 / 5000) * 5)
    tick_step = tick_step_kb * 1000
    for bp in range(0, genome_length, tick_step):
        a = bp_to_angle(bp)
        r1, r2 = r_fwd_outer + 0.01, r_fwd_outer + 0.04
        ax.plot([cx + r1 * math.cos(a), cx + r2 * math.cos(a)],
                [cy + r1 * math.sin(a), cy + r2 * math.sin(a)],
                color="#64748b", linewidth=0.8)
        r_lbl = r_fwd_outer + 0.08
        label = "0 kb" if bp == 0 else f"{bp // 1000} kb"
        ax.text(cx + r_lbl * math.cos(a), cy + r_lbl * math.sin(a),
                label, ha="center", va="center",
                fontsize=5.5, color="#64748b", fontfamily="monospace")

    # --- Centre text ---
    kb = f"{genome_length / 1000:.1f} kb"
    ax.text(cx, cy + 0.04, kb, ha="center", va="center",
            fontsize=11, fontweight="bold", color="#94a3b8", fontfamily="monospace")
    ax.text(cx, cy - 0.04, f"GC {genome_length}", ha="center", va="center",
            fontsize=6, color="#475569", fontfamily="monospace")

    ax.set_xlim(-1.15, 1.15)
    ax.set_ylim(-1.15, 1.15)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_png), dpi=180, bbox_inches="tight",
                facecolor="#020617", edgecolor="none")
    plt.close(fig)


def run_genome_viz(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 9 entry point.

    Reads from ctx : results[stem].phynteny_gbk (falls back to phold_gbk / pharokka_gbk)
    Writes to ctx['results'][stem] : genome_map_png
    """
    output_path: Path = ctx["output_path"]
    force: bool = ctx["force"]
    ok = 0

    for stem, per in ctx["results"].items():
        gbk: Optional[Path] = (
            per.get("phynteny_gbk")
            or per.get("phold_gbk")
            or per.get("pharokka_gbk")
        )
        if not gbk or not gbk.exists():
            logger.warning("  [SKIP] %s — no GBK found for genome viz.", stem)
            continue

        out_png = output_path / stem / "genome_map.png"

        if not force and out_png.exists():
            logger.info("  [SKIP] %s — genome_map.png already present.", stem)
            per["genome_map_png"] = out_png
            ok += 1
            continue

        logger.info("  Genome viz ← %s", gbk.name)
        try:
            genome_length, gc_percent, features, gc_content, gc_skew = _parse_gbk_features(gbk)
            _draw_genome_map(genome_length, features, gc_content, gc_skew, out_png)
            per["genome_map_png"] = out_png
            ok += 1
            logger.info("  Genome map saved: %s (%d features)", out_png.name, len(features))
        except Exception as exc:
            logger.error("  [FAIL] Genome viz failed for %s: %s", stem, exc)

    logger.info("Genome viz: %d/%d succeeded", ok, len(ctx["results"]))
    return ctx
