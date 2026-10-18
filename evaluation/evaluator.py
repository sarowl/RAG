import csv
from pathlib import Path

from bert_score import BERTScorer
from rouge_score import rouge_scorer

BASE_DIR = Path(__file__).resolve().parent
INPUT_PATH = BASE_DIR / "eval_results.csv"
OUTPUT_PATH = BASE_DIR / "scored_results.csv"

# Keep these settings consistent across evaluation runs.
BERT_MODEL = "roberta-large"
BERT_BATCH_SIZE = 4
USE_STEMMER = True


def main():
    with INPUT_PATH.open(newline="", encoding="utf-8") as file:
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
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved results to {OUTPUT_PATH}")
    print(f"Scored: {len(valid_rows)}")
    print(f"Skipped: {len(rows) - len(valid_rows)}")


if __name__ == "__main__":
    main()