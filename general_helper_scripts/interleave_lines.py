import os
from typing import List, Tuple


# Configure here: list files and 1-based inclusive line ranges to show
FILES: List[str] = [
    # Example:
    "source_texts/8k_phrases_eng_extended.txt",
    "source_texts/8k_phrases_ind_extended.txt",
    "source_texts/8k_phrases_por_extended.txt",
]

# Each tuple is (start_line_inclusive, end_line_inclusive)
LINE_RANGES: List[Tuple[int, int]] = [
    # Example:
    (2835, 2854),
]


def read_lines(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().splitlines()
    except UnicodeDecodeError:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read().splitlines()


def interleave(files: List[str], ranges: List[Tuple[int, int]]) -> None:
    if len(files) < 2:
        print("Please configure at least two files in FILES.")
        return

    file_to_lines = {path: read_lines(path) for path in files}
    file_labels = {path: os.path.basename(path) for path in files}

    for (start, end) in ranges:
        if start <= 0 or end <= 0:
            print(f"Skipping invalid range ({start}, {end}); lines are 1-based.")
            continue
        if end < start:
            print(f"Skipping invalid range ({start}, {end}); end < start.")
            continue

        for line_no in range(start, end + 1):
            for path in files:
                lines = file_to_lines[path]
                label = file_labels[path]
                if 1 <= line_no <= len(lines):
                    print(f"{label} L{line_no}: {lines[line_no - 1]}")
                else:
                    print(f"{label} L{line_no}: [OUT OF RANGE]")
            print("")


if __name__ == "__main__":
    interleave(FILES, LINE_RANGES)


