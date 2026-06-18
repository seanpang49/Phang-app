"""
Step 8: DepoScope — depolymerase detection within RBP candidates.

Uses a finetuned ESM-2 + CNN model (Zenodo: https://zenodo.org/records/10957073).
Only runs on the filtered RBP candidates from Step 7 (score ≥ 0.5).

Input  : rbp_candidates.faa (from Step 7)
Outputs (in <output>/<phage>/deposcope/):
    deposcope_results.csv   — per-protein: depolymerase score, is_depolymerase,
                              domain fold type, domain start/end
    deposcope_tokens.tsv    — per-amino-acid token labels (for domain viz)

Both consumed by Report Card (Tail Fibers tab).
"""

from __future__ import annotations

import ast
import logging
import csv
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

from phang.config import ENV_DEPOSCOPE, ENV_PHANOTATE, PHANG_HOME
from phang.install.common import find_conda
from phang.install.deposcope import get_deposcope_model_paths
from phang.utils.process import run_streaming

logger = logging.getLogger(__name__)

_DEPOSCOPE_SCRIPT_DIR = PHANG_HOME / "tools" / "deposcope"
_DEPOSCOPE_DOMAIN_LABELS = {
    1: "beta-helix",
    2: "beta-propeller",
    3: "triple-helix",
}


def _find_deposcope_script() -> Optional[Path]:
    """Locate the deposcope-predict.py (or equivalent) script."""
    candidates = [
        _DEPOSCOPE_SCRIPT_DIR / "deposcope-predict.py",
        _DEPOSCOPE_SCRIPT_DIR / "predict.py",
        _DEPOSCOPE_SCRIPT_DIR / "deposcope_predict.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    for p in _DEPOSCOPE_SCRIPT_DIR.rglob("*predict*.py"):
        return p
    return None


def _outputs_present(outdir: Path) -> bool:
    # DepoScope writes a single CSV file; accept either extension
    return (outdir / "deposcope_results.csv").exists() or (outdir / "deposcope_results.tsv").exists()


def _run_single(
    conda: str,
    script: Path,
    esm2_dir: Path,
    dpo_model: Path,
    faa: Path,
    outdir: Path,
    gpu: str,
    force: bool,
    log_path: Path,
) -> bool:
    """Run DepoScope on one RBP candidates FFN. Returns True on success."""
    if outdir.exists() and force:
        shutil.rmtree(outdir)

    outdir.mkdir(parents=True, exist_ok=True)

    if not force and _outputs_present(outdir):
        logger.info("  [SKIP] %s — deposcope outputs already present.", faa.parent.parent.name)
        return True

    # DepoScope's -o flag takes a FILE path, not a directory
    out_csv = outdir / "deposcope_results.csv"

    cmd = [
        conda, "run", "--no-capture-output", "-p", str(ENV_DEPOSCOPE),
        "python", str(script),
        "-i", str(faa),
        "-o", str(out_csv),
        "--esm2", str(esm2_dir),
        "--Dpo", str(dpo_model),
    ]

    # DepoScope does not accept a --device flag; it auto-detects GPU

    # Put the dedicated phanotate env on PATH so the vendored predict script's
    # `subprocess.run(["phanotate.py", ...])` resolves a working (native-arch)
    # phanotate. The deposcope env deliberately ships none, so this is what it
    # finds. `conda run` prepends the deposcope env bin, but phanotate isn't
    # there, so resolution falls through to this entry.
    run_env = os.environ.copy()
    run_env["PATH"] = str(ENV_PHANOTATE / "bin") + os.pathsep + run_env.get("PATH", "")

    rc = run_streaming(cmd, log_path=log_path, env=run_env)
    return rc == 0


def _iter_fasta_records(path: Path):
    header = None
    seq_lines = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(seq_lines)
                header = line[1:].strip()
                seq_lines = []
            else:
                seq_lines.append(line)
    if header is not None:
        yield header, "".join(seq_lines)


def _normalise_results(raw_csv: Path, protein_id: str) -> tuple[dict, list[dict]]:
    rows = []
    with open(raw_csv, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return (
            {
                "protein_id": protein_id,
                "dep_score": 0.0,
                "is_depolymerase": False,
                "domain_type": "",
                "domain_start": "",
                "domain_end": "",
            },
            [],
        )

    best = max(rows, key=lambda row: float(row.get("scores_DepoScope", 0) or 0))
    best_score = float(best.get("scores_DepoScope", 0) or 0)
    token_labels_raw = best.get("token_labels", "")
    protein_length = len(best.get("protein_sequence", "") or "")
    try:
        token_labels = ast.literal_eval(token_labels_raw) if token_labels_raw else []
    except (SyntaxError, ValueError):
        token_labels = []

    normalized_labels = []
    for value in token_labels[:protein_length or None]:
        try:
            normalized_labels.append(int(float(value)))
        except (TypeError, ValueError):
            continue

    non_zero = [label for label in normalized_labels if label > 0]
    domain_type = ""
    domain_start = ""
    domain_end = ""
    if non_zero:
        dominant_label = Counter(non_zero).most_common(1)[0][0]
        positions = [idx + 1 for idx, label in enumerate(normalized_labels) if label == dominant_label]
        if positions:
            domain_type = _DEPOSCOPE_DOMAIN_LABELS.get(dominant_label, f"Domain {dominant_label}")
            domain_start = str(positions[0])
            domain_end = str(positions[-1])

    result_row = {
        "protein_id": protein_id,
        "dep_score": round(best_score, 6),
        "is_depolymerase": best_score >= 0.5,
        "domain_type": domain_type,
        "domain_start": domain_start,
        "domain_end": domain_end,
    }
    token_rows = [
        {
            "protein_id": protein_id,
            "gene_id": row.get("gene_ID", ""),
            "token_labels": row.get("token_labels", ""),
        }
        for row in rows
    ]
    return result_row, token_rows


def run_deposcope(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 8 entry point.

    Reads from ctx : results[stem].rbp_candidates_faa, output_path, gpu, force
    Writes to ctx['results'][stem] : deposcope_dir, deposcope_results, deposcope_tokens
    """
    output_path: Path = ctx["output_path"]
    gpu: str = ctx["gpu"]
    force: bool = ctx["force"]

    conda = find_conda()
    tool_status = ctx.get("tool_status", {})
    install_status = str(tool_status.get("deposcope", ""))
    install_error = install_status.removeprefix("FAILED:").strip() if install_status.startswith("FAILED:") else ""
    script = _find_deposcope_script()
    esm2_dir: Optional[Path] = None
    dpo_model: Optional[Path] = None

    if script is None:
        logger.error(
            "DepoScope predict script not found. "
            "Install DepoScope and ensure the script is at %s",
            _DEPOSCOPE_SCRIPT_DIR,
        )
        return ctx

    ok = 0
    skipped = 0

    for stem, per in ctx["results"].items():
        # DepoScope requires nucleotide input (it runs phanotate internally).
        # Use the nucleotide FFN extracted for RBP candidates; fall back to
        # checking FAA only to decide whether to skip.
        candidates_ffn: Path = per.get("rbp_candidates_ffn")  # type: ignore[assignment]
        candidates_faa: Path = per.get("rbp_candidates_faa")  # type: ignore[assignment]

        if not candidates_faa or not candidates_faa.exists():
            reason = "Step 8 did not produce RBP candidates"
            if install_error:
                reason += f"; DepoScope installer status: {install_error}"
            logger.info("  [SKIP] %s — no RBP candidates FAA (%s).", stem, reason)
            skipped += 1
            continue

        # Skip if the candidates file is empty (no RBPs found)
        with open(candidates_faa, encoding="utf-8") as fh:
            has_content = any(l.startswith(">") for l in fh)
        if not has_content:
            logger.info("  [SKIP] %s — no RBP candidates to run DepoScope on.", stem)
            skipped += 1
            continue

        if not candidates_ffn or not candidates_ffn.exists():
            logger.warning(
                "  [SKIP] %s — no RBP candidates FFN (nucleotide sequences needed by DepoScope).",
                stem,
            )
            skipped += 1
            continue

        if esm2_dir is None or dpo_model is None:
            try:
                esm2_dir, dpo_model = get_deposcope_model_paths()
            except RuntimeError as exc:
                detail = install_error or str(exc)
                logger.error("DepoScope is not runnable for this step: %s", detail)
                break

        outdir = output_path / stem / "deposcope"
        log_path = output_path / "_logs" / f"{stem}.deposcope.log"

        if not force and _outputs_present(outdir):
            logger.info("  [SKIP] %s — deposcope outputs already present.", stem)
            per["deposcope_dir"] = outdir
            per["deposcope_results"] = outdir / "deposcope_results.csv"
            per["deposcope_tokens"] = outdir / "deposcope_tokens.tsv"
            ok += 1
            continue

        logger.info("  DepoScope ← %s", candidates_ffn.name)

        success = True
        results_rows = []
        token_rows = []
        with tempfile.TemporaryDirectory(prefix=f"{stem}.deposcope.") as tmp_dir:
            tmp_root = Path(tmp_dir)
            for idx, (header, sequence) in enumerate(_iter_fasta_records(candidates_ffn), start=1):
                protein_id = header.split()[0]
                single_fasta = tmp_root / f"{idx:04d}_{protein_id}.fasta"
                raw_csv = tmp_root / f"{idx:04d}_{protein_id}.csv"
                single_fasta.write_text(f">{protein_id}\n{sequence}\n", encoding="utf-8")

                item_log = output_path / "_logs" / f"{stem}.deposcope.{idx:04d}.log"
                item_ok = _run_single(
                    conda=conda,
                    script=script,
                    esm2_dir=esm2_dir,
                    dpo_model=dpo_model,
                    faa=single_fasta,
                    outdir=tmp_root / f"run_{idx:04d}",
                    gpu=gpu,
                    force=True,
                    log_path=item_log,
                )
                generated_csv = tmp_root / f"run_{idx:04d}" / "deposcope_results.csv"
                if not item_ok or not generated_csv.exists():
                    success = False
                    logger.error("  [FAIL] DepoScope failed for candidate %s", protein_id)
                    continue
                result_row, item_tokens = _normalise_results(generated_csv, protein_id)
                results_rows.append(result_row)
                token_rows.extend(item_tokens)

        if success:
            ok += 1
            results_csv = outdir / "deposcope_results.csv"
            tokens_tsv = outdir / "deposcope_tokens.tsv"
            outdir.mkdir(parents=True, exist_ok=True)
            with open(results_csv, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=[
                        "protein_id",
                        "dep_score",
                        "is_depolymerase",
                        "domain_type",
                        "domain_start",
                        "domain_end",
                    ],
                )
                writer.writeheader()
                writer.writerows(results_rows)
            with open(tokens_tsv, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=["protein_id", "gene_id", "token_labels"],
                    delimiter="\t",
                )
                writer.writeheader()
                writer.writerows(token_rows)
            per["deposcope_dir"]     = outdir
            per["deposcope_results"] = results_csv
            per["deposcope_tokens"]  = tokens_tsv
        else:
            logger.error("  [FAIL] DepoScope failed for %s", stem)

    total = len(ctx["results"])
    logger.info("DepoScope: %d succeeded, %d skipped (no RBP candidates), %d failed",
                ok, skipped, total - ok - skipped)
    return ctx
