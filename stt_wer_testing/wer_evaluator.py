"""Score kiosk STT transcripts from Excel and export pooled and row WER."""

import argparse
from pathlib import Path
import re
import sys
import unicodedata

import pandas as pd
from jiwer import process_words


REQUIRED_COLUMNS = ["Query ID", "Condition", "Speaker", "Reference", "STT output"]


def normalize_text(value):
    """Use identical missing-value, case, punctuation, and whitespace rules."""
    if pd.isna(value):
        return ""
    text = str(value).lower()
    text = "".join(c for c in text if not unicodedata.category(c).startswith("P"))
    return re.sub(r"\s+", " ", text).strip()


def load_input(file_path, sheet_name):
    data = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
    missing = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing:
        raise ValueError("Missing required columns: " + ", ".join(missing))
    if data.empty:
        raise ValueError("The input sheet contains no data rows.")
    return data


def wer_percentage(substitutions, deletions, insertions, reference_words):
    """Zero-reference WER is undefined; export it as N/A."""
    if reference_words == 0:
        return float("nan")
    return 100 * (substitutions + deletions + insertions) / reference_words


def score_rows(data):
    detail = data.copy()
    scores = []
    empty_outputs = []
    empty_references = []
    for index, row in data.iterrows():
        reference = normalize_text(row["Reference"])
        hypothesis = normalize_text(row["STT output"])
        if not hypothesis:
            empty_outputs.append(index)
        if not reference:
            empty_references.append(index)
        result = process_words(reference, hypothesis)
        s, d, i = result.substitutions, result.deletions, result.insertions
        n = result.hits + s + d
        scores.append((s, d, i, n, wer_percentage(s, d, i, n)))
    if empty_outputs:
        print(f"Warning: empty normalized STT output at zero-based row indices: {empty_outputs}. "
              "All reference words in these rows count as deletions.", file=sys.stderr)
    if empty_references:
        print(f"Warning: empty normalized reference at zero-based row indices: {empty_references}. "
              "Row WER is N/A because N is zero; insertion counts remain included in summaries.",
              file=sys.stderr)
    detail[["S", "D", "I", "N", "WER (%)"]] = pd.DataFrame(scores, index=data.index)
    return detail


def build_summary(detail):
    rows = []

    def add_group(group_type, group_name, group):
        s, d, i, n = (int(group[column].sum()) for column in ["S", "D", "I", "N"])
        rows.append({"Group": group_type, "Value": group_name, "S": s, "D": d,
                     "I": i, "N": n, "WER (%)": wer_percentage(s, d, i, n)})

    for column in ["Condition", "Speaker"]:
        for name, group in detail.groupby(column, dropna=False, sort=False):
            add_group(column, "(missing)" if pd.isna(name) else name, group)
    add_group("Overall", "All rows", detail)
    return pd.DataFrame(rows)


def save_results(summary, detail, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [output_dir / "wer_summary.csv", output_dir / "wer_detail.csv"]
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError("Output already exists; move it or choose another --output-dir: "
                              + ", ".join(existing))
    for frame, path in zip([summary, detail], paths):
        frame.to_csv(path, index=False, encoding="utf-8-sig", na_rep="N/A", mode="x")
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path", nargs="?", type=Path,
                        default=Path(__file__).parent / "input.xlsx")
    parser.add_argument("--sheet", default=None,
                        help="Excel sheet name (default: first sheet)")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).parent,
                        help="CSV directory (default: script directory)")
    args = parser.parse_args()
    try:
        data = load_input(args.file_path, args.sheet if args.sheet is not None else 0)
        detail = score_rows(data)
        summary = build_summary(detail)
        paths = save_results(summary, detail, args.output_dir)
    except (OSError, ValueError, ImportError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(summary.to_string(index=False, float_format=lambda value: f"{value:.2f}", na_rep="N/A"))
    for path in paths:
        print(f"Saved: {path}")


if __name__ == "__main__":
    main()
