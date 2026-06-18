"""Tests for phang.batch.parser — markdown batch list parser."""

from pathlib import Path

import pytest

from phang.batch.parser import PhageEntry, parse_batch_list

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_simple_table():
    """Parse a 3-row markdown table and return 3 PhageEntry items."""
    entries = parse_batch_list(FIXTURES / "batch_simple.md")
    assert len(entries) == 3
    assert entries[0] == PhageEntry("PhageA", "path/to/a.fasta")
    assert entries[1] == PhageEntry("PhageB", "path/to/b.fasta")
    assert entries[2] == PhageEntry("PhageC (isolate X)", "path/to/c.fasta")


def test_non_numeric_row_included():
    """Row with # value '3b' (non-numeric) must be included."""
    entries = parse_batch_list(FIXTURES / "batch_simple.md")
    assert entries[2].name == "PhageC (isolate X)"


def test_backticks_stripped():
    """Source file values have backtick wrapping stripped."""
    entries = parse_batch_list(FIXTURES / "batch_simple.md")
    assert "`" not in entries[0].source_file
    assert entries[0].source_file == "path/to/a.fasta"


def test_skipped_section_excluded():
    """Entries listed in the Skipped section are NOT returned."""
    entries = parse_batch_list(FIXTURES / "batch_with_skipped.md")
    assert len(entries) == 2


def test_empty_file_raises():
    """File with no markdown table raises ValueError."""
    empty = FIXTURES / "_empty_test.md"
    empty.write_text("# No table here\nJust some text.\n", encoding="utf-8")
    try:
        with pytest.raises(ValueError):
            parse_batch_list(empty)
    finally:
        empty.unlink(missing_ok=True)


def test_real_batch_list():
    """The real phage_batch_list.md parses to exactly 30 entries.

    The table contains rows 1-21, 21b, 22-29 (30 data rows total).
    The **Skipped:** section lists files that are not in the table at all,
    so they do not affect the count.
    """
    real_list = Path(__file__).parent.parent / "phage_batch_list.md"
    entries = parse_batch_list(real_list)
    assert len(entries) == 30
