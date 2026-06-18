"""
phang CLI — argument parsing entry point.

Usage:
    phang run --input phage.fasta --output ./results
    phang run --input ./my_phages/ --output ./results --threads 8
    phang run --input phage.fasta --output ./results --gpu
"""

import argparse
import logging
import sys
from pathlib import Path

from phang.config import VERSION


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phang",
        description="End-to-end phage genome analysis pipeline.",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"phang {VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ---- gui subcommand ----
    subparsers.add_parser(
        "gui",
        help="Open the Phang graphical interface.",
    )

    # ---- install subcommand ----
    subparsers.add_parser(
        "install",
        help="Install all tools and databases (~/.phang/). Safe to re-run — skips already-installed components.",
    )

    # ---- bootstrap subcommand (first-run orchestrator for installers) ----
    bootstrap_parser = subparsers.add_parser(
        "bootstrap",
        help="First-run setup: verify conda, install all tools + databases, and "
             "record a manifest. Safe to re-run. Used by the installers.",
    )
    bootstrap_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if a previous bootstrap manifest is present.",
    )

    # ---- setup subcommand (creates desktop shortcut) ----
    subparsers.add_parser(
        "setup",
        help="Create a desktop shortcut to launch Phang.",
    )

    # ---- run subcommand ----
    run_parser = subparsers.add_parser(
        "run",
        help="Run the full pipeline on one or more phage genomes.",
    )
    run_parser.add_argument(
        "--input", "-i",
        required=True,
        metavar="PATH",
        help="Single .fasta file, directory of .fasta files, or multi-record .fasta.",
    )
    run_parser.add_argument(
        "--output", "-o",
        default="./phang_output",
        metavar="DIR",
        help="Output root directory (default: ./phang_output).",
    )
    run_parser.add_argument(
        "--threads", "-t",
        type=int,
        default=8,
        metavar="N",
        help="CPU threads for parallelisable tools (default: 8).",
    )

    gpu_group = run_parser.add_mutually_exclusive_group()
    gpu_group.add_argument(
        "--gpu",
        action="store_true",
        help="Force GPU mode (CUDA or MPS).",
    )
    gpu_group.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU-only mode.",
    )

    run_parser.add_argument(
        "--db-dir",
        default=None,
        metavar="DIR",
        help="Custom database directory (default: ~/.phang/databases).",
    )
    run_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing outputs.",
    )
    run_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )

    # ---- report subcommand (rebuild HTML reports without re-running tools) ----
    report_parser = subparsers.add_parser(
        "report",
        help="Rebuild report_card.html files from an existing output directory.",
    )
    report_parser.add_argument(
        "--rebuild",
        required=True,
        metavar="DIR",
        help="Output directory containing per-phage subdirs to re-render.",
    )
    report_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )

    # ---- batch subcommand ----
    batch_parser = subparsers.add_parser(
        "batch",
        help="Run the pipeline on all phages listed in a markdown batch file.",
    )
    batch_parser.add_argument(
        "--list", "-l",
        required=True,
        metavar="FILE",
        dest="list_file",
        help="Markdown file containing the phage batch table.",
    )
    batch_parser.add_argument(
        "--input-dir",
        default=None,
        metavar="DIR",
        help="Directory containing source FASTA files (default: directory of the list file).",
    )
    batch_parser.add_argument(
        "--output", "-o",
        default="~/phang_batch_output",
        metavar="DIR",
        help="Output root directory (default: ~/phang_batch_output).",
    )
    batch_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )
    batch_parser.add_argument(
        "--threads", "-t",
        type=int,
        default=8,
        metavar="N",
        help="CPU threads for parallelisable tools (default: 8).",
    )
    gpu_batch_group = batch_parser.add_mutually_exclusive_group()
    gpu_batch_group.add_argument(
        "--gpu",
        action="store_true",
        help="Force GPU mode (CUDA or MPS).",
    )
    gpu_batch_group.add_argument(
        "--cpu",
        action="store_true",
        help="Force CPU-only mode.",
    )

    return parser


def _setup_logging(verbose: bool, log_file: Path) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%H:%M:%S"

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    # File handler (always DEBUG)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)


def print_batch_summary(results: dict) -> None:
    """Print a human-readable batch summary to stdout."""
    print(
        f"\nBatch complete: {len(results['completed'])} completed, "
        f"{len(results['skipped'])} skipped, {len(results['failed'])} failed"
    )
    if results["completed"]:
        print("  Completed:", ", ".join(results["completed"]))
    if results["skipped"]:
        print("  Skipped:  ", ", ".join(results["skipped"]))
    if results["failed"]:
        print("  Failed:   ", ", ".join(results["failed"]))


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "install":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        from phang.install.manager import ensure_all
        results = ensure_all()  # raises SystemExit on fatal failures
        failed = {k: v for k, v in results.items() if v.startswith("FAILED:")}
        if failed:
            print("\nSome non-fatal tools failed:")
            for tool, msg in failed.items():
                print(f"  {tool}: {msg}")
        else:
            print("\nAll tools installed successfully.")
        return

    if args.command == "bootstrap":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        from phang.install.bootstrap import bootstrap
        manifest = bootstrap(force=args.force)
        tools = manifest.get("tools", {})
        failed = {k: v for k, v in tools.items() if v.get("state") == "failed"}
        if failed:
            print("\nSome non-fatal tools failed:")
            for tool, info in failed.items():
                print(f"  {tool}: {info.get('message', '')}")
        else:
            print("\nphang bootstrap complete — all tools ready.")
        return

    if args.command == "gui":
        from phang.gui.app import launch
        launch()
        return

    if args.command == "setup":
        from phang.gui.shortcut import create_desktop_shortcut
        try:
            path = create_desktop_shortcut()
            print(f"✅  Desktop shortcut created: {path}")
            print("    Double-click it to launch Phang.")
        except Exception as exc:
            print(f"❌  Failed to create shortcut: {exc}")
            sys.exit(1)
        return

    if args.command == "run":
        input_path = Path(args.input).expanduser().resolve()
        output_path = Path(args.output).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)

        _setup_logging(
            verbose=args.verbose,
            log_file=output_path / "phang_run.log",
        )

        logger = logging.getLogger(__name__)
        logger.info("phang %s", VERSION)
        logger.info("Input:   %s", input_path)
        logger.info("Output:  %s", output_path)
        logger.info("Threads: %s", args.threads)

        # Resolve GPU mode
        if args.gpu:
            gpu_mode = "force_gpu"
        elif args.cpu:
            gpu_mode = "cpu"
        else:
            gpu_mode = "auto"
        logger.info("GPU mode: %s", gpu_mode)

        # Override db dir if specified
        if args.db_dir:
            from phang import config
            config.DB_DIR = Path(args.db_dir).expanduser().resolve()
            logger.info("DB dir: %s", config.DB_DIR)

        # Validate input path exists
        if not input_path.exists():
            logger.error("Input path does not exist: %s", input_path)
            sys.exit(1)

        # Run pipeline
        from phang.pipeline import run_pipeline
        run_pipeline(
            input_path=input_path,
            output_path=output_path,
            threads=args.threads,
            gpu_mode=gpu_mode,
            force=args.force,
        )

    if args.command == "report":
        output_dir = Path(args.rebuild).expanduser().resolve()
        if not output_dir.exists():
            print(f"❌  Output directory not found: {output_dir}")
            sys.exit(1)

        level = logging.DEBUG if args.verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )

        from phang.report.rebuild import rebuild_reports
        ok = rebuild_reports(output_dir)
        sys.exit(0 if ok > 0 else 1)

    if args.command == "batch":
        list_file = Path(args.list_file).expanduser().resolve()
        if not list_file.exists():
            print(f"Error: List file not found: {list_file}", file=sys.stderr)
            sys.exit(1)

        # CLI-02: --input-dir defaults to directory containing the list file
        if args.input_dir is not None:
            input_dir = Path(args.input_dir).expanduser().resolve()
        else:
            input_dir = list_file.parent

        # CLI-03: --output defaults to ~/phang_batch_output
        output_root = Path(args.output).expanduser().resolve()
        output_root.mkdir(parents=True, exist_ok=True)

        _setup_logging(
            verbose=args.verbose,
            log_file=output_root / "phang_batch.log",
        )

        logger = logging.getLogger(__name__)
        logger.info("phang batch %s", VERSION)
        logger.info("List file:  %s", list_file)
        logger.info("Input dir:  %s", input_dir)
        logger.info("Output:     %s", output_root)

        # Resolve GPU mode
        if args.gpu:
            gpu_mode = "force_gpu"
        elif args.cpu:
            gpu_mode = "cpu"
        else:
            gpu_mode = "auto"

        from phang.batch.runner import run_batch
        results = run_batch(
            list_file=list_file,
            input_dir=input_dir,
            output_root=output_root,
            verbose=args.verbose,
            threads=args.threads,
            gpu_mode=gpu_mode,
        )

        # Print summary
        logger.info(
            "Batch complete: %d completed, %d skipped, %d failed",
            len(results["completed"]),
            len(results["skipped"]),
            len(results["failed"]),
        )
        print_batch_summary(results)


if __name__ == "__main__":
    main()
