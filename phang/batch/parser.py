"""Markdown batch list parser for the phang pipeline.

Parses a markdown file containing a table of phage entries in the format:

    | # | Name | Source File |
    |---|------|-------------|
    | 1 | PhageA | `path/to/a.fasta` |
    ...

Returns a list of PhageEntry named tuples. Entries in the **Skipped:** section
below the table are excluded (they are not table rows — the parser stops at the
first non-pipe line after the table header).
"""

from pathlib import Path
from typing import List, NamedTuple


class PhageEntry(NamedTuple):
    """A single phage entry parsed from the batch list."""

    name: str
    source_file: str


def parse_batch_list(path: Path) -> List[PhageEntry]:
    """Parse a markdown batch list file and return a list of PhageEntry items.

    Args:
        path: Path to the markdown file containing the phage table.

    Returns:
        List of PhageEntry(name, source_file) for each row in the table.

    Raises:
        ValueError: If no markdown table with the expected header is found.
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()

    # Find the header line: must contain | # |, | Name |, | Source File |
    header_idx = None
    for i, line in enumerate(lines):
        if "| # |" in line and "| Name |" in line and "| Source File |" in line:
            header_idx = i
            break

    if header_idx is None:
        raise ValueError(
            f"No markdown table found in {path}. "
            "Expected a header line containing '| # |', '| Name |', '| Source File |'."
        )

    # Skip the separator line immediately after the header (contains dashes)
    entries: List[PhageEntry] = []
    reading = False

    for line in lines[header_idx + 1 :]:
        # Skip the separator line (e.g. |---|------|-------------|)
        if not reading and "---" in line:
            reading = True
            continue

        # Stop when we hit a line that isn't a table row
        if not line.strip().startswith("|"):
            break

        # Split on pipe and extract columns (index 1=row#, 2=name, 3=source_file)
        cols = line.split("|")
        if len(cols) < 4:
            continue

        name = cols[2].strip()
        source_file = cols[3].strip().strip("`")

        if not name:
            continue

        entries.append(PhageEntry(name=name, source_file=source_file))

    return entries
