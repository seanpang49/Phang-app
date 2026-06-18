"""
Step 7: PhageRBPdetect v4 — receptor-binding protein identification.

Uses a finetuned ESM-2 model (Zenodo: https://zenodo.org/records/14810759) to
classify each predicted protein as RBP or non-RBP.

Input  : pharokka.faa (all predicted proteins)
Outputs:
    rbp_predictions.csv   — per-protein RBP score (all proteins)
    rbp_candidates.faa    — filtered proteins with RBP score ≥ 0.5
                            → consumed by Step 8 (DepoScope)

Both outputs consumed by Report Card (Tail Fibers tab).
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from phang.config import ENV_RBPDETECT
from phang.install.common import find_conda
from phang.install.rbpdetect import get_rbpdetect_model_dir, get_rbpdetect_script
from phang.utils.process import run_streaming

logger = logging.getLogger(__name__)

_RBP_SCORE_THRESHOLD = 0.5


def _find_rbpdetect_script() -> Optional[Path]:
    """Locate the PhageRBPdetect_v4_inference.py script."""
    try:
        return get_rbpdetect_script()
    except Exception:
        return None


def _outputs_present(outdir: Path) -> bool:
    return (outdir / "rbp_predictions.csv").exists()


def _filter_rbp_candidates(predictions_csv: Path, faa_path: Path, out_faa: Path) -> int:
    """
    Write a FAA file containing only proteins with RBP score ≥ threshold.

    Returns the number of candidate proteins written.
    """
    # Parse predictions CSV: expect columns protein_id, rbp_score (or similar)
    high_score_ids: set = set()
    try:
        with open(predictions_csv, encoding="utf-8") as fh:
            header = fh.readline().strip().split(",")
            # Try to find score column: rbp_score, score, probability, pred_score
            score_col = None
            id_col = 0
            for i, col in enumerate(header):
                col_lower = col.lower()
                if "score" in col_lower or "prob" in col_lower:
                    score_col = i
                if col_lower in ("protein_id", "id", "name", "header"):
                    id_col = i

            if score_col is None:
                logger.warning("Cannot identify score column in %s — keeping all proteins.", predictions_csv.name)
                # Fall back: copy all proteins
                shutil.copy2(faa_path, out_faa)
                return _count_faa_records(faa_path)

            for line in fh:
                parts = line.strip().split(",")
                if len(parts) <= max(id_col, score_col):
                    continue
                try:
                    score = float(parts[score_col])
                    if score >= _RBP_SCORE_THRESHOLD:
                        high_score_ids.add(parts[id_col].strip())
                except ValueError:
                    continue
    except OSError as exc:
        logger.error("Cannot read predictions CSV %s: %s", predictions_csv, exc)
        return 0

    # Write filtered FAA
    count = 0
    current_id: Optional[str] = None
    keep = False
    out_faa.parent.mkdir(parents=True, exist_ok=True)

    with open(faa_path, encoding="utf-8") as src, open(out_faa, "w", encoding="utf-8") as dst:
        for line in src:
            if line.startswith(">"):
                current_id = line[1:].split()[0]
                keep = current_id in high_score_ids
                if keep:
                    dst.write(line)
                    count += 1
            elif keep:
                dst.write(line)

    return count


def _count_faa_records(faa_path: Path) -> int:
    count = 0
    with open(faa_path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith(">"):
                count += 1
    return count


def _filter_ffn_by_faa_ids(candidates_faa: Path, ffn_path: Path, out_ffn: Path) -> None:
    """
    Write a FFN file containing only the nucleotide sequences for proteins
    listed in candidates_faa.  DepoScope requires nucleotide input (it runs
    phanotate internally); the protein FAA alone is not accepted.
    """
    candidate_ids: set = set()
    if candidates_faa.exists():
        with open(candidates_faa, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith(">"):
                    candidate_ids.add(line[1:].split()[0].strip())

    if not candidate_ids or not ffn_path.exists():
        return

    out_ffn.parent.mkdir(parents=True, exist_ok=True)
    with open(ffn_path, encoding="utf-8") as src, open(out_ffn, "w", encoding="utf-8") as dst:
        keep = False
        for line in src:
            if line.startswith(">"):
                seq_id = line[1:].split()[0]
                keep = seq_id in candidate_ids
                if keep:
                    dst.write(line)
            elif keep:
                dst.write(line)


def _read_faa_lengths(faa_path: Path) -> Dict[str, int]:
    lengths: Dict[str, int] = {}
    current_id: Optional[str] = None
    current_len = 0
    with open(faa_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if current_id is not None:
                    lengths[current_id] = current_len
                current_id = line[1:].split()[0]
                current_len = 0
            else:
                current_len += len(line)
    if current_id is not None:
        lengths[current_id] = current_len
    return lengths


def _normalise_predictions(raw_csv: Path, faa: Path, out_csv: Path) -> None:
    lengths = _read_faa_lengths(faa)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    with open(raw_csv, encoding="utf-8") as src, open(out_csv, "w", encoding="utf-8", newline="") as dst:
        reader = csv.DictReader(src)
        fieldnames = ["protein_id", "length", "rbp_score", "prediction"]
        writer = csv.DictWriter(dst, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            protein_id = (row.get("protein_name") or "").strip()
            if not protein_id:
                continue
            pred_raw = str(row.get("preds", "")).strip()
            prediction = "RBP" if pred_raw == "1" else "non-RBP"
            writer.writerow(
                {
                    "protein_id": protein_id,
                    "length": lengths.get(protein_id, ""),
                    "rbp_score": row.get("score", ""),
                    "prediction": prediction,
                }
            )


def _run_single(
    conda: str,
    script: Path,
    model_dir: Path,
    faa: Path,
    outdir: Path,
    gpu: str,
    force: bool,
    log_path: Path,
) -> bool:
    """Run PhageRBPdetect on one FAA. Returns True on success."""
    if outdir.exists() and force:
        shutil.rmtree(outdir)

    outdir.mkdir(parents=True, exist_ok=True)

    if not force and _outputs_present(outdir):
        logger.info("  [SKIP] %s — rbpdetect outputs already present.", faa.parent.parent.name)
        return True

    device = gpu if gpu in {"cpu", "cuda", "mps"} else "cpu"
    cmd = [
        conda, "run", "--no-capture-output", "-p", str(ENV_RBPDETECT),
        "python", str(script),
        "--input", str(faa),
        "--output", str(outdir),
        "--model", str(model_dir),
        "--device", device,
    ]

    rc = run_streaming(cmd, log_path=log_path)
    if rc != 0:
        return False

    raw_predictions = outdir / "predictions.csv"
    if not raw_predictions.exists():
        logger.error("PhageRBPdetect completed without writing %s", raw_predictions)
        return False

    _normalise_predictions(raw_predictions, faa, outdir / "rbp_predictions.csv")
    return True


def run_rbpdetect(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 7 entry point.

    Reads from ctx : results[stem].pharokka_faa, output_path, gpu, force
    Writes to ctx['results'][stem] : rbpdetect_dir, rbp_predictions, rbp_candidates_faa
    """
    output_path: Path = ctx["output_path"]
    gpu: str = ctx["gpu"]
    force: bool = ctx["force"]

    conda = find_conda()
    tool_status = ctx.get("tool_status", {})
    install_status = str(tool_status.get("rbpdetect", ""))
    install_error = install_status.removeprefix("FAILED:").strip() if install_status.startswith("FAILED:") else ""
    script: Optional[Path] = None  # resolved lazily
    model_dir: Optional[Path] = None
    ok = 0

    for stem, per in ctx["results"].items():
        faa: Path = per.get("pharokka_faa")  # type: ignore[assignment]
        if not faa or not faa.exists():
            logger.warning("  [SKIP] %s — pharokka.faa not found.", stem)
            continue

        outdir = output_path / stem / "rbpdetect"
        log_path = output_path / "_logs" / f"{stem}.rbpdetect.log"

        if not force and _outputs_present(outdir):
            logger.info("  [SKIP] %s — rbpdetect outputs already present.", stem)
            ok += 1
            predictions_csv = outdir / "rbp_predictions.csv"
            candidates_faa = outdir / "rbp_candidates.faa"
            candidates_ffn = outdir / "rbp_candidates.ffn"
            per["rbpdetect_dir"]      = outdir
            per["rbp_predictions"]    = predictions_csv
            per["rbp_candidates_faa"] = candidates_faa
            per["rbp_candidates_ffn"] = candidates_ffn
            continue

        if script is None:
            try:
                script = _find_rbpdetect_script()
                model_dir = get_rbpdetect_model_dir()
            except RuntimeError as exc:
                detail = install_error or str(exc)
                logger.error(
                    "PhageRBPdetect is not runnable for this step: %s",
                    detail,
                )
                break
            if script is None or model_dir is None:
                logger.error("PhageRBPdetect assets are unavailable for this step.")
                break

        logger.info("  PhageRBPdetect ← %s", faa.name)

        success = _run_single(
            conda=conda,
            script=script,
            model_dir=model_dir,
            faa=faa,
            outdir=outdir,
            gpu=gpu,
            force=force,
            log_path=log_path,
        )

        if success:
            ok += 1
            predictions_csv = outdir / "rbp_predictions.csv"
            candidates_faa = outdir / "rbp_candidates.faa"
            candidates_ffn = outdir / "rbp_candidates.ffn"

            n_candidates = _filter_rbp_candidates(predictions_csv, faa, candidates_faa)
            logger.info(
                "  RBP candidates (score ≥ %.1f): %d", _RBP_SCORE_THRESHOLD, n_candidates
            )

            # Also extract nucleotide sequences for DepoScope (which runs phanotate internally)
            pharokka_ffn: Optional[Path] = per.get("pharokka_ffn")  # type: ignore[assignment]
            if pharokka_ffn and pharokka_ffn.exists():
                _filter_ffn_by_faa_ids(candidates_faa, pharokka_ffn, candidates_ffn)

            per["rbpdetect_dir"]      = outdir
            per["rbp_predictions"]    = predictions_csv
            per["rbp_candidates_faa"] = candidates_faa
            per["rbp_candidates_ffn"] = candidates_ffn
        else:
            logger.error("  [FAIL] PhageRBPdetect failed for %s", stem)

    logger.info("PhageRBPdetect: %d/%d succeeded", ok, len(ctx["results"]))
    return ctx
