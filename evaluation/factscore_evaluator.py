"""Score answer faithfulness against saved retrieval contexts with RAGAS."""

import argparse
import asyncio
import csv
import json
import os
from pathlib import Path

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_JUDGE_MODEL = "qwen2.5:1.5b"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Score RAGAS Faithfulness separately for a runner CSV."
    )
    parser.add_argument("input", type=Path, help="Runner results CSV with retrieved_contexts.")
    parser.add_argument(
        "--output", type=Path,
        help="Output CSV; defaults to <input>_faithfulness.csv.",
    )
    parser.add_argument(
        "--judge-model", default=DEFAULT_JUDGE_MODEL,
        help=f"Local Ollama judge model (default: {DEFAULT_JUDGE_MODEL}).",
    )
    return parser.parse_args()


async def score_rows(rows, judge_model):
    # Ollama provides an OpenAI-compatible endpoint locally. The dummy key is
    # required by the OpenAI client but is not sent as a real credential.
    client = AsyncOpenAI(
        api_key="ollama",
        base_url=f"{OLLAMA_BASE_URL.rstrip('/')}/v1",
    )
    judge = llm_factory(
        judge_model,
        client=client,
        temperature=0,
    )
    metric = Faithfulness(llm=judge)

    for row in rows:
        if row.get("status", "").strip().lower() != "success":
            row["faithfulness_score"] = ""
            row["supported_claims"] = ""
            row["total_claims"] = ""
            row["faithfulness_status"] = "skipped_request_error"
            continue

        answer = (row.get("answer") or "").strip()
        try:
            contexts = json.loads(row.get("retrieved_contexts") or "[]")
        except (json.JSONDecodeError, TypeError):
            contexts = []

        if not answer:
            row["faithfulness_status"] = "skipped_empty_answer"
        elif not isinstance(contexts, list) or not contexts:
            row["faithfulness_status"] = "skipped_missing_context"
        else:
            try:
                result = await metric.ascore(
                    user_input=row.get("query", ""),
                    response=answer,
                    retrieved_contexts=[str(context) for context in contexts],
                )
                row["faithfulness_score"] = (
                    "" if result.value is None else f"{result.value:.6f}"
                )
                # RAGAS exposes the final faithfulness score, not a stable
                # supported/total claim count through this metric API.
                row["supported_claims"] = ""
                row["total_claims"] = ""
                row["faithfulness_status"] = "scored"
            except Exception as exc:
                row["faithfulness_status"] = "error"
                row["faithfulness_error"] = str(exc)

        row["faithfulness_judge_model"] = judge_model
        print(f"{row.get('query_id', '?')}: {row['faithfulness_status']}")


def main():
    args = parse_args()
    input_path = args.input.resolve()
    output_path = (
        args.output.resolve()
        if args.output
        else input_path.with_name(f"{input_path.stem}_faithfulness.csv")
    )

    with input_path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        fields = reader.fieldnames or []
        if not {"query_id", "query", "answer", "status", "retrieved_contexts"}.issubset(fields):
            raise ValueError(
                "Input CSV must include query_id, query, answer, status, and "
                "retrieved_contexts. Rerun the runner after enabling passage capture."
            )
        rows = list(reader)

    if not rows:
        raise ValueError("Input CSV contains no result rows.")
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {output_path}")

    asyncio.run(score_rows(rows, args.judge_model))

    added_fields = [
        "faithfulness_score", "supported_claims", "total_claims",
        "faithfulness_status", "faithfulness_judge_model", "faithfulness_error",
    ]
    output_fields = fields + [field for field in added_fields if field not in fields]
    with output_path.open("x", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved RAGAS Faithfulness results to {output_path}")


if __name__ == "__main__":
    main()
