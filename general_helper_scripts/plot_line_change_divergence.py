import argparse
import os
import sys
from typing import List


def read_lines(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().splitlines()
    except UnicodeDecodeError:
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read().splitlines()


def measure_length(line: str, mode: str) -> int:
    stripped = line.strip()
    if mode == "words":
        return 0 if not stripped else len(stripped.split())
    return len(stripped)


def compute_deviation_series(lengths: List[int]) -> List[float]:
    if not lengths:
        return []
    avg = sum(lengths) / max(len(lengths), 1)
    if avg == 0:
        return [0.0 for _ in lengths]
    return [(value - avg) / avg for value in lengths]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Plot absolute differences between deviation-from-average series for up to three files."
        )
    )
    parser.add_argument("files", nargs="+", help="Paths to 2 or 3 text files to compare")

    args = parser.parse_args()

    import matplotlib.pyplot as plt

    # Validate number of files
    if len(args.files) < 2:
        print("Please provide 2 or 3 files.")
        return 1
    if len(args.files) > 3:
        print("Please provide at most 3 files.")
        return 1

    # Read all files and compute deviation series for each (based on character counts)
    all_lines: List[List[str]] = [read_lines(path) for path in args.files]
    if any(len(lines) == 0 for lines in all_lines):
        print("One or more files are empty. Cannot compute deviations.")
        return 1

    # Compute full-length character counts and deviations per file
    all_lengths: List[List[int]] = [
        [measure_length(line, "chars") for line in lines] for lines in all_lines
    ]
    all_devs: List[List[float]] = [compute_deviation_series(lengths) for lengths in all_lengths]

    # Truncate all series to the minimum length to align line indices for plotting
    min_len = min(len(devs) for devs in all_devs)
    if min_len < 1:
        print("Not enough lines to compute deviations.")
        return 1

    x_values = list(range(1, min_len + 1))

    # Build punctuation presence maps (over the truncated length)
    def flags_for_line(text: str) -> dict:
        has_qmark = "?" in text
        has_exclam = "!" in text
        return {
            "question": has_qmark,
            "exclam": has_exclam,
        }

    punct_flags: List[List[dict]] = [
        [flags_for_line(line) for line in lines[:min_len]] for lines in all_lines
    ]

    # Print text summary of punctuation mismatches per pair
    labels = [os.path.basename(p) for p in args.files]
    def summarize_pair(i: int, j: int, title: str) -> None:
        print(f"\nPunctuation mismatches (question/exclamation) for {title}:")
        any_found = False
        for idx in range(min_len):
            a_flags = punct_flags[i][idx]
            b_flags = punct_flags[j][idx]
            mismatched_keys = [k for k in ("question", "exclam") if a_flags[k] != b_flags[k]]
            if mismatched_keys:
                any_found = True
                for key in mismatched_keys:
                    a_has = a_flags[key]
                    b_has = b_flags[key]
                    a_label = labels[i]
                    b_label = labels[j]
                    line_no = idx + 1
                    if a_has and not b_has:
                        print(f"  line {line_no}: present in {a_label}, absent in {b_label} [{key}]")
                    elif b_has and not a_has:
                        print(f"  line {line_no}: present in {b_label}, absent in {a_label} [{key}]")
        if not any_found:
            print("  (none)")

    if len(all_devs) == 2:
        summarize_pair(0, 1, f"{labels[0]} vs {labels[1]}")
    else:
        summarize_pair(0, 1, f"{labels[0]} vs {labels[1]}")
        summarize_pair(1, 2, f"{labels[1]} vs {labels[2]}")
        summarize_pair(2, 0, f"{labels[2]} vs {labels[0]}")

    # Prepare pairwise absolute differences
    diffs = []
    titles = []
    if len(all_devs) == 2:
        a, b = all_devs[0][:min_len], all_devs[1][:min_len]
        diffs.append([abs(x - y) for x, y in zip(a, b)])
        titles.append(f"|{labels[0]} - {labels[1]}|")
        # Fill remaining with None to keep three subplots consistent
        diffs.extend([None, None])
        titles.extend(["", ""])
    else:  # exactly 3
        a, b, c = all_devs[0][:min_len], all_devs[1][:min_len], all_devs[2][:min_len]
        diffs.append([abs(x - y) for x, y in zip(a, b)])
        titles.append(f"|{labels[0]} - {labels[1]}|")
        diffs.append([abs(x - y) for x, y in zip(b, c)])
        titles.append(f"|{labels[1]} - {labels[2]}|")
        diffs.append([abs(x - y) for x, y in zip(c, a)])
        titles.append(f"|{labels[2]} - {labels[0]}|")

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    for idx, ax in enumerate(axes):
        series = diffs[idx]
        if series is None:
            ax.axis("off")
            continue
        ax.plot(x_values, series, linewidth=1.2)
        ax.set_ylabel("|Δ dev|")
        ax.set_title(titles[idx])
        ax.axhline(0.0, color="#888888", linewidth=0.8)
    axes[-1].set_xlabel("Line number")
    fig.suptitle("Absolute difference of deviation-from-average (chars)")
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    plt.show()

    return 0


if __name__ == "__main__":
    sys.exit(main())


