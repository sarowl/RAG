import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INPUT_PATH = BASE_DIR / "eval_results.csv"
OUTPUT_PATH = BASE_DIR / "scored_results.csv"

# Keep these settings consistent across evaluation runs.
BERT_MODEL = "roberta-large"
BERT_BATCH_SIZE = 4
USE_STEMMER = True


def evaluate(input_path=INPUT_PATH, output_path=OUTPUT_PATH):
    from bert_score import BERTScorer
    from rouge_score import rouge_scorer

    with input_path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        original_fields = reader.fieldnames or []

        required = {"query_id", "answer", "reference_answer", "status"}
        missing = required - set(original_fields)
        if missing:
            raise ValueError(
                f"Missing CSV columns: {', '.join(sorted(missing))}"
            )

        rows = list(reader)

    if not rows:
        raise ValueError("eval_results.csv contains no results.")

    score_fields = ["rouge_l_f1", "bertscore_f1", "evaluation_status"]
    output_fields = original_fields + [
        field for field in score_fields if field not in original_fields
    ]

    valid_rows = []

    for row in rows:
        row["rouge_l_f1"] = ""
        row["bertscore_f1"] = ""

        if row["status"].strip().lower() != "success":
            row["evaluation_status"] = "skipped_request_error"
        elif not (row.get("answer") or "").strip():
            row["evaluation_status"] = "skipped_empty_answer"
        elif not (row.get("reference_answer") or "").strip():
            row["evaluation_status"] = "skipped_empty_reference"
        else:
            row["evaluation_status"] = "pending"
            valid_rows.append(row)

    if valid_rows:
        rouge = rouge_scorer.RougeScorer(
            ["rougeL"],
            use_stemmer=USE_STEMMER,
        )

        print(f"Loading BERTScore model: {BERT_MODEL}")
        print("The first run may download model files.")

        bert = BERTScorer(
            model_type=BERT_MODEL,
            lang="en",
            device="cpu",
            batch_size=BERT_BATCH_SIZE,
            rescale_with_baseline=False,
        )

        answers = [row["answer"].strip() for row in valid_rows]
        references = [
            row["reference_answer"].strip() for row in valid_rows
        ]

        print(f"Scoring {len(valid_rows)} answers...")
        _, _, bert_f1 = bert.score(
            answers,
            references,
            verbose=True,
        )

        for row, answer, reference, f1 in zip(
            valid_rows, answers, references, bert_f1.tolist()
        ):
            rouge_f1 = rouge.score(reference, answer)["rougeL"].fmeasure

            row["rouge_l_f1"] = f"{rouge_f1:.6f}"
            row["bertscore_f1"] = f"{f1:.6f}"
            row["evaluation_status"] = "scored"

            print(
                f"{row['query_id']}: "
                f"ROUGE-L F1={rouge_f1:.4f}, "
                f"BERTScore F1={f1:.4f}"
            )

    # Replaces the scored output; preserves the original input CSV.
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved results to {output_path}")
    print(f"Scored: {len(valid_rows)}")
    print(f"Skipped: {len(rows) - len(valid_rows)}")


def main():
    parser = argparse.ArgumentParser(
        description="Run every benchmark question, then score similarity and faithfulness."
    )
    parser.add_argument("--benchmark", type=Path, default=BASE_DIR / "benchmark.json")
    parser.add_argument("--output-dir", type=Path, help="New directory for this run.")
    parser.add_argument("--judge-model", default="qwen2.5:1.5b")
    parser.add_argument(
        "--input", type=Path,
        help="Score an existing runner CSV instead of sending questions again.",
    )
    args = parser.parse_args()

    # Support both direct execution and python -m evaluation.evaluator.
    if __package__:
        from . import runner, factscore_evaluator
    else:
        import runner
        import factscore_evaluator

    # Check scoring dependencies before making potentially slow API requests.
    import bert_score
    import rouge_score

    output_dir = args.output_dir or (
        BASE_DIR / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    raw_path = args.input or output_dir / "eval_results.csv"
    scored_path = output_dir / "scored_results.csv"
    final_path = output_dir / "scored_results_faithfulness.csv"

    if args.input is None:
        print("Step 1/3: Running all benchmark questions...", flush=True)
        runner.main(args.benchmark, raw_path)
    print("Step 2/3: Scoring ROUGE-L and BERTScore...", flush=True)
    evaluate(raw_path, scored_path)
    print("Step 3/3: Scoring faithfulness...", flush=True)
    factscore_evaluator.evaluate(scored_path, final_path, args.judge_model)
    print(f"\nEvaluation complete. Combined results: {final_path}")


if __name__ == "__main__":
    main()
