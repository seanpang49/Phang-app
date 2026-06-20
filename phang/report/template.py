"""
HTML template for the phage report card.

Generates a fully self-contained HTML file:
- All CSS inline
- All data embedded as a JS object
- No CDN dependencies
- Vanilla JS tab switching
- Opens by double-clicking in any browser
"""

from __future__ import annotations

import html
import json
import math
from typing import Any, Dict


_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #020617; color: #e2e8f0; font-family: 'Segoe UI', system-ui, sans-serif; font-size: 14px; }
button { font-family: inherit; }
a { color: #60a5fa; text-decoration: none; }

.header {
  background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
  border-bottom: 1px solid #1e293b;
  padding: 28px 32px 20px;
}
.header-inner { max-width: 1100px; margin: 0 auto; display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.header-label { font-size: 10px; font-weight: 600; color: #6366f1; text-transform: uppercase; letter-spacing: 0.2em; font-family: monospace; margin-bottom: 6px; }
.header-title { font-size: 28px; font-weight: 300; color: #f8fafc; }
.header-sub { margin-top: 8px; font-size: 13px; color: #94a3b8; }
.header-badges { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.tabs { background: #0f172a; border-bottom: 1px solid #1e293b; position: sticky; top: 0; z-index: 10; }
.tabs-inner { max-width: 1100px; margin: 0 auto; display: flex; overflow-x: auto; }
.tab-btn {
  padding: 12px 22px; background: none; border: none;
  border-bottom: 2px solid transparent;
  color: #64748b; cursor: pointer; font-size: 12px;
  font-weight: 600; font-family: monospace; text-transform: uppercase;
  letter-spacing: 0.1em; white-space: nowrap; transition: color 0.15s;
}
.tab-btn:hover { color: #94a3b8; }
.tab-btn.active { border-bottom-color: #6366f1; color: #e2e8f0; }

.content { max-width: 1100px; margin: 0 auto; padding: 24px 32px 60px; }
.tab-pane { display: none; }
.tab-pane.active { display: block; }

.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
.col-span-2 { grid-column: span 2; }
.col-span-4 { grid-column: span 4; }
.col-1-3   { grid-column: 1 / 3; }
.col-3-5   { grid-column: 3 / 5; }

.card { background: #0f172a; border: 1px solid #1e293b; border-radius: 10px; padding: 20px; }
.card + .card { margin-top: 14px; }

.section-title {
  margin: 0 0 14px 0; font-size: 13px; font-weight: 700; color: #e2e8f0;
  text-transform: uppercase; letter-spacing: 0.12em; font-family: monospace;
  display: flex; align-items: center; gap: 8px;
  border-bottom: 1px solid #1e293b; padding-bottom: 8px;
}

.stat-label { font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 0.1em; font-family: monospace; margin-bottom: 6px; }
.stat-value { font-size: 26px; font-weight: 300; color: #f8fafc; }
.stat-sub   { font-size: 11px; color: #475569; margin-top: 2px; font-family: monospace; }

.badge {
  padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 600;
  letter-spacing: 0.03em; font-family: monospace; white-space: nowrap;
  display: inline-block;
}
.badge-pass    { background: #052e16; color: #4ade80; border: 1px solid #166534; }
.badge-fail    { background: #450a0a; color: #f87171; border: 1px solid #991b1b; }
.badge-warn    { background: #451a03; color: #fbbf24; border: 1px solid #92400e; }
.badge-default { background: #1e293b; color: #94a3b8; border: 1px solid #334155; }
.badge-info    { background: #0c1a3d; color: #60a5fa; border: 1px solid #1e3a5f; }
.badge-lytic   { background: #3b0764; color: #c084fc; border: 1px solid #581c87; }

.check-item { display: flex; align-items: center; gap: 10px; padding: 6px 0; font-size: 13px; color: #cbd5e1; }
.check-icon { width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; flex-shrink: 0; }
.check-pass { background: #052e16; border: 1.5px solid #166534; }
.check-fail { background: #450a0a; border: 1.5px solid #991b1b; }

.mini-table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: monospace; }
.mini-table th { text-align: left; padding: 6px 10px; color: #64748b; font-weight: 600; border-bottom: 1px solid #1e293b; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; }
.mini-table td { padding: 6px 10px; color: #cbd5e1; border-bottom: 1px solid #0f172a; }

.dl-btn {
  background: linear-gradient(135deg, #1e40af, #3b82f6); color: #fff; border: none;
  border-radius: 6px; padding: 8px 16px; font-size: 11px; font-weight: 600;
  font-family: monospace; cursor: pointer; letter-spacing: 0.05em;
  display: inline-flex; align-items: center; gap: 6px; text-decoration: none;
}
.dl-btn:hover { opacity: 0.85; }
.dl-btn.purple { background: linear-gradient(135deg, #6b21a8, #8b5cf6); }
.dl-btn.green  { background: linear-gradient(135deg, #14532d, #16a34a); }

.bar-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.bar-label { width: 260px; font-size: 11px; color: #94a3b8; font-family: monospace; text-align: right; flex-shrink: 0; display: flex; align-items: center; justify-content: flex-end; gap: 6px; }
.bar-track { flex: 1; background: #1e293b; border-radius: 4px; height: 20px; overflow: hidden; }
.bar-fill  { height: 100%; border-radius: 4px; opacity: 0.85; min-width: 2px; }
.bar-count { width: 32px; font-size: 13px; font-weight: 600; color: #e2e8f0; font-family: monospace; text-align: right; }
.bar-pct   { width: 44px; font-size: 10px; color: #475569; font-family: monospace; }

.genome-img { max-width: 480px; width: 100%; display: block; border-radius: 8px; }
.genome-svg-wrap { position: relative; max-width: 100%; width: 100%; overflow-x: auto; padding-bottom: 6px; }
.genome-svg { width: 1280px; height: auto; display: block; border-radius: 8px; background: #020617; border: 1px solid #1e293b; }
.genome-toolbar { margin-top: 12px; display: flex; gap: 10px; flex-wrap: wrap; }
.genome-svg .genome-feature { cursor: pointer; transition: opacity 0.15s, stroke-width 0.15s; }
.genome-svg .genome-feature:hover { opacity: 1; stroke-width: 1.4; }
.genome-svg .genome-feature.is-selected { stroke: #f8fafc; stroke-width: 1.6; opacity: 1; }
.genome-svg .gene-annotation-line { stroke: #cbd5e1; stroke-width: 1.2; fill: none; stroke-linecap: round; }
.genome-svg .gene-annotation-bg { fill: rgba(2, 6, 23, 0.92); stroke: #334155; stroke-width: 0.8; rx: 4; ry: 4; }
.genome-svg .gene-annotation-text { fill: #e2e8f0; font-size: 11px; font-family: monospace; dominant-baseline: middle; }
.genome-selection-panel { margin-top: 14px; padding: 14px; border: 1px solid #1e293b; border-radius: 8px; background: #020617; }
.genome-selection-title { font-size: 10px; color: #64748b; text-transform: uppercase; font-family: monospace; letter-spacing: 0.1em; margin-bottom: 10px; }
.genome-selection-empty { color: #64748b; font-size: 12px; font-style: italic; }
.genome-selection-list { display: flex; flex-direction: column; gap: 10px; }
.genome-selection-item { padding: 10px 12px; border: 1px solid #1e293b; border-radius: 8px; background: #0b1220; }
.genome-selection-label { color: #f8fafc; font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.genome-selection-meta { color: #94a3b8; font-size: 11px; font-family: monospace; margin-bottom: 4px; }
.genome-selection-product { color: #cbd5e1; font-size: 12px; line-height: 1.5; }
.genome-hint { margin-top: 10px; font-size: 11px; color: #94a3b8; font-family: monospace; line-height: 1.5; }
.flex-gap   { display: flex; gap: 28px; align-items: flex-start; flex-wrap: wrap; }
.legend-section { flex: 0 0 220px; display: flex; flex-direction: column; gap: 18px; padding-top: 8px; }
.legend-title { font-size: 10px; color: #64748b; text-transform: uppercase; font-family: monospace; letter-spacing: 0.1em; margin-bottom: 8px; font-weight: 600; }
.legend-item { display: flex; align-items: center; gap: 8px; padding: 2.5px 0; }
.legend-dot  { width: 14px; height: 10px; border-radius: 2px; flex-shrink: 0; }

.lifestyle-ring { width: 80px; height: 80px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.lifestyle-inner { width: 60px; height: 60px; border-radius: 50%; background: #0f172a; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 700; color: #c084fc; font-family: monospace; }

.dl-item { background: #020617; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; display: flex; align-items: flex-start; gap: 14px; }
.dl-icon { width: 44px; height: 44px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; }
.dl-name { font-size: 13px; font-weight: 600; color: #e2e8f0; margin-bottom: 2px; }
.dl-meta { font-size: 10px; color: #64748b; font-family: monospace; margin-bottom: 4px; }

.na { color: #475569; font-style: italic; font-size: 13px; }
.code-pre { background: #020617; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; font-family: monospace; font-size: 10px; color: #94a3b8; overflow-x: auto; max-height: 140px; overflow-y: auto; line-height: 1.6; white-space: pre; }
"""


_JS = """
function showTab(id) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
  document.getElementById('tab-btn-' + id).classList.add('active');
  document.getElementById('tab-' + id).classList.add('active');
}

function dlData(b64, filename) {
  if (!b64) { alert('File not available.'); return; }
  const a = document.createElement('a');
  a.href = b64;
  a.download = filename;
  a.click();
}

function getGenomeSelectedFeatures(svg) {
  return Array.from(svg.querySelectorAll('.genome-feature.is-selected'));
}

function packGenomeAnnotationPositions(features, side, svgWidth, svgHeight) {
  const minY = 22;
  const maxY = svgHeight - 22;
  const spacing = 16;
  const packed = features
    .map((feature) => ({
      feature,
      desiredY: Number(feature.dataset.desiredLabelY || 0),
    }))
    .sort((a, b) => a.desiredY - b.desiredY);

  let lastY = minY - spacing;
  packed.forEach((item) => {
    item.y = Math.max(item.desiredY, lastY + spacing);
    lastY = item.y;
  });

  if (packed.length && packed[packed.length - 1].y > maxY) {
    packed[packed.length - 1].y = maxY;
    for (let i = packed.length - 2; i >= 0; i -= 1) {
      packed[i].y = Math.min(packed[i].y, packed[i + 1].y - spacing);
    }
    if (packed[0].y < minY) {
      const shift = minY - packed[0].y;
      packed.forEach((item) => {
        item.y = Math.min(maxY, item.y + shift);
      });
    }
  }

  return packed.map((item) => {
    const isRight = side === 'right';
    const lineX3 = isRight ? (svgWidth - 260) : 340;
    const textX = isRight ? (svgWidth - 252) : 332;
    return {
      feature: item.feature,
      y: item.y,
      lineX3,
      textX,
      textAnchor: isRight ? 'start' : 'end',
    };
  });
}

function createGenomeAnnotationGroup(svg, layout) {
  const feature = layout.feature;
  const ns = 'http://www.w3.org/2000/svg';
  const group = document.createElementNS(ns, 'g');
  group.setAttribute('class', 'gene-annotation');
  group.setAttribute('data-feature-id', feature.dataset.featureId);
  group.setAttribute('data-side', feature.dataset.side || '');

  const line1 = document.createElementNS(ns, 'line');
  line1.setAttribute('class', 'gene-annotation-line');
  line1.setAttribute('x1', feature.dataset.lineX1);
  line1.setAttribute('y1', feature.dataset.lineY1);
  line1.setAttribute('x2', feature.dataset.lineX2);
  line1.setAttribute('y2', feature.dataset.lineY2);

  const line2 = document.createElementNS(ns, 'line');
  line2.setAttribute('class', 'gene-annotation-line');
  line2.setAttribute('x1', feature.dataset.lineX2);
  line2.setAttribute('y1', feature.dataset.lineY2);
  line2.setAttribute('x2', String(layout.lineX3));
  line2.setAttribute('y2', String(layout.y));

  const text = document.createElementNS(ns, 'text');
  text.setAttribute('class', 'gene-annotation-text');
  text.setAttribute('x', String(layout.textX));
  text.setAttribute('y', String(layout.y));
  text.setAttribute('text-anchor', layout.textAnchor);
  text.textContent = feature.dataset.label || 'CDS';

  group.appendChild(line1);
  group.appendChild(line2);
  group.appendChild(text);

  const layer = svg.querySelector('.genome-annotations');
  layer.appendChild(group);

  const bbox = text.getBBox();
  const bg = document.createElementNS(ns, 'rect');
  bg.setAttribute('class', 'gene-annotation-bg');
  bg.setAttribute('x', String(bbox.x - 4));
  bg.setAttribute('y', String(bbox.y - 2));
  bg.setAttribute('width', String(bbox.width + 8));
  bg.setAttribute('height', String(bbox.height + 4));
  group.insertBefore(bg, text);
}

function rebuildGenomeSelectionPanel(svg) {
  const wrap = svg.closest('.genome-svg-wrap');
  if (!wrap) return;
  const panel = wrap.querySelector('.genome-selection-list');
  const empty = wrap.querySelector('.genome-selection-empty');
  if (!panel || !empty) return;

  const selected = getGenomeSelectedFeatures(svg).sort((a, b) => {
    return Number(a.dataset.start || 0) - Number(b.dataset.start || 0);
  });

  panel.innerHTML = '';
  if (!selected.length) {
    empty.style.display = '';
    return;
  }

  empty.style.display = 'none';
  selected.forEach((feature) => {
    const item = document.createElement('div');
    item.className = 'genome-selection-item';

    const label = document.createElement('div');
    label.className = 'genome-selection-label';
    label.textContent = feature.dataset.label || feature.dataset.locusTag || 'CDS';

    const meta = document.createElement('div');
    meta.className = 'genome-selection-meta';
    const locusTag = feature.dataset.locusTag || '—';
    const coords = feature.dataset.coords || '—';
    const category = feature.dataset.category || 'unknown function';
    meta.textContent = locusTag + ' | ' + coords + ' | ' + category;

    const product = document.createElement('div');
    product.className = 'genome-selection-product';
    product.textContent = feature.dataset.product || 'hypothetical protein';

    item.appendChild(label);
    item.appendChild(meta);
    item.appendChild(product);
    panel.appendChild(item);
  });
}

function rebuildGenomeAnnotations(svg) {
  if (!svg) return;
  const layer = svg.querySelector('.genome-annotations');
  if (!layer) return;
  layer.innerHTML = '';

  const selected = getGenomeSelectedFeatures(svg);
  const svgWidth = Number(svg.viewBox.baseVal.width || 1280);
  const svgHeight = Number(svg.viewBox.baseVal.height || 660);
  const left = selected.filter((node) => node.dataset.side === 'left');
  const right = selected.filter((node) => node.dataset.side !== 'left');
  const layouts = [
    ...packGenomeAnnotationPositions(left, 'left', svgWidth, svgHeight),
    ...packGenomeAnnotationPositions(right, 'right', svgWidth, svgHeight),
  ];
  layouts.forEach((layout) => createGenomeAnnotationGroup(svg, layout));
  rebuildGenomeSelectionPanel(svg);
}

function toggleGenomeAnnotation(feature) {
  const svg = feature.closest('svg');
  if (!svg) return;
  feature.classList.toggle('is-selected');
  rebuildGenomeAnnotations(svg);
}

function clearGenomeAnnotations(button) {
  const wrap = button.closest('.genome-svg-wrap');
  if (!wrap) return;
  wrap.querySelectorAll('.genome-feature.is-selected').forEach((node) => node.classList.remove('is-selected'));
  const svg = wrap.querySelector('svg');
  if (svg) rebuildGenomeAnnotations(svg);
}

function downloadAnnotatedGenomeMap(button) {
  const wrap = button.closest('.genome-svg-wrap');
  if (!wrap) return;
  const svg = wrap.querySelector('svg');
  if (!svg) return;
  const clone = svg.cloneNode(true);
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
  const style = document.createElementNS('http://www.w3.org/2000/svg', 'style');
  style.textContent = `
    .genome-export-bg { fill: #ffffff !important; }
    .genome-ring { stroke: #475569 !important; }
    .genome-tick-line { stroke: #64748b !important; }
    .genome-tick-label { fill: #64748b !important; }
    .genome-center-name { fill: #334155 !important; }
    .genome-center-size { fill: #0f172a !important; }
    .genome-center-gc { fill: #475569 !important; }
    .genome-feature.is-selected { stroke: #0f172a !important; stroke-width: 1.6 !important; opacity: 1 !important; }
    .gene-annotation-line { stroke: #334155 !important; stroke-width: 1.2; fill: none; stroke-linecap: round; }
    .gene-annotation-bg { fill: rgba(255, 255, 255, 0.96) !important; stroke: #94a3b8 !important; stroke-width: 0.8; }
    .gene-annotation-text { fill: #0f172a !important; font-size: 11px; font-family: monospace; dominant-baseline: middle; }
  `;
  clone.insertBefore(style, clone.firstChild);
  const serializer = new XMLSerializer();
  const svgText = '<?xml version=\"1.0\" encoding=\"UTF-8\"?>\\n' + serializer.serializeToString(clone);
  const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = (wrap.dataset.filenameBase || 'genome_map') + '_annotated.svg';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

document.addEventListener('click', (event) => {
  const feature = event.target.closest('.genome-feature');
  if (feature) {
    toggleGenomeAnnotation(feature);
  }
});

document.addEventListener('keydown', (event) => {
  const feature = event.target.closest('.genome-feature');
  if (!feature) return;
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    toggleGenomeAnnotation(feature);
  }
});
"""


def _badge(text: str, variant: str = "default") -> str:
    return f'<span class="badge badge-{variant}">{text}</span>'


def _check(label: str, passed: bool) -> str:
    icon_class = "check-pass" if passed else "check-fail"
    icon = "✓" if passed else "✗"
    return (
        f'<div class="check-item">'
        f'<span class="check-icon {icon_class}">{icon}</span>'
        f'{label}</div>'
    )


def _check_with_hits(label: str, passed: bool, hits=None) -> str:
    """Like ``_check`` but, when failing, lists each detected hit with its
    gene name, % sequence identity, and detection source (e.g. phold
    foldseek structural alignment vs. Pharokka MMseqs2). Structural-only
    hits at low % identity are real signals that should be visible, but a
    reader needs to see the identity to judge them."""
    header = _check(label, passed)
    if passed or not hits:
        return header

    items = []
    for h in hits or []:
        name = html.escape(str(h.get("name") or "?"))
        pct = h.get("identity_pct")
        src = html.escape(str(h.get("source") or ""))
        evalue = html.escape(str(h.get("evalue") or ""))
        aln_score = html.escape(str(h.get("aln_score") or ""))
        meta_bits = []
        if pct is not None:
            meta_bits.append(f"<strong>{pct}% identity</strong>")
        if src:
            meta_bits.append(src)
        if evalue:
            meta_bits.append(f"E={evalue}")
        elif aln_score:
            # Pharokka MMseqs2 has no E-value column; show alnScore instead.
            meta_bits.append(f"alnScore={aln_score}")
        # Optional extras for AMR vs VF detail
        extra = h.get("drug_class") or h.get("description")
        if extra:
            meta_bits.append(html.escape(str(extra)))
        meta = " · ".join(meta_bits)
        items.append(
            f'<li style="margin:2px 0">'
            f'<span style="color:#f1f5f9">{name}</span> '
            f'<span style="color:#94a3b8;font-size:11px">{meta}</span>'
            f'</li>'
        )
    if not items:
        return header

    detail = (
        '<ul style="margin:4px 0 8px 36px;padding:0;list-style:disc;'
        'color:#cbd5e1;font-size:12px;line-height:1.6">'
        + "".join(items)
        + '</ul>'
    )
    return header + detail


def _na(msg: str = "No data available") -> str:
    return f'<span class="na">{msg}</span>'


def _tool_banner(d: Dict[str, Any], tool_key: str) -> str:
    """
    Warning banner for a tool that did not run for this genome.

    Returns '' when the tool ran (or its status is unknown), so a section can
    do ``_tool_banner(d, key) or <normal empty state>`` and surface the banner
    only when the tool genuinely failed / never ran — never when it ran and
    simply found nothing.
    """
    info = (d.get("tool_status") or {}).get(tool_key)
    if not info or info.get("ran", True):
        return ""
    label = info.get("label", tool_key)
    reason = info.get("reason") or "did not run"
    return (
        '<div style="display:flex;gap:10px;align-items:flex-start;'
        'padding:11px 14px;background:#451a03;border:1px solid #92400e;'
        'border-radius:8px;color:#fbbf24;font-size:13px;line-height:1.5">'
        '<span style="font-size:15px;line-height:1.3">⚠️</span>'
        f'<span><strong>{label} {reason}</strong> — results unavailable for this '
        'genome. An empty section here means the tool produced no output, not '
        'that nothing was found.</span>'
        '</div>'
    )


def _organism_label_from_hosts(hosts: list[Dict[str, Any]]) -> str:
    for row in hosts or []:
        host = (row.get("host") or "").strip()
        if not host or host.lower() in {"undetermined", "unknown", "-", "—"}:
            continue
        cleaned = host
        if ":" in cleaned:
            prefix, value = cleaned.split(":", 1)
            if prefix.lower() in {"genus", "species", "host"} and value.strip():
                cleaned = value.strip()
        genus = cleaned.split()[0].strip()
        if genus:
            return f"{genus} phage"
    return "phage"


def _render_interactive_genome_map(genome_map: Dict[str, Any], map_name: str = "genome_map") -> str:
    length = int(genome_map.get("length") or 0)
    features = genome_map.get("features") or []
    if length <= 0 or not features:
        return ""

    width = 1280
    height = 660
    cx = 560
    cy = height / 2

    def bp_to_angle(bp: int) -> float:
        return (bp / length) * 2 * math.pi - math.pi / 2

    def polar_point(radius: float, angle: float) -> tuple[float, float]:
        return (cx + radius * math.cos(angle), cy + radius * math.sin(angle))

    def annulus_path(start_bp: int, end_bp: int, r_outer: float, r_inner: float) -> str:
        a_start = bp_to_angle(start_bp)
        a_end = bp_to_angle(end_bp)
        if a_end < a_start:
            a_end += 2 * math.pi
        large_arc = 1 if (a_end - a_start) > math.pi else 0
        x1o, y1o = polar_point(r_outer, a_start)
        x2o, y2o = polar_point(r_outer, a_end)
        x2i, y2i = polar_point(r_inner, a_end)
        x1i, y1i = polar_point(r_inner, a_start)
        return (
            f"M {x1o:.2f} {y1o:.2f} "
            f"A {r_outer:.2f} {r_outer:.2f} 0 {large_arc} 1 {x2o:.2f} {y2o:.2f} "
            f"L {x2i:.2f} {y2i:.2f} "
            f"A {r_inner:.2f} {r_inner:.2f} 0 {large_arc} 0 {x1i:.2f} {y1i:.2f} Z"
        )

    def tick_line(bp: int, r1: float, r2: float) -> str:
        a = bp_to_angle(bp)
        x1, y1 = polar_point(r1, a)
        x2, y2 = polar_point(r2, a)
        return f'<line class="genome-tick-line" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#64748b" stroke-width="1" />'

    def tick_label(bp: int, r: float) -> str:
        a = bp_to_angle(bp)
        x, y = polar_point(r, a)
        label = "0 kb" if bp == 0 else f"{bp // 1000} kb"
        return (
            f'<text class="genome-tick-label" x="{x:.2f}" y="{y:.2f}" fill="#64748b" font-size="10" '
            f'font-family="monospace" text-anchor="middle" dominant-baseline="middle">{label}</text>'
        )

    rings = [
        f'<rect class="genome-export-bg" x="0" y="0" width="{width}" height="{height}" fill="#020617" />',
        f'<circle class="genome-ring" cx="{cx:.1f}" cy="{cy:.1f}" r="194" fill="none" stroke="#334155" stroke-width="1.1" />',
        f'<circle class="genome-ring" cx="{cx:.1f}" cy="{cy:.1f}" r="150" fill="none" stroke="#1e293b" stroke-width="1" />',
        f'<circle class="genome-ring" cx="{cx:.1f}" cy="{cy:.1f}" r="119" fill="none" stroke="#1e293b" stroke-width="0.9" />',
        f'<circle class="genome-ring" cx="{cx:.1f}" cy="{cy:.1f}" r="92" fill="none" stroke="#1e293b" stroke-width="0.9" />',
    ]

    gc_paths = []
    gc_content = genome_map.get("gc_content") or []
    if len(gc_content) > 1:
        mean_gc = sum(gc_content) / len(gc_content)
        for i, value in enumerate(gc_content):
            start_bp = round(i * length / len(gc_content))
            end_bp = round((i + 1) * length / len(gc_content))
            delta = value - mean_gc
            outer = 119 + min(18, abs(delta) * 90)
            path = annulus_path(start_bp, end_bp, outer, 119)
            color = "#334155" if delta >= 0 else "#1e293b"
            gc_paths.append(f'<path d="{path}" fill="{color}" opacity="0.75" />')

    skew_paths = []
    gc_skew = genome_map.get("gc_skew") or []
    if len(gc_skew) > 1:
        for i, value in enumerate(gc_skew):
            start_bp = round(i * length / len(gc_skew))
            end_bp = round((i + 1) * length / len(gc_skew))
            outer = 92 + min(16, abs(value) * 42)
            path = annulus_path(start_bp, end_bp, outer, 92)
            color = "#22c55e" if value >= 0 else "#a855f7"
            skew_paths.append(f'<path d="{path}" fill="{color}" opacity="0.55" />')

    feature_paths = []
    for idx, feat in enumerate(features, start=1):
        strand = int(feat.get("strand") or 1)
        r_outer = 194 if strand == 1 else 149
        r_inner = 174 if strand == 1 else 129
        gene = (feat.get("gene") or "").strip()
        locus_tag = (feat.get("locus_tag") or "").strip()
        product = feat.get("product") or "hypothetical protein"
        category = feat.get("category") or "unknown function"
        label = gene or (product if product.lower() != "hypothetical protein" else locus_tag) or "CDS"
        strand_txt = "+" if strand == 1 else "-"
        start_bp = int(feat.get("start", 0))
        end_bp = int(feat.get("end", 0))
        mid_bp = start_bp + ((end_bp - start_bp) / 2)
        angle = bp_to_angle(mid_bp)
        line_start_radius = r_outer + 3
        elbow_radius = 226 if strand == 1 else 170
        x1, y1 = polar_point(line_start_radius, angle)
        x2, y2 = polar_point(elbow_radius, angle)
        right_side = math.cos(angle) >= 0
        side = "right" if right_side else "left"
        title = "\n".join([
            label,
            product,
            f"{start_bp + 1:,}-{end_bp:,} bp ({strand_txt})",
            f"Category: {category}",
        ])
        feature_paths.append(
            f'<path class="genome-feature" data-feature-id="feat-{idx}" data-label="{html.escape(label)}" '
            f'data-locus-tag="{html.escape(locus_tag)}" data-product="{html.escape(product)}" '
            f'data-category="{html.escape(category)}" data-start="{start_bp}" '
            f'data-coords="{start_bp + 1:,}-{end_bp:,} bp ({strand_txt})" '
            f'data-line-x1="{x1:.2f}" data-line-y1="{y1:.2f}" data-line-x2="{x2:.2f}" data-line-y2="{y2:.2f}" '
            f'data-desired-label-y="{y2:.2f}" data-side="{side}" tabindex="0" '
            f'd="{annulus_path(start_bp, end_bp, r_outer, r_inner)}" '
            f'fill="{feat["color"]}" stroke="#020617" stroke-width="0.8" opacity="0.92">'
            f"<title>{html.escape(title)}</title></path>"
        )

    tick_step_kb = max(5, round(length / 8 / 5000) * 5)
    tick_step = max(5000, tick_step_kb * 1000)
    ticks = [tick_line(bp, 198, 208) + tick_label(bp, 222) for bp in range(0, length, tick_step)]

    center_text = [
        f'<text class="genome-center-name" x="{cx:.1f}" y="{cy - 32:.1f}" fill="#94a3b8" font-size="13" font-weight="600" font-family="monospace" text-anchor="middle">{html.escape(map_name)}</text>',
        f'<text class="genome-center-size" x="{cx:.1f}" y="{cy + 4:.1f}" fill="#cbd5e1" font-size="18" font-weight="700" font-family="monospace" text-anchor="middle">{length / 1000:.1f} kb</text>',
        f'<text class="genome-center-gc" x="{cx:.1f}" y="{cy + 32:.1f}" fill="#64748b" font-size="11" font-family="monospace" text-anchor="middle">GC {float(genome_map.get("gc_percent") or 0):.1f}%</text>',
    ]

    svg = "\n".join(
        [
            f'<svg class="genome-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Interactive circular genome map">',
            *rings,
            *gc_paths,
            *skew_paths,
            *feature_paths,
            '<g class="genome-annotations"></g>',
            *ticks,
            *center_text,
            "</svg>",
        ]
    )
    return (
        f'<div class="genome-svg-wrap" data-filename-base="{html.escape(map_name)}">'
        f"{svg}"
        '<div class="genome-toolbar">'
        '<button type="button" class="dl-btn green" onclick="downloadAnnotatedGenomeMap(this)">⬇ Download Annotated SVG</button>'
        '<button type="button" class="dl-btn" onclick="clearGenomeAnnotations(this)">Clear Labels</button>'
        '</div>'
        '<div class="genome-selection-panel">'
        '<div class="genome-selection-title">Selected Gene Annotations</div>'
        '<div class="genome-selection-empty">Click one or more CDS segments to list their full annotations here.</div>'
        '<div class="genome-selection-list"></div>'
        '</div>'
        '<div class="genome-hint">Hover any CDS segment to inspect the gene name, product, coordinates, and strand. Click a CDS to pin its gene label onto the map. Labels are automatically stacked into left/right lanes to reduce collisions, and the downloaded SVG preserves that cleaned-up layout.</div>'
        '</div>'
    )


def render_report(d: Dict[str, Any]) -> str:
    """Render the full report card HTML for phage *d*."""

    name = d["name"]
    genome = d["genome"]
    lifestyle = d["lifestyle"]
    therapy = d["therapy"]
    dl = d["downloads"]

    # ------------------------------------------------------------------ #
    # Header badges
    # ------------------------------------------------------------------ #
    ls_label = lifestyle["lifestyle"]
    ls_badge = _badge(ls_label, "lytic" if ls_label.lower() == "lytic" else "warn")
    th_badge = _badge(
        "THERAPY CANDIDATE ✓" if therapy["suitable"] else "NOT SUITABLE ✗",
        "pass" if therapy["suitable"] else "fail",
    )

    # ------------------------------------------------------------------ #
    # Overview tab
    # ------------------------------------------------------------------ #
    total_proteins = genome["cds_count"]
    annotated = sum(
        c["count"] for c in d["phrog_cats"]
        if "unknown" not in c["name"].lower()
    )
    organism_label = _organism_label_from_hosts(d.get("hosts", []))
    host_badges = " ".join(
        _badge(h["host"], "info") for h in d["hosts"]
    ) or _tool_banner(d, "phabox2") or _na("No host prediction data")

    tax = d["taxonomy"]
    tax_html = ""
    if tax:
        ranks = [
            ("Realm",     tax.get("realm",     "—")),
            ("Kingdom",   tax.get("kingdom",   "—")),
            ("Phylum",    tax.get("phylum",    "—")),
            ("Class",     tax.get("class_",    "—")),
            ("Order",     tax.get("order",     "—")),
            ("Family",    tax.get("family",    "—")),
            ("Subfamily", tax.get("subfamily", "—")),
            ("Genus",     tax.get("genus",     "—")),
        ]
        # Render as a two-column grid of rank → value pairs
        items = "".join(
            f'<div style="display:flex;align-items:baseline;gap:8px;padding:4px 0;border-bottom:1px solid #1e293b">'
            f'<span style="font-size:10px;color:#64748b;font-family:monospace;text-transform:uppercase;'
            f'letter-spacing:0.08em;width:80px;flex-shrink:0">{lbl}</span>'
            f'<span style="font-size:13px;color:{"#e2e8f0" if val != "—" else "#334155"};font-weight:{"500" if val != "—" else "400"}">{val}</span>'
            f'</div>'
            for lbl, val in ranks
        )
        tax_source = d.get("taxonomy_source") or "vConTACT3 v3.1.6 — RefSeq v230"
        tax_html = f'<div style="margin-top:8px">{items}</div><div style="margin-top:8px;font-size:10px;color:#475569">Source: {tax_source}</div>'

    def _dl_btn(key: str, label: str, filename: str, cls: str = "") -> str:
        b64 = dl.get(key)
        if not b64:
            return f'<span class="na">Not available</span>'
        return (
            f'<a class="dl-btn {cls}" href="{b64}" download="{filename}">⬇ {label}</a>'
        )

    def _render_closest_phages(phages: list) -> str:
        if not phages:
            return _na("vConTACT3 did not return network neighbors for this genome")
        rows = ""
        for p in phages:
            acc = p.get("genome_id", "—")
            acc_html = (
                f"<a href='{p['ncbi_url']}' target='_blank' style='color:#60a5fa;text-decoration:none'>{acc}</a>"
                if p.get("ncbi_url") else acc
            )
            distance = "—" if p.get("distance") is None else f"{float(p['distance']):.4f}"
            rows += (
                f"<tr>"
                f"<td>{acc_html}</td>"
                f"<td>{p['name']}</td>"
                f"<td>{distance}</td>"
                f"<td>{p.get('shared_genes', '—')}</td>"
                f"<td>{p.get('order', '—')}</td>"
                f"<td>{p['family']}</td>"
                f"<td>{p.get('subfamily', '—')}</td>"
                f"<td>{p['genus']}</td>"
                f"</tr>"
            )
        return (
            f'<div style="font-size:11px;color:#475569;margin-bottom:8px">'
            f'Source: vConTACT3 protein-sharing network. Lower distance means closer network similarity.</div>'
            f'<table class="mini-table"><thead><tr>'
            f'<th>Accession</th><th>Name</th><th>Distance</th><th>Shared Genes</th><th>Order</th><th>Family</th><th>Subfamily</th><th>Genus</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>'
        )

    overview_tab = f"""
<div class="grid-4">
  <div class="card"><div class="stat-label">Genome Length</div>
    <div class="stat-value">{genome["length"] / 1000:.1f} kb</div>
    <div class="stat-sub">{genome["length"]:,} bp</div></div>
  <div class="card"><div class="stat-label">GC Content</div>
    <div class="stat-value">{genome["gc_percent"]}%</div></div>
  <div class="card"><div class="stat-label">Total ORFs</div>
    <div class="stat-value">{total_proteins}</div>
    <div class="stat-sub">{annotated} annotated</div></div>
  <div class="card"><div class="stat-label">tRNAs</div>
    <div class="stat-value">{genome["trna_count"]}</div></div>

  <div class="card col-1-3">
    <div class="section-title">🧬 Taxonomy</div>
    {tax_html if tax_html else (_tool_banner(d, "vcontact3") or _na("Run vConTACT3 for taxonomy"))}
  </div>

  <div class="card col-3-5">
    <div class="section-title">🦠 Predicted Host</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px">{host_badges}</div>
  </div>

  <div class="card col-span-4">
    <div class="section-title">🔗 Closest Related Phages</div>
    {_render_closest_phages(d.get("closest_phages", []))}
  </div>

  <div class="card col-span-4">
    <div class="section-title">📁 NCBI BankIt Submission Files</div>
    <div style="font-size:12px;color:#94a3b8;margin-bottom:16px;line-height:1.6">
      Download the files required for NCBI BankIt genome submission.
    </div>
    <div class="grid-2" style="gap:14px">
      <div class="dl-item">
        <div class="dl-icon" style="background:linear-gradient(135deg,#1e3a5f,#0c1a3d);border:1px solid #1e3a5f">🧬</div>
        <div>
          <div class="dl-name">bankit_multi.fasta</div>
          <div class="dl-meta">Multi-FASTA · BankIt-ready genome sequences</div>
          {_dl_btn("ncbi_fasta", "Download Multi-FASTA", "bankit_multi.fasta")}
        </div>
      </div>
      <div class="dl-item">
        <div class="dl-icon" style="background:linear-gradient(135deg,#3b0764,#581c87);border:1px solid #581c87">📋</div>
        <div>
          <div class="dl-name">bankit_features.tbl</div>
          <div class="dl-meta">5-Column Feature Table · NCBI BankIt format</div>
          {_dl_btn("ncbi_tbl", "Download Feature Table", "bankit_features.tbl", "purple")}
        </div>
      </div>
    </div>
  </div>
</div>"""

    # ------------------------------------------------------------------ #
    # Genome tab
    # ------------------------------------------------------------------ #
    interactive_genome_map = _render_interactive_genome_map(d.get("genome_map") or {}, name)
    if interactive_genome_map:
        genome_img = interactive_genome_map
    elif d.get("genome_map_b64"):
        genome_img = f'<img class="genome-img" src="{d["genome_map_b64"]}" alt="Circular genome map" />'
    else:
        genome_img = _na("Genome map not generated")

    phrog_bars = ""
    for cat in sorted(d["phrog_cats"], key=lambda x: -x["count"]):
        pct = (cat["count"] / total_proteins * 100) if total_proteins else 0
        phrog_bars += f"""
<div class="bar-row">
  <div class="bar-label">
    <div style="width:8px;height:8px;border-radius:2px;background:{cat["color"]}"></div>
    {cat["name"]}
  </div>
  <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;background:{cat["color"]}"></div></div>
  <div class="bar-count">{cat["count"]}</div>
  <div class="bar-pct">{pct:.1f}%</div>
</div>"""

    genome_tab = f"""
<div class="card">
  <div class="section-title">🗺️ Circular Genome Map</div>
  <div class="flex-gap">
    <div style="flex:1 1 400px;min-width:280px">{genome_img}</div>
    <div class="legend-section">
      <div>
        <div class="legend-title">PHROG CDS</div>
        {''.join(
            f'<div class="legend-item"><div class="legend-dot" style="background:{c["color"]}"></div>'
            f'<span style="font-size:10.5px;color:#cbd5e1">{c["name"]}</span></div>'
            for c in d["phrog_cats"]
        )}
      </div>
      <div>
        <div class="legend-title">GC Skew</div>
        <div class="legend-item"><span style="color:#22c55e">▲</span> <span style="font-size:10px;color:#94a3b8">Positive</span></div>
        <div class="legend-item"><span style="color:#a855f7">▼</span> <span style="font-size:10px;color:#94a3b8">Negative</span></div>
      </div>
    </div>
  </div>
</div>
<div class="card" style="margin-top:14px">
  <div class="section-title">📊 Protein Functional Categories (PHROG)</div>
  {phrog_bars or _na("No PHROG annotations found")}
</div>"""

    # ------------------------------------------------------------------ #
    # Therapy tab
    # ------------------------------------------------------------------ #
    verdict_bg = (
        "linear-gradient(135deg,#052e16,#0f172a)" if therapy["suitable"]
        else "linear-gradient(135deg,#450a0a,#0f172a)"
    )
    verdict_border = "#166534" if therapy["suitable"] else "#991b1b"
    verdict_emoji  = "✅" if therapy["suitable"] else "❌"
    verdict_label  = "Suitable Candidate" if therapy["suitable"] else "Not Suitable"
    verdict_color  = "#4ade80" if therapy["suitable"] else "#f87171"

    conf_pct = int(lifestyle["confidence"] * 100)
    conic = f"conic-gradient(#8b5cf6 {lifestyle['confidence'] * 360:.0f}deg, #1e293b 0deg)"
    amr_label = (
        "No antimicrobial resistance genes"
        if therapy["no_amr"]
        else "Antimicrobial resistance genes detected"
    )
    virulence_label = (
        "No virulence factor genes"
        if therapy["no_virulence"]
        else "Virulence factor genes detected"
    )
    integrase_label = (
        "No integrase / recombinase detected"
        if therapy["no_integrase"]
        else "Integrase / recombinase detected"
    )

    therapy_tab = f"""
<div class="grid-2">
  <div class="card">
    <div class="section-title">💊 Phage Therapy Suitability</div>
    <div style="text-align:center;padding:16px;margin-bottom:16px;border-radius:8px;
                background:{verdict_bg};border:1px solid {verdict_border}">
      <div style="font-size:28px;margin-bottom:4px">{verdict_emoji}</div>
      <div style="font-size:16px;font-weight:600;color:{verdict_color}">{verdict_label}</div>
    </div>
    {_check("Strictly lytic lifecycle", therapy["strictly_lytic"])}
    {_check_with_hits(amr_label, therapy["no_amr"], therapy.get("_amr_hits"))}
    {_check_with_hits(virulence_label, therapy["no_virulence"], therapy.get("_vf_hits"))}
    {_check(integrase_label, therapy["no_integrase"])}
  </div>
  <div class="card">
    <div class="section-title">🔄 Lifestyle Prediction</div>
    {_tool_banner(d, "phastyle")}
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px">
      <div class="lifestyle-ring" style="background:{conic}">
        <div class="lifestyle-inner">{conf_pct}%</div>
      </div>
      <div>
        <div style="font-size:20px;font-weight:600;color:#e2e8f0">{ls_label}</div>
        <div style="font-size:12px;color:#64748b;margin-top:2px">ProkBERT PhaStyle prediction</div>
      </div>
    </div>
  </div>
</div>"""

    # ------------------------------------------------------------------ #
    # Defence tab
    # ------------------------------------------------------------------ #
    def _defence_table(rows: list, headers: list, row_fn, empty: str = "") -> str:
        if not rows:
            return empty or _na("None detected")
        header_html = "".join(f"<th>{h}</th>" for h in headers)
        body_html = "".join(
            f"<tr>{''.join(f'<td>{c}</td>' for c in row_fn(r))}</tr>"
            for r in rows
        )
        return f'<table class="mini-table"><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>'

    def _acr_row(r: dict) -> list:
        return [
            r.get("protein") or "—",
            r.get("gene_name") or "—",
            r.get("subtype") or "—",
            r.get("evalue") or "—",
            r.get("source") or "DefenseFinder",
        ]

    def _defense_system_row(r: dict) -> list:
        return [
            r.get("type") or "—",
            r.get("subtype") or "—",
            r.get("activity") or "—",
            r.get("proteins") or "—",
            r.get("genes_count") or "—",
            r.get("source") or "DefenseFinder",
        ]

    def _defense_gene_row(r: dict) -> list:
        return [
            r.get("protein") or "—",
            r.get("gene_name") or "—",
            r.get("type") or "—",
            r.get("subtype") or "—",
            r.get("evalue") or "—",
            r.get("source") or "DefenseFinder",
        ]

    defence_tab = f"""
<div class="card">
  <div class="section-title">🛡️ Anti-CRISPR Proteins</div>
  {_defence_table(d["defence"]["acr"], ["Protein", "Gene", "Subtype", "E-value", "Source"], _acr_row)}
</div>
<div class="card">
  <div class="section-title">⚔️ Antidefense Systems</div>
  {_defence_table(
      d["defence"]["defence_finder"],
      ["Type", "Subtype", "Activity", "Proteins", "Gene Count", "Source"],
      _defense_system_row,
      empty=_tool_banner(d, "defensefinder"),
  )}
</div>
<div class="card">
  <div class="section-title">🧾 Antidefense Gene Hits</div>
  {_defence_table(
      d["defence"]["defence_finder_genes"],
      ["Protein", "Gene", "Type", "Subtype", "E-value", "Source"],
      _defense_gene_row,
      empty=_tool_banner(d, "defensefinder"),
  )}
</div>
<div class="card">
  <div class="section-title">🧪 NetFlax — Anti-TA Predictions</div>
  {_defence_table(d["defence"]["netflax"], ["Protein", "Note"],
                  lambda r: [r["protein"], r["note"]])}
</div>"""

    # ------------------------------------------------------------------ #
    # Tail Fibers tab
    # ------------------------------------------------------------------ #
    rbp_rows = d["rbp"]
    depo_rows = d["deposcope"]

    def _rbp_row(r: dict) -> list:
        return [r["protein"], r.get("length", ""), f'{r["score"]:.3f}',
                _badge("RBP", "pass")]

    def _depo_row(r: dict) -> list:
        is_d = _badge("Yes", "pass") if r["is_depo"] else _badge("No", "default")
        return [r["protein"], f'{r["score"]:.3f}', is_d,
                r.get("domain_type") or "—",
                f'{r.get("domain_start","")}-{r.get("domain_end","")}' if r.get("domain_start") else "—"]

    tailfibers_tab = f"""
<div class="card">
  <div class="section-title">🔍 PhageRBPdetect — Receptor-Binding Proteins</div>
  {_defence_table(rbp_rows, ["Protein", "Length", "RBP Score", "Class"], _rbp_row,
                  empty=_tool_banner(d, "rbpdetect"))}
</div>
<div class="card">
  <div class="section-title">🧬 DepoScope — Depolymerase Predictions</div>
  {_defence_table(depo_rows, ["Protein", "Dep Score", "Is Depolymerase", "Domain Type", "Domain Region"], _depo_row,
                  empty=_tool_banner(d, "deposcope"))}
</div>"""

    # ------------------------------------------------------------------ #
    # Downloads tab
    # ------------------------------------------------------------------ #
    def _dl_row(fi: Optional[Dict], icon: str, label: str, desc: str, cls: str = "") -> str:
        """Render one download row. fi = _file_info() dict or None."""
        if not fi:
            return f"""
<div class="dl-item">
  <div class="dl-icon" style="background:#1e293b;border:1px solid #1e293b;opacity:0.4">{icon}</div>
  <div><div class="dl-name" style="color:#475569">{label}</div>
  <div class="dl-meta">{desc}</div>
  <span class="na">Not generated this run</span></div>
</div>"""
        size_str = f"{fi['size_kb']:.0f} KB" if fi['size_kb'] < 1024 else f"{fi['size_kb']/1024:.1f} MB"
        if fi.get("b64"):
            btn = f'<a class="dl-btn {cls}" href="{fi["b64"]}" download="{fi["name"]}">⬇ Download ({size_str})</a>'
        elif fi.get("href"):
            btn = f'<a class="dl-btn {cls}" href="{fi["href"]}" download="{fi["name"]}">⬇ Open file ({size_str})</a>'
        else:
            btn = f'<span style="font-size:11px;color:#f59e0b">⚠ File too large to embed ({size_str}) — find it in the output folder</span>'
        return f"""
<div class="dl-item">
  <div class="dl-icon" style="background:#1e293b;border:1px solid #334155">{icon}</div>
  <div style="flex:1"><div class="dl-name">{fi["name"]}</div>
  <div class="dl-meta">{desc}</div>
  {btn}</div>
</div>"""

    def _section(title: str, rows: str) -> str:
        return f'<div class="card"><div class="section-title">{title}</div><div style="display:flex;flex-direction:column;gap:10px">{rows}</div></div>'

    downloads_tab = (
        _section("🧬 Annotation GenBanks", "".join([
            _dl_row(dl.get("pharokka_gbk"),  "📄", "pharokka.gbk",  "Step 1 — Pharokka initial gene annotation"),
            _dl_row(dl.get("phold_gbk"),     "🔬", "phold.gbk",    "Step 2 — Phold structure-informed re-annotation"),
            _dl_row(dl.get("phynteny_gbk"),  "⭐", "phynteny.gbk", "Step 3 — Phynteny synteny-aware annotation (most complete)", "green"),
        ])) + "\n" +
        _section("🔤 Sequence Files", "".join([
            _dl_row(dl.get("pharokka_faa"),  "🧬", "phanotate.faa",  "Predicted protein sequences (FASTA)"),
            _dl_row(dl.get("pharokka_ffn"),  "📜", "phanotate.ffn",  "CDS nucleotide sequences (FASTA)"),
            _dl_row(dl.get("pharokka_gff"),  "📋", "pharokka.gff",   "GFF3 genome annotations"),
            _dl_row(dl.get("pharokka_tbl"),  "📑", "pharokka.tbl",   "5-column feature table (NCBI format)"),
            _dl_row(dl.get("pharokka_cds_tsv"), "📊", "pharokka_cds_final_merged_output.tsv", "All CDS annotations with PHROG categories"),
        ])) + "\n" +
        _section("📊 Analysis Results", "".join([
            _dl_row(dl.get("genome_map_png"),        "🗺️", "genome_map.png",           "Circular genome map (PNG)"),
            _dl_row(dl.get("phastyle_tsv"),           "🔄", "predictions.tsv",          "PhaStyle — lifestyle prediction (Lytic/Lysogenic/Temperate)"),
            _dl_row(dl.get("cherry_csv"),             "🦠", "host_prediction.csv",      "PhaBOX2 (CHERRY) — predicted host organisms"),
            _dl_row(dl.get("defensefinder_systems_tsv"), "🛡️", "defense_finder_systems.tsv", "DefenseFinder — antidefense system calls"),
            _dl_row(dl.get("defensefinder_genes_tsv"),   "🛡️", "defense_finder_genes.tsv",   "DefenseFinder — per-gene hits including Anti-CRISPR models"),
            _dl_row(dl.get("defensefinder_hmmer_tsv"),   "🛡️", "defense_finder_hmmer.tsv",   "DefenseFinder — raw HMM hit table"),
            _dl_row(dl.get("vcontact3_assignments"),  "🌳", "final_assignments.csv",    "vConTACT3 — full taxonomy assignments (all reference genomes)"),
            _dl_row(dl.get("vcontact3_metrics"),      "📈", "performance_metrics.csv",  "vConTACT3 — clustering performance metrics"),
            _dl_row(dl.get("vcontact3_cyjs"),         "🕸️", "part1.cyjs",              "vConTACT3 — Cytoscape network (import via File → Network from File)"),
            _dl_row(dl.get("vcontact3_graphml"),      "🕸️", "part1.graphml",           "vConTACT3 — GraphML network (Gephi, yEd, Cytoscape)"),
            _dl_row(dl.get("rbp_predictions_csv"),    "🔍", "rbp_predictions.csv",      "PhageRBPdetect — RBP scores for all proteins"),
            _dl_row(dl.get("rbp_candidates_faa"),     "🔍", "rbp_candidates.faa",       "PhageRBPdetect — RBP candidate sequences (score ≥ 0.5)"),
            _dl_row(dl.get("deposcope_results_csv"),  "💧", "deposcope_results.csv",    "DepoScope — depolymerase predictions and derived domain annotations"),
            _dl_row(dl.get("deposcope_tokens_tsv"),   "💧", "deposcope_tokens.tsv",     "DepoScope — per-residue domain labels"),
        ])) + "\n" +
        _section("📁 NCBI BankIt Submission", "".join([
            _dl_row(dl.get("ncbi_fasta"), "🧬", "bankit_multi.fasta",   "BankIt-ready multifasta with [organism=...] headers", "purple"),
            _dl_row(dl.get("ncbi_tbl"),   "📋", "bankit_features.tbl",  "5-column feature table for BankIt submission", "purple"),
        ]))
    )

    # ------------------------------------------------------------------ #
    # Supplementary tab — explanations of all output files
    # ------------------------------------------------------------------ #
    supplementary_tab = f"""
<div class="card">
  <div class="section-title">📖 About the Output Files</div>
  <div style="font-size:13px;color:#94a3b8;line-height:1.7;margin-bottom:8px">
    This section describes every file produced by the Phang pipeline, what tool generated it, and how to use it.
    All files can be downloaded from the <strong style="color:#e2e8f0">Downloads</strong> tab above.
  </div>
</div>

<div class="card">
  <div class="section-title">🧬 Annotation GenBanks</div>
  <table class="mini-table">
    <thead><tr><th>File</th><th>Tool</th><th>Description</th><th>Use for</th></tr></thead>
    <tbody>
      <tr><td>pharokka.gbk</td><td>Pharokka</td><td>Initial gene annotation using PHROG HMM profiles</td><td>Starting annotation, NCBI submission prep</td></tr>
      <tr><td>phold.gbk</td><td>Phold</td><td>Re-annotation using predicted 3D protein structures (ProstT5 + FoldSeek)</td><td>More sensitive annotation of hypothetical proteins</td></tr>
      <tr><td>phynteny.gbk ⭐</td><td>Phynteny</td><td>Final annotation with synteny-aware functional categories (≥0.8 confidence). Most complete file.</td><td>All downstream analysis, visualisation, reporting</td></tr>
    </tbody>
  </table>
</div>

<div class="card">
  <div class="section-title">🔤 Sequence Files</div>
  <table class="mini-table">
    <thead><tr><th>File</th><th>Description</th><th>Use for</th></tr></thead>
    <tbody>
      <tr><td>phanotate.faa</td><td>Predicted protein sequences in FASTA format</td><td>BLAST searches, protein analysis, RBP detection input</td></tr>
      <tr><td>phanotate.ffn</td><td>CDS nucleotide sequences in FASTA format</td><td>Nucleotide-level analysis, primer design</td></tr>
      <tr><td>pharokka.gff</td><td>GFF3 format genome annotations</td><td>Genome browsers (IGV, Artemis, JBrowse)</td></tr>
      <tr><td>pharokka.tbl</td><td>NCBI 5-column feature table</td><td>NCBI BankIt submission, tbl2asn</td></tr>
      <tr><td>pharokka_cds_final_merged_output.tsv</td><td>All CDS with PHROG categories, functions, and scores</td><td>Detailed annotation review, spreadsheet analysis</td></tr>
    </tbody>
  </table>
</div>

<div class="card">
  <div class="section-title">📊 Analysis Results</div>
  <table class="mini-table">
    <thead><tr><th>File</th><th>Tool</th><th>Description</th><th>Use for</th></tr></thead>
    <tbody>
      <tr><td>genome_map.png</td><td>pyCirclize</td><td>Circular genome map coloured by PHROG category with GC content and GC skew rings</td><td>Publications, presentations, visual inspection</td></tr>
      <tr><td>predictions.tsv</td><td>PhaStyle</td><td>Lifestyle prediction (Lytic / Lysogenic / Temperate) with confidence score</td><td>Therapy suitability assessment</td></tr>
      <tr><td>host_prediction.csv</td><td>PhaBOX2 (CHERRY)</td><td>Predicted host organisms ranked by confidence score using the maintained PhaBOX2 host-prediction workflow</td><td>Understanding host range, therapy targeting</td></tr>
      <tr><td>defense_finder_systems.tsv</td><td>DefenseFinder</td><td>Antidefense systems detected from the genome’s predicted proteins</td><td>Identifying anti-defense loci such as Anti-CBASS or Anti-Dnd</td></tr>
      <tr><td>defense_finder_genes.tsv</td><td>DefenseFinder</td><td>Per-gene DefenseFinder hits, including Anti-CRISPR protein calls when present</td><td>Reviewing individual antidefense proteins</td></tr>
      <tr><td>defense_finder_hmmer.tsv</td><td>DefenseFinder</td><td>Raw HMM profile matches underlying DefenseFinder calls</td><td>Inspecting marginal or low-level hits in more detail</td></tr>
      <tr><td>final_assignments.csv</td><td>vConTACT3</td><td>Full taxonomy assignments at all ranks (realm → genus) for your phage and all reference genomes in the DB</td><td>Taxonomy reporting, phylogenetic context</td></tr>
      <tr><td>performance_metrics.csv</td><td>vConTACT3</td><td>Internal benchmarking metrics (PPV, sensitivity, accuracy) for the clustering run</td><td>Assessing confidence in taxonomy predictions</td></tr>
      <tr><td>part1.cyjs</td><td>vConTACT3</td><td>Protein-sharing network in Cytoscape JSON format. Load via File → Import → Network from File in Cytoscape.</td><td>Interactive network visualisation, cluster exploration</td></tr>
      <tr><td>part1.graphml</td><td>vConTACT3</td><td>Protein-sharing network in GraphML format. Open in Gephi, yEd, or Cytoscape.</td><td>Network analysis, publication-quality figures</td></tr>
      <tr><td>rbp_predictions.csv</td><td>PhageRBPdetect v4</td><td>Per-protein RBP classification scores (0–1) for all predicted proteins</td><td>Identifying receptor-binding proteins</td></tr>
      <tr><td>rbp_candidates.faa</td><td>PhageRBPdetect v4</td><td>Protein sequences of RBP candidates (score ≥ 0.5)</td><td>DepoScope input, structural analysis, cloning targets</td></tr>
      <tr><td>deposcope_results.csv</td><td>DepoScope</td><td>Depolymerase predictions with scores plus derived domain type (β-helix, β-propeller, triple helix) and boundaries</td><td>Identifying polysaccharide-degrading enzymes for biofilm disruption</td></tr>
      <tr><td>deposcope_tokens.tsv</td><td>DepoScope</td><td>Per-amino-acid domain labels used for domain architecture visualisation</td><td>Detailed domain analysis, structural biology</td></tr>
    </tbody>
  </table>
</div>

<div class="card">
  <div class="section-title">📁 NCBI BankIt Submission Files</div>
  <table class="mini-table">
    <thead><tr><th>File</th><th>Description</th><th>How to use</th></tr></thead>
    <tbody>
      <tr><td>bankit_multi.fasta</td><td>Combined multifasta with BankIt-formatted headers: <code>&gt;Seq1 [organism=Genus phage Name]</code></td><td>Upload to NCBI BankIt as the sequence file</td></tr>
      <tr><td>bankit_features.tbl</td><td>5-column feature table matching the multifasta SeqIDs, derived from Pharokka annotations</td><td>Upload to NCBI BankIt alongside the multifasta</td></tr>
    </tbody>
  </table>
  <div style="margin-top:12px;padding:10px;background:#020617;border-radius:6px;font-size:12px;color:#64748b;font-family:monospace">
    Submit at: <span style="color:#60a5fa">https://www.ncbi.nlm.nih.gov/WebSub/?tool=bankit</span>
  </div>
</div>"""

    # ------------------------------------------------------------------ #
    # Assemble full HTML
    # ------------------------------------------------------------------ #
    tabs = [
        ("overview",      "Overview",      overview_tab),
        ("genome",        "Genome",        genome_tab),
        ("therapy",       "Therapy",       therapy_tab),
        ("defence",       "Defence",       defence_tab),
        ("tailfibers",    "Tail Fibers",   tailfibers_tab),
        ("downloads",     "Downloads",     downloads_tab),
        ("supplementary", "Supplementary", supplementary_tab),
    ]

    tab_btns = "".join(
        f'<button class="tab-btn{" active" if i == 0 else ""}" '
        f'id="tab-btn-{tid}" onclick="showTab(\'{tid}\')">{tlabel}</button>'
        for i, (tid, tlabel, _) in enumerate(tabs)
    )
    tab_panes = "".join(
        f'<div class="tab-pane{" active" if i == 0 else ""}" id="tab-{tid}">{tcontent}</div>'
        for i, (tid, _, tcontent) in enumerate(tabs)
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Phage Report Card — {name}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="header">
  <div class="header-inner">
    <div>
      <div class="header-label">Phage Report Card</div>
      <h1 class="header-title">{name}</h1>
      <div class="header-sub">
        <span style="color:#64748b">Organism:</span> {organism_label}
      </div>
    </div>
    <div class="header-badges">{ls_badge} {th_badge}</div>
  </div>
</div>
<div class="tabs"><div class="tabs-inner">{tab_btns}</div></div>
<div class="content">{tab_panes}</div>
<script>{_JS}</script>
</body>
</html>"""

    return html
