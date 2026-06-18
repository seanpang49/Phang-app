"""
Step 11: Report card generation.

Produces a self-contained HTML report card for each phage:
    <output>/<phage>/report_card.html

The HTML file:
- Has all CSS inline
- Embeds all data as JavaScript objects
- Embeds genome map as base64 PNG
- Has no external dependencies (CDN-free)
- Opens by double-clicking in any browser
"""

from __future__ import annotations

import logging
import os
from urllib.parse import quote
from pathlib import Path
from typing import Any, Dict

from phang.report.builder import build_report_data
from phang.report.template import render_report

logger = logging.getLogger(__name__)


def _attach_download_hrefs(data: Dict[str, Any], report_dir: Path) -> None:
    downloads = data.get("downloads") or {}
    for item in downloads.values():
        if not item or item.get("b64"):
            continue
        path_str = item.get("path")
        if not path_str:
            continue
        path = Path(path_str)
        if not path.exists():
            continue
        rel = Path(os.path.relpath(path, report_dir))
        item["href"] = quote(rel.as_posix(), safe="/")


def run_report(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 11 entry point.

    Reads from ctx : all per-phage results, ncbi_multifasta, ncbi_features_tbl
    Writes to ctx['results'][stem] : report_card_html
    """
    output_path: Path = ctx["output_path"]
    force: bool = ctx["force"]

    ncbi_ctx = {
        "ncbi_multifasta":   ctx.get("ncbi_multifasta"),
        "ncbi_features_tbl": ctx.get("ncbi_features_tbl"),
    }

    ok = 0
    for stem, per in ctx["results"].items():
        out_html = output_path / stem / "report_card.html"

        if not force and out_html.exists():
            logger.info("  [SKIP] %s — report_card.html already present.", stem)
            per["report_card_html"] = out_html
            ok += 1
            continue

        logger.info("  Report card ← %s", stem)
        try:
            data = build_report_data(stem, per, ncbi_ctx)
            _attach_download_hrefs(data, out_html.parent)
            html = render_report(data)
            out_html.parent.mkdir(parents=True, exist_ok=True)
            out_html.write_text(html, encoding="utf-8")
            per["report_card_html"] = out_html
            ok += 1
            size_kb = out_html.stat().st_size // 1024
            logger.info("  Report card saved: %s (%d KB)", out_html.name, size_kb)
        except Exception as exc:
            logger.error("  [FAIL] Report card failed for %s: %s", stem, exc)

    logger.info("Report card: %d/%d succeeded", ok, len(ctx["results"]))
    return ctx
