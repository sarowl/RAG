import csv
import json
from pathlib import Path
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
BENCHMARK_PATH = BASE_DIR / "benchmark.json"
OUTPUT_PATH = BASE_DIR / "eval_results.csv"
API_URL = "http://127.0.0.1:8000/api/chat"
MODEL_NAME = "llama3.2:3b"


def main():
    with BENCHMARK_PATH.open(encoding="utf-8") as file:
        benchmark = json.load(file)

    if not isinstance(benchmark, list) or not benchmark:
        raise ValueError("benchmark.json must contain a nonempty array.")

    seen_ids = set()
    for case in benchmark:
        for field in ("query_id", "query", "reference_answer"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError(f"Each case needs a nonempty '{field}'.")

        if case["query_id"] in seen_ids:
            raise ValueError(f"Duplicate query_id: {case['query_id']}")
        seen_ids.add(case["query_id"])

    fields = [
        "model", "query_id", "query", "reference_answer", "answer",
        "sources", "retrieved_contexts", "tps", "ttft", "status", "error",
    ]

    # Exclusive creation prevents accidentally overwriting an earlier run.
    with OUTPUT_PATH.open("x", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for case in benchmark:
            row = {
                "model": MODEL_NAME,
                "query_id": case["query_id"],
                "query": case["query"],
                "reference_answer": case["reference_answer"],
            }

            request = Request(
                API_URL,
                data=json.dumps({
                    "question": case["query"],
                    "history": [],
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            try:
                with urlopen(request, timeout=600) as response:
                    result = json.load(response)

                answer = result.get("answer")
                if not isinstance(answer, str) or not answer.strip():
                    raise ValueError("API returned no usable answer.")

                row.update({
                    "answer": answer,
                    "sources": json.dumps(
                        result.get("sources", []), ensure_ascii=False
                    ),
                    "retrieved_contexts": json.dumps(
                        result.get("retrieved_contexts", []), ensure_ascii=False
                    ),
                    "tps": result.get("tps"),
                    "ttft": result.get("ttft"),
                    "status": "success",
                    "error": "",
                })
            except Exception as exc:
                row.update({
                    "status": "error",
                    "error": str(exc),
                })

            writer.writerow(row)
            file.flush()
            print(f"{case['query_id']}: {row['status']}")

    print(f"Results saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
