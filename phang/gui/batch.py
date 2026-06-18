"""
Build a combined batch dashboard HTML from multiple phage run outputs.

The dashboard shows all phages as clickable cards. Clicking a card
opens that phage's individual report_card.html in a new browser tab.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def _normalize_host_value(value: Optional[str]) -> str:
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


def _parse_lifestyle_row(row: dict) -> tuple[str, str, Optional[bool]]:
    lifestyle = (
        row.get("predicted_label")
        or row.get("prediction")
        or row.get("lifestyle")
        or row.get("Prediction")
        or "—"
    )
    lifestyle = lifestyle.title() if lifestyle and lifestyle != "—" else lifestyle
    lifestyle_lower = lifestyle.strip().lower() if lifestyle and lifestyle != "—" else ""
    confidence_str = (
        row.get("score")
        or row.get("confidence")
        or row.get("Score")
        or row.get("Confidence")
        or row.get(f"score_{lifestyle_lower}")
        or ""
    )
    confidence = "—"
    if confidence_str:
        try:
            confidence = f"{float(confidence_str) * 100:.0f}%"
        except ValueError:
            confidence = "—"
    therapy = lifestyle_lower == "lytic"
    return lifestyle, confidence, therapy if lifestyle != "—" else None


def _read_assignments(report_dir: Path) -> dict:
    """Extract key stats from a completed phage run directory."""
    stats: dict = {
        "name": report_dir.name,
        "genome_length": "—",
        "gc": "—",
        "orfs": "—",
        "lifestyle": "—",
        "lifestyle_conf": "—",
        "family": "—",
        "genus": "—",
        "host": "—",
        "therapy": None,
        "report_path": report_dir / "report_card.html",
    }

    # Genome stats from pharokka GBK
    gbk = (report_dir / "phynteny" / "phynteny.gbk") or \
          (report_dir / "phold" / "phold.gbk") or \
          (report_dir / "pharokka" / "pharokka.gbk")
    for candidate in [
        report_dir / "phynteny" / "phynteny.gbk",
        report_dir / "phold" / "phold.gbk",
        report_dir / "pharokka" / "pharokka.gbk",
    ]:
        if candidate.exists():
            try:
                from phang.utils.gbk import get_genome_stats
                g = get_genome_stats(candidate)
                stats["genome_length"] = f"{g['length'] / 1000:.1f} kb"
                stats["gc"] = f"{g['gc_percent']}%"
                stats["orfs"] = str(g["cds_count"])
            except Exception:
                pass
            break

    # Lifestyle from PhaStyle
    phastyle = report_dir / "phastyle" / "predictions.tsv"
    if phastyle.exists():
        try:
            import csv
            with open(phastyle) as fh:
                row = next(csv.DictReader(fh, delimiter="\t"), {})
            lifestyle, confidence, therapy = _parse_lifestyle_row(row)
            stats["lifestyle"] = lifestyle
            stats["lifestyle_conf"] = confidence
            stats["therapy"] = therapy
        except Exception:
            pass

    # Taxonomy from vConTACT3
    vc3 = report_dir / "vcontact3" / "exports" / "final_assignments.csv"
    if vc3.exists():
        try:
            import csv
            with open(vc3) as fh:
                for row in csv.DictReader(fh):
                    if row.get("Reference", "True").lower() in ("false", "0", ""):
                        stats["family"] = _normalize_taxonomy_value(row.get("family_prediction"))
                        stats["genus"] = _normalize_taxonomy_value(row.get("genus_prediction"))
                        break
        except Exception:
            pass

    # Host from PhaBOX2 (CHERRY workflow)
    cherry = report_dir / "cherry" / "host_prediction.csv"
    if cherry.exists():
        try:
            import csv
            with open(cherry) as fh:
                row = next(csv.DictReader(fh), {})
            host = (
                row.get("host")
                or row.get("Host")
                or row.get("predicted_host")
                or row.get("Host_NCBI")
                or row.get("Host_GTDB")
                or ""
            )
            stats["host"] = _normalize_host_value(host) or "—"
        except Exception:
            pass

    return stats


def build_batch_dashboard(output_dir: Path) -> Optional[Path]:
    """
    Scan *output_dir* for completed phage runs and generate a batch
    dashboard HTML at *output_dir/batch_dashboard.html*.

    Returns the path to the dashboard, or None if no runs found.
    """
    phage_dirs = sorted(
        d for d in output_dir.iterdir()
        if d.is_dir() and (d / "report_card.html").exists()
    )

    if not phage_dirs:
        logger.warning("No completed phage runs found in %s", output_dir)
        return None

    phages = [_read_assignments(d) for d in phage_dirs]
    html = _render_dashboard(phages, output_dir)
    out = output_dir / "batch_dashboard.html"
    out.write_text(html, encoding="utf-8")
    logger.info("Batch dashboard saved: %s (%d phages)", out, len(phages))
    return out


def _therapy_badge(therapy: Optional[bool]) -> str:
    if therapy is True:
        return '<span style="background:#052e16;color:#4ade80;border:1px solid #166534;padding:2px 8px;border-radius:999px;font-size:10px;font-weight:700;font-family:monospace">LYTIC ✓</span>'
    if therapy is False:
        return '<span style="background:#450a0a;color:#f87171;border:1px solid #991b1b;padding:2px 8px;border-radius:999px;font-size:10px;font-weight:700;font-family:monospace">NON-LYTIC</span>'
    return '<span style="background:#1e293b;color:#64748b;border:1px solid #334155;padding:2px 8px;border-radius:999px;font-size:10px;font-family:monospace">UNKNOWN</span>'


def _render_dashboard(phages: List[dict], output_dir: Path) -> str:
    cards = ""
    for p in phages:
        report_rel = p["report_path"].relative_to(output_dir) if p["report_path"].exists() else None
        link = str(report_rel).replace("\\", "/") if report_rel else "#"
        cards += f"""
<a href="{link}" target="_blank" style="text-decoration:none">
  <div class="phage-card">
    <div class="card-header">
      <div class="phage-name">{p["name"]}</div>
      {_therapy_badge(p["therapy"])}
    </div>
    <div class="card-grid">
      <div class="stat"><div class="stat-l">Genome</div><div class="stat-v">{p["genome_length"]}</div></div>
      <div class="stat"><div class="stat-l">GC</div><div class="stat-v">{p["gc"]}</div></div>
      <div class="stat"><div class="stat-l">ORFs</div><div class="stat-v">{p["orfs"]}</div></div>
      <div class="stat"><div class="stat-l">Lifestyle</div><div class="stat-v">{p["lifestyle"]} <span style="color:#64748b;font-size:11px">{p["lifestyle_conf"]}</span></div></div>
      <div class="stat"><div class="stat-l">Family</div><div class="stat-v">{p["family"]}</div></div>
      <div class="stat"><div class="stat-l">Genus</div><div class="stat-v">{p["genus"]}</div></div>
      <div class="stat" style="grid-column:span 2"><div class="stat-l">Predicted Host</div><div class="stat-v">{p["host"]}</div></div>
    </div>
    <div class="open-link">Open full report →</div>
  </div>
</a>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Phang — Batch Results ({len(phages)} phages)</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#020617; color:#e2e8f0; font-family:'Segoe UI',system-ui,sans-serif; padding:32px; }}
.header {{ margin-bottom:28px; }}
.header h1 {{ font-size:24px; font-weight:300; color:#f8fafc; }}
.header p {{ font-size:13px; color:#64748b; margin-top:6px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:16px; }}
.phage-card {{
  background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:18px;
  transition:border-color 0.15s, transform 0.1s;
  cursor:pointer;
}}
.phage-card:hover {{ border-color:#6366f1; transform:translateY(-2px); }}
.card-header {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }}
.phage-name {{ font-size:15px; font-weight:600; color:#f8fafc; font-family:monospace; }}
.card-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:12px; }}
.stat {{ background:#020617; border-radius:6px; padding:8px 10px; }}
.stat-l {{ font-size:9px; color:#475569; text-transform:uppercase; letter-spacing:0.1em; font-family:monospace; margin-bottom:2px; }}
.stat-v {{ font-size:13px; color:#cbd5e1; }}
.open-link {{ font-size:11px; color:#6366f1; text-align:right; font-family:monospace; letter-spacing:0.05em; }}
</style>
</head>
<body>
<div class="header">
  <h1>🦠  Phang — Batch Results</h1>
  <p>{len(phages)} phage genome(s) analysed &nbsp;·&nbsp; Click any card to open the full report</p>
</div>
<div class="grid">
{cards}
</div>
</body>
</html>"""
