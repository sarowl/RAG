"""Score the saved LAN answers with ROUGE-L, BERTScore, and Faithfulness.

Run from the project root:
    python evaluation/evaluate_all_runner.py

Requires the evaluation packages and a running Ollama server with
qwen2.5:1.5b installed. Does not send questions to the chatbot again.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys


BASE_DIR = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path,
        default=BASE_DIR / "LAN" / "runner" / "All_runner.csv",
        help="Saved answers CSV (defaults to LAN/runner/All_runner.csv).",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        help="New results directory; defaults to LAN/evaluation/<UTC timestamp>.",
    )
    parser.add_argument(
        "--judge-model", default="qwen2.5:1.5b",
        help="Installed Ollama model used to judge faithfulness.",
    )
    args = parser.parse_args()
    input_path = args.input.resolve()
    if not input_path.is_file():
        parser.error(f"Input CSV not found: {input_path}")

    output_dir = args.output_dir or (
        BASE_DIR / "LAN" / "evaluation"
        / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    )
    output_dir = output_dir.resolve()
    if output_dir.exists():
        parser.error(f"Output directory already exists; choose a new one: {output_dir}")

    print(f"Evaluating saved answers: {input_path}", flush=True)
    print(f"Results directory: {output_dir}", flush=True)
    result = subprocess.run([
        sys.executable, "-u", str(BASE_DIR / "evaluator.py"),
        "--input", str(input_path),
        "--output-dir", str(output_dir),
        "--judge-model", args.judge_model,
    ], check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
