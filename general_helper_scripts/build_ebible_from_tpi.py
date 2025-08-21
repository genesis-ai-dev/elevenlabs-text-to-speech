#!/usr/bin/env python3
"""
Build an ebible-style text from Tok Pisin source files and a versification list.

Given a versification file (e.g., "vref_eng_verses_added_1.txt") that lists one
verse reference per line (e.g., "GEN 1:1"), and a directory containing Tok Pisin
book files (e.g., "tpi_Tok_Pisin/GEN.txt"), this script reconstructs a single
output file where each output line contains ONLY the verse content (no
reference), in the exact order of the versification file.

Behavior on missing verses: leaves the line blank and logs a warning to stderr.

Usage:
  python general_helper_scripts/build_ebible_from_tpi.py \
    --vref vref_eng_verses_added_1.txt \
    --input-dir tpi_Tok_Pisin \
    --output ebible_tpi_Tok_Pisin.txt
"""

from __future__ import annotations

import argparse
import sys
import re
from pathlib import Path
from typing import Dict, Tuple, List


VERSE_PATTERN = re.compile(r"^([1-3]?[A-Z]{2,3})\s+(\d+):(\d+)\s*(.*)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build ebible text from Tok Pisin sources and a versification list.")
    parser.add_argument("--vref", required=True, type=Path, help="Path to versification file (one 'BOOK C:V' per line)")
    parser.add_argument("--input-dir", required=True, type=Path, help="Directory containing Tok Pisin book files (e.g., GEN.txt)")
    parser.add_argument("--output", required=True, type=Path, help="Output file to write ebible verses to")
    return parser.parse_args()


def load_book(file_path: Path) -> Dict[Tuple[int, int], str]:
    """Load a Tok Pisin book file into a map of (chapter, verse) -> verse_content.

    Lines are expected to begin with "BOOK C:V", where BOOK matches the filename stem.
    Returns a dictionary mapping (chapter, verse) to the remaining content of the line.
    Non-matching lines are ignored.
    """
    verses: Dict[Tuple[int, int], str] = {}
    if not file_path.exists():
        return verses

    book_code = file_path.stem.upper()
    with file_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n\r")
            m = VERSE_PATTERN.match(line)
            if not m:
                continue
            ref_book, chapter_str, verse_str, remainder = m.groups()
            # Be permissive if the line's ref book code doesn't match the filename
            # (we still accept it, but filename determines which file we are in).
            try:
                chapter = int(chapter_str)
                verse = int(verse_str)
            except ValueError:
                continue
            verse_content = (remainder or "").strip()
            verses[(chapter, verse)] = verse_content
    return verses


def build_book_index(input_dir: Path) -> Dict[str, Dict[Tuple[int, int], str]]:
    """Eagerly load all book files into memory.

    Returns a mapping: BOOK_CODE -> {(chapter, verse): content}
    """
    index: Dict[str, Dict[Tuple[int, int], str]] = {}
    for path in sorted(input_dir.glob("*.txt")):
        book_code = path.stem.upper()
        index[book_code] = load_book(path)
    return index


def parse_vref_line(line: str) -> Tuple[str, int, int] | None:
    m = VERSE_PATTERN.match(line.strip())
    if not m:
        return None
    book, ch_str, vs_str, _ = m.groups()
    try:
        return book.upper(), int(ch_str), int(vs_str)
    except ValueError:
        return None


def main() -> None:
    args = parse_args()

    if not args.vref.exists():
        print(f"ERROR: Versification file not found: {args.vref}", file=sys.stderr)
        sys.exit(1)
    if not args.input_dir.exists() or not args.input_dir.is_dir():
        print(f"ERROR: Input directory not found or not a directory: {args.input_dir}", file=sys.stderr)
        sys.exit(1)

    # Preload all available books
    book_index = build_book_index(args.input_dir)

    total_lines = 0
    found = 0
    missing: List[str] = []
    output_lines: List[str] = []

    with args.vref.open("r", encoding="utf-8") as vf:
        for total_lines, raw_line in enumerate(vf, start=1):
            parsed = parse_vref_line(raw_line)
            if parsed is None:
                # Non-verse line in vref; output blank to preserve line numbers
                output_lines.append("")
                continue
            book, chapter, verse = parsed
            book_map = book_index.get(book)
            if not book_map:
                missing.append(f"{book} {chapter}:{verse}")
                output_lines.append("")
                continue
            content = book_map.get((chapter, verse))
            # Handle known shift: REV 12:18 aligns to REV 13:1 in many versifications
            if content is None and book == "REV" and chapter == 12 and verse == 18:
                content = book_map.get((13, 1))
            if content is None:
                missing.append(f"{book} {chapter}:{verse}")
                output_lines.append("")
                continue
            found += 1
            output_lines.append(content)

    # Ensure output directory exists
    if args.output.parent and not args.output.parent.exists():
        args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8", newline="\n") as out:
        for line in output_lines:
            out.write(f"{line}\n")

    print(f"Wrote ebible: {args.output}")
    print(f"Lines processed: {total_lines}")
    print(f"Found verses:   {found}")
    missing_count = len(missing)
    print(f"Missing verses: {missing_count}")
    if missing_count:
        # Print a concise sample of missing refs to help debug
        sample = ", ".join(missing[:20])
        print(f"First missing:  {sample}{' ...' if missing_count > 20 else ''}")


if __name__ == "__main__":
    main()


