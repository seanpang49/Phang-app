"""
Step 7: DefenseFinder — antidefense system detection.

Uses DefenseFinder's AntiDefenseFinder mode on the Pharokka protein FASTA to
detect anti-CRISPR and other antidefense systems.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from phang.config import DB_DEFENSEFINDER_MODELS, ENV_DEFENSEFINDER
from phang.install.common import find_conda
from phang.utils.process import run_streaming

logger = logging.getLogger(__name__)

_SYSTEMS_NAME = "defense_finder_systems.tsv"
_GENES_NAME = "defense_finder_genes.tsv"
_HMMER_NAME = "defense_finder_hmmer.tsv"


def _outputs_present(outdir: Path) -> bool:
    return all((outdir / name).exists() for name in (_SYSTEMS_NAME, _GENES_NAME, _HMMER_NAME))


def _find_named_output(outdir: Path, suffix: str) -> Optional[Path]:
    stable = outdir / suffix
    if stable.exists():
        return stable
    matches = sorted(outdir.glob(f"*_defense_finder_{suffix.removeprefix('defense_finder_')}"))
    return matches[0] if matches else None


def _normalise_outputs(raw_outdir: Path, final_outdir: Path) -> bool:
    final_outdir.mkdir(parents=True, exist_ok=True)
    mapping = {
        _SYSTEMS_NAME: _find_named_output(raw_outdir, _SYSTEMS_NAME),
        _GENES_NAME: _find_named_output(raw_outdir, _GENES_NAME),
        _HMMER_NAME: _find_named_output(raw_outdir, _HMMER_NAME),
    }
    if not all(mapping.values()):
        return False
    for name, src in mapping.items():
        assert src is not None
        shutil.copy2(src, final_outdir / name)
    return True


def _run_single(
    conda: str,
    faa: Path,
    outdir: Path,
    threads: int,
    force: bool,
    log_path: Path,
) -> bool:
    """Run DefenseFinder on one FAA. Returns True on success."""
    if outdir.exists() and force:
        shutil.rmtree(outdir)

    outdir.mkdir(parents=True, exist_ok=True)

    if not force and _outputs_present(outdir):
        logger.info("  [SKIP] %s — DefenseFinder outputs already present.", faa.parent.parent.name)
        return True

    def _build_cmd(input_faa: Path, output_dir: Path) -> list[str]:
        return [
            conda,
            "run",
            "--no-capture-output",
            "-p",
            str(ENV_DEFENSEFINDER),
            "defense-finder",
            "run",
            "-A",
            "--skip-model-version-check",
            "--models-dir",
            str(DB_DEFENSEFINDER_MODELS),
            "-w",
            str(max(1, threads)),
            "-o",
            str(output_dir),
            str(input_faa),
        ]

    needs_safe_workspace = " " in str(faa) or " " in str(outdir)
    if needs_safe_workspace:
        with tempfile.TemporaryDirectory(prefix="phang-defensefinder-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            safe_faa = tmp_root / faa.name.replace(" ", "_")
            safe_outdir = tmp_root / "defensefinder_out"
            shutil.copy2(faa, safe_faa)

            rc = run_streaming(_build_cmd(safe_faa, safe_outdir), log_path=log_path)
            if rc != 0:
                return False
            return _normalise_outputs(safe_outdir, outdir)

    rc = run_streaming(_build_cmd(faa, outdir), log_path=log_path)
    if rc != 0:
        return False
    return _normalise_outputs(outdir, outdir)


def run_defensefinder(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """
    Step 7 entry point.

    Reads from ctx : results[stem].pharokka_faa, output_path, force, threads
    Writes to ctx['results'][stem] : defensefinder_dir, defensefinder_systems,
    defensefinder_genes, defensefinder_hmmer
    """
    output_path: Path = ctx["output_path"]
    force: bool = ctx["force"]
    threads: int = ctx.get("threads", 1)

    conda = find_conda()
    ok = 0

    for stem, per in ctx["results"].items():
        faa: Optional[Path] = per.get("pharokka_faa")
        if not faa or not faa.exists():
            logger.warning("  [SKIP] %s — Pharokka FAA not found.", stem)
            continue

        outdir = output_path / stem / "defensefinder"
        log_path = output_path / "_logs" / f"{stem}.defensefinder.log"

        if not force and _outputs_present(outdir):
            logger.info("  [SKIP] %s — DefenseFinder outputs already present.", stem)
            ok += 1
            per["defensefinder_dir"] = outdir
            per["defensefinder_systems"] = outdir / _SYSTEMS_NAME
            per["defensefinder_genes"] = outdir / _GENES_NAME
            per["defensefinder_hmmer"] = outdir / _HMMER_NAME
            continue

        logger.info("  DefenseFinder ← %s", faa.name)
        success = _run_single(
            conda=conda,
            faa=faa,
            outdir=outdir,
            threads=threads,
            force=force,
            log_path=log_path,
        )
        if success:
            ok += 1
            per["defensefinder_dir"] = outdir
            per["defensefinder_systems"] = outdir / _SYSTEMS_NAME
            per["defensefinder_genes"] = outdir / _GENES_NAME
            per["defensefinder_hmmer"] = outdir / _HMMER_NAME
        else:
            logger.error("  [FAIL] DefenseFinder failed for %s", stem)

    logger.info("DefenseFinder: %d/%d succeeded", ok, len(ctx["results"]))
    return ctx
