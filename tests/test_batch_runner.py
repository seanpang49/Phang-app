"""Unit tests for the batch runner module (phang/batch/runner.py).

Tests cover:
- run_pipeline called once per parsed entry with correct input/output paths
- Phages with existing output directories are skipped
- A failed phage run does not abort the batch (fault tolerance)
- FASTA paths resolved relative to input_dir
- Verbose flag passes through correctly
- Progress lines printed to stdout ([N/Total] Running <name>...)
- End-of-batch summary via print_batch_summary()
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from phang.batch.parser import PhageEntry
from phang.batch.runner import run_batch
from phang.cli import print_batch_summary


@patch("phang.batch.runner.run_pipeline")
@patch("phang.batch.runner.parse_batch_list")
def test_runs_pipeline_for_each_entry(mock_parse, mock_pipeline):
    """run_batch calls run_pipeline once per parsed entry with correct paths."""
    mock_parse.return_value = [
        PhageEntry("A", "a.fasta"),
        PhageEntry("B", "b.fasta"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        result = run_batch(
            list_file=Path("fake.md"),
            input_dir=Path("/src"),
            output_root=tmppath,
            verbose=False,
        )

    assert mock_pipeline.call_count == 2

    first_call = mock_pipeline.call_args_list[0]
    assert first_call.kwargs["input_path"] == Path("/src/a.fasta")
    assert first_call.kwargs["output_path"].name == "A"

    second_call = mock_pipeline.call_args_list[1]
    assert second_call.kwargs["input_path"] == Path("/src/b.fasta")
    assert second_call.kwargs["output_path"].name == "B"

    assert result["completed"] == ["A", "B"]
    assert result["skipped"] == []
    assert result["failed"] == []


@patch("phang.batch.runner.run_pipeline")
@patch("phang.batch.runner.parse_batch_list")
def test_skips_existing_output_dir(mock_parse, mock_pipeline):
    """When an output directory already exists for a phage, it is skipped."""
    mock_parse.return_value = [
        PhageEntry("A", "a.fasta"),
        PhageEntry("B", "b.fasta"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        # Pre-create the output dir for "A"
        (tmppath / "A").mkdir()

        result = run_batch(
            list_file=Path("fake.md"),
            input_dir=Path("/src"),
            output_root=tmppath,
            verbose=False,
        )

    # Only B should have been run
    assert mock_pipeline.call_count == 1
    assert mock_pipeline.call_args.kwargs["input_path"] == Path("/src/b.fasta")

    assert result["skipped"] == ["A"]
    assert result["completed"] == ["B"]
    assert result["failed"] == []


@patch("phang.batch.runner.run_pipeline")
@patch("phang.batch.runner.parse_batch_list")
def test_continues_after_failure(mock_parse, mock_pipeline):
    """A pipeline failure for one phage does not abort the rest of the batch."""
    mock_parse.return_value = [
        PhageEntry("A", "a.fasta"),
        PhageEntry("B", "b.fasta"),
        PhageEntry("C", "c.fasta"),
    ]
    # A fails; B and C succeed
    mock_pipeline.side_effect = [Exception("boom"), None, None]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_batch(
            list_file=Path("fake.md"),
            input_dir=Path("/src"),
            output_root=Path(tmpdir),
            verbose=False,
        )

    # All three were attempted
    assert mock_pipeline.call_count == 3

    assert result["failed"] == ["A"]
    assert result["completed"] == ["B", "C"]
    assert result["skipped"] == []


@patch("phang.batch.runner.run_pipeline")
@patch("phang.batch.runner.parse_batch_list")
def test_resolves_fasta_relative_to_input_dir(mock_parse, mock_pipeline):
    """FASTA paths in entries are resolved relative to input_dir."""
    mock_parse.return_value = [
        PhageEntry("X", "sub/dir/x.fasta"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        run_batch(
            list_file=Path("fake.md"),
            input_dir=Path("/data/phages"),
            output_root=Path(tmpdir),
            verbose=False,
        )

    assert mock_pipeline.call_count == 1
    assert mock_pipeline.call_args.kwargs["input_path"] == Path(
        "/data/phages/sub/dir/x.fasta"
    )


@patch("phang.batch.runner.run_pipeline")
@patch("phang.batch.runner.parse_batch_list")
def test_verbose_passes_through(mock_parse, mock_pipeline):
    """Verbose flag is accepted without error; run_pipeline still called."""
    mock_parse.return_value = [PhageEntry("A", "a.fasta")]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_batch(
            list_file=Path("fake.md"),
            input_dir=Path("/src"),
            output_root=Path(tmpdir),
            verbose=True,
        )

    assert mock_pipeline.call_count == 1
    assert result["completed"] == ["A"]


# ---------------------------------------------------------------------------
# Task 1: Progress line tests
# ---------------------------------------------------------------------------


@patch("phang.batch.runner.run_pipeline")
@patch("phang.batch.runner.parse_batch_list")
def test_progress_line_printed_before_run(mock_parse, mock_pipeline, capsys):
    """When 2 phages are queued and neither is skipped, stdout contains [1/2] and [2/2] lines."""
    mock_parse.return_value = [
        PhageEntry("A", "a.fasta"),
        PhageEntry("B", "b.fasta"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        run_batch(
            list_file=Path("fake.md"),
            input_dir=Path("/src"),
            output_root=Path(tmpdir),
            verbose=False,
        )

    captured = capsys.readouterr()
    assert "[1/2] Running A..." in captured.out
    assert "[2/2] Running B..." in captured.out


@patch("phang.batch.runner.run_pipeline")
@patch("phang.batch.runner.parse_batch_list")
def test_progress_line_not_printed_for_skipped(mock_parse, mock_pipeline, capsys):
    """When phage A has an existing output dir (skipped) and B runs, stdout contains B but NOT A."""
    mock_parse.return_value = [
        PhageEntry("A", "a.fasta"),
        PhageEntry("B", "b.fasta"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        # Pre-create the output dir for "A" so it gets skipped
        (tmppath / "A").mkdir()

        run_batch(
            list_file=Path("fake.md"),
            input_dir=Path("/src"),
            output_root=tmppath,
            verbose=False,
        )

    captured = capsys.readouterr()
    assert "[2/2] Running B..." in captured.out
    assert "Running A" not in captured.out


@patch("phang.batch.runner.run_pipeline")
@patch("phang.batch.runner.parse_batch_list")
def test_progress_line_index_is_queue_position(mock_parse, mock_pipeline, capsys):
    """When phage 1 is skipped and phage 2 runs, the progress shows [2/2] not [1/1]."""
    mock_parse.return_value = [
        PhageEntry("A", "a.fasta"),
        PhageEntry("B", "b.fasta"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        # Pre-create output dir for "A" so it is skipped
        (tmppath / "A").mkdir()

        run_batch(
            list_file=Path("fake.md"),
            input_dir=Path("/src"),
            output_root=tmppath,
            verbose=False,
        )

    captured = capsys.readouterr()
    assert "[2/2] Running B..." in captured.out
    assert "[1/1]" not in captured.out


# ---------------------------------------------------------------------------
# Task 2: Batch summary tests
# ---------------------------------------------------------------------------


def test_summary_printed_with_counts_and_names(capsys):
    """print_batch_summary prints counts line and name lines for all non-empty categories."""
    print_batch_summary({"completed": ["A", "B"], "skipped": ["C"], "failed": ["D"]})
    captured = capsys.readouterr()
    assert "Batch complete: 2 completed, 1 skipped, 1 failed" in captured.out
    assert "Completed:" in captured.out and "A, B" in captured.out
    assert "Skipped:" in captured.out and "C" in captured.out
    assert "Failed:" in captured.out and "D" in captured.out


def test_summary_omits_empty_categories(capsys):
    """print_batch_summary omits Skipped/Failed lines when those lists are empty."""
    print_batch_summary({"completed": ["A"], "skipped": [], "failed": []})
    captured = capsys.readouterr()
    assert "Batch complete: 1 completed, 0 skipped, 0 failed" in captured.out
    assert "Skipped:" not in captured.out
    assert "Failed:" not in captured.out
