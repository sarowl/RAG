"""Score answer faithfulness against saved retrieval contexts with RAGAS."""

import argparse
import asyncio
import csv
import json
import logging
import os
from pathlib import Path

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = BASE_DIR.parent / "sanitize" / "kiosks_data.csv"
DEFAULT_JUDGE_MODEL = "gemma3:12b"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
FAITHFULNESS_FIELDS = [
    "faithfulness_score", "supported_claims", "total_claims",
    "faithfulness_status", "faithfulness_judge_model", "faithfulness_error",
]
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Score RAGAS Faithfulness for kiosk data or a runner CSV."
    )
    parser.add_argument(
        "input", type=Path, nargs="?", default=DEFAULT_INPUT,
        help="Results CSV with retrieved_contexts (default: sanitize/kiosks_data.csv).",
    )
    parser.add_argument(
        "--output", type=Path,
        help="Output CSV; defaults to <input>_faithfulness.csv.",
    )
    parser.add_argument(
        "--judge-model", default=DEFAULT_JUDGE_MODEL,
        help=f"Local Ollama judge model (default: {DEFAULT_JUDGE_MODEL}).",
    )
    parser.add_argument("--retry-errors", action="store_true",
                        help="Score only rows with faithfulness_status=error; preserve other rows.")
    parser.add_argument("--log", type=Path, help="Write progress and exception tracebacks to this file.")
    parser.add_argument("--max-tokens", type=int, default=8192,
                        help="Judge output token limit (default: 8192).")
    return parser.parse_args()


async def score_rows(rows, judge_model, max_tokens=8192):
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
        max_tokens=max_tokens,
    )
    metric = Faithfulness(llm=judge)
    logger.info("Judge request parameters: %s", judge.model_args)

    for index, row in enumerate(rows, start=1):
        # Kiosk exports already contain scores. Clear them before each attempt
        # so skipped or failed rows cannot retain results from a previous judge.
        row.update(dict.fromkeys(FAITHFULNESS_FIELDS, ""))
        row["faithfulness_judge_model"] = judge_model
        label = f"[{index}/{len(rows)}] {row.get('model', '?')} / {row.get('query_id', '?')}"
        if row.get("status", "").strip().lower() != "success":
            row["faithfulness_status"] = "skipped_request_error"
            logger.info("%s: %s", label, row["faithfulness_status"])
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
                row["faithfulness_error"] = f"{type(exc).__name__}: {exc!r}"
                logger.exception("%s: scoring failed", label)
                completion = getattr(exc, "last_completion", None)
                if completion is not None:
                    logger.error("%s: usage=%s; finish_reasons=%s", label,
                                 getattr(completion, "usage", None),
                                 [choice.finish_reason for choice in completion.choices])

        logger.info("%s: %s (score=%s)", label, row["faithfulness_status"], row["faithfulness_score"])


def evaluate(input_path=DEFAULT_INPUT, output_path=None, judge_model=DEFAULT_JUDGE_MODEL,
             retry_errors=False, max_tokens=8192):
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive.")
    input_path = input_path.resolve()
    output_path = (
        output_path.resolve()
        if output_path
        else input_path.with_name(f"{input_path.stem}_{'retry' if retry_errors else 'faithfulness'}.csv")
    )

    with input_path.open(newline="", encoding="utf-8-sig") as file:
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

    selected = (
        [row for row in rows if row.get("faithfulness_status", "").strip().lower() == "error"]
        if retry_errors else rows
    )
    logger.info("Scoring %d of %d rows with %s, max_tokens=%d; input=%s",
                len(selected), len(rows), judge_model, max_tokens, input_path)
    if selected:
        asyncio.run(score_rows(selected, judge_model, max_tokens))

    output_fields = fields + [field for field in FAITHFULNESS_FIELDS if field not in fields]
    with output_path.open("x", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Saved RAGAS Faithfulness results to %s", output_path)


def main():
    args = parse_args()
    handlers = [logging.StreamHandler()]
    if args.log:
        handlers.append(logging.FileHandler(args.log, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    evaluate(args.input, args.output, args.judge_model, args.retry_errors, args.max_tokens)


if __name__ == "__main__":
    main()
