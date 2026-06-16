"""Run the test set against the live /chat endpoint, score, and write a report.

Usage (from project root):
    python -m eval.run_eval [--base-url URL] [--limit N]

Outputs `eval/results/run_<timestamp>.{json,md}`.

The API must be running. For docker:
    docker compose up -d
    docker compose exec api python -m scripts.ingest_kb --recreate
    python -m eval.run_eval
"""
import argparse
import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import httpx

from eval.metrics import (
    data_value_reference,
    faithfulness_judge,
    must_contain_check,
    refusal_correctness_judge,
    source_attribution,
    tool_selection_correctness,
)

logger = logging.getLogger(__name__)


async def _fetch_history(client: httpx.AsyncClient, base_url: str, user_id: str) -> list[dict]:
    r = await client.get(f"{base_url}/sample-history", params={"user_id": user_id}, timeout=30)
    r.raise_for_status()
    return r.json()["history"]


async def _run_case(
    client: httpx.AsyncClient,
    case: dict,
    base_url: str,
    histories: dict[str, list],
) -> tuple[dict, float]:
    body = {
        "message": case["input"]["message"],
        "user_id": case["input"].get("user_id", "anonymous"),
    }
    history_key = case["input"].get("history_user")
    if history_key is not None:
        body["history"] = histories.get(history_key, [])

    t0 = time.time()
    resp = await client.post(f"{base_url}/chat", json=body, timeout=180)
    elapsed = time.time() - t0
    resp.raise_for_status()
    return resp.json(), elapsed


async def _score_case(case: dict, response: dict) -> list[dict]:
    expected = case["expected"]
    scored: list[dict] = []

    scored.append(tool_selection_correctness(expected, response))

    for fn in (source_attribution, data_value_reference, must_contain_check):
        result = fn(expected, response)
        if result is not None:
            scored.append(result)

    faithfulness = await faithfulness_judge(case, response)
    if faithfulness is not None:
        scored.append(faithfulness)

    if case["type"] == "adversarial":
        scored.append(await refusal_correctness_judge(case, response))

    return scored


def _aggregate(results: list[dict]) -> dict:
    per_metric: dict[str, dict] = {}
    per_type: dict[str, dict] = {}

    for r in results:
        if r.get("error"):
            continue
        case_type = r["case"]["type"]
        per_type.setdefault(case_type, {"total": 0, "all_pass": 0})
        per_type[case_type]["total"] += 1
        if all(s.get("passed", False) for s in r["scores"]):
            per_type[case_type]["all_pass"] += 1

        for s in r["scores"]:
            metric = s["metric"]
            per_metric.setdefault(metric, {"total": 0, "passed": 0, "scores": []})
            per_metric[metric]["total"] += 1
            if s.get("passed"):
                per_metric[metric]["passed"] += 1
            per_metric[metric]["scores"].append(s["score"])

    return {
        "per_metric": {
            m: {
                "n": v["total"],
                "passed": v["passed"],
                "pass_rate": round(v["passed"] / max(v["total"], 1), 3),
                "avg_score": round(sum(v["scores"]) / max(len(v["scores"]), 1), 3),
            }
            for m, v in per_metric.items()
        },
        "per_type": {
            t: {
                "n": v["total"],
                "all_metrics_pass": v["all_pass"],
                "pass_rate": round(v["all_pass"] / max(v["total"], 1), 3),
            }
            for t, v in per_type.items()
        },
        "total_cases": len(results),
        "errored": sum(1 for r in results if r.get("error")),
    }


def _render_markdown(summary: dict, results: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# Evaluation Report")
    lines.append(f"\nGenerated: {datetime.now().isoformat(timespec='seconds')}\n")

    lines.append("## Summary by metric\n")
    lines.append("| Metric | N | Passed | Pass rate | Avg score |")
    lines.append("|---|---|---|---|---|")
    for m, v in summary["per_metric"].items():
        lines.append(
            f"| `{m}` | {v['n']} | {v['passed']} | {v['pass_rate']:.0%} | {v['avg_score']:.2f} |"
        )

    lines.append("\n## Summary by case type\n")
    lines.append("| Type | N | All metrics pass | Pass rate |")
    lines.append("|---|---|---|---|")
    for t, v in summary["per_type"].items():
        lines.append(
            f"| {t} | {v['n']} | {v['all_metrics_pass']} | {v['pass_rate']:.0%} |"
        )

    lines.append(
        f"\n**Total cases:** {summary['total_cases']} (errored: {summary['errored']})\n"
    )

    lines.append("\n## Per-case detail\n")
    for r in results:
        case = r["case"]
        lines.append(f"### `{case['id']}` ({case['type']})")
        if r.get("error"):
            lines.append(f"\n**ERROR:** {r['error']}\n")
            continue
        resp = r["response"]
        lines.append(f"\n- **Input:** {case['input']['message']}")
        lines.append(
            f"- **Refused:** {resp.get('refused')} ({resp.get('refusal_category')})"
        )
        tools = [t["tool_name"] for t in resp.get("tool_traces", [])]
        lines.append(f"- **Tools called:** {tools}")
        lines.append(f"- **Latency:** {r.get('elapsed_s')}s")
        ans_preview = (resp.get("answer") or "").replace("\n", " ")[:300]
        lines.append(f"- **Answer (truncated):** {ans_preview}...")
        lines.append("\n**Metrics:**")
        for s in r["scores"]:
            symbol = "✓" if s.get("passed") else "✗"
            lines.append(
                f"- {symbol} `{s['metric']}` = {s['score']} — {s.get('detail', '')}"
            )
        lines.append("")

    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run eval test set against /chat")
    parser.add_argument("--base-url", default="http://localhost:8000/api/v1")
    parser.add_argument("--testset", default="eval/testset.json")
    parser.add_argument("--out-dir", default="eval/results")
    parser.add_argument("--limit", type=int, default=None, help="Only run first N cases")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")

    cases = json.loads(Path(args.testset).read_text())
    if args.limit:
        cases = cases[: args.limit]
    print(f"Running {len(cases)} eval cases against {args.base_url}\n")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as client:
        histories: dict[str, list] = {"__empty__": []}
        for uid in ("user_a", "user_b"):
            histories[uid] = await _fetch_history(client, args.base_url, uid)

        results: list[dict] = []
        for case in cases:
            print(f"  {case['id']:38s}  ", end="", flush=True)
            try:
                response, elapsed = await _run_case(client, case, args.base_url, histories)
                scores = await _score_case(case, response)
                passes = sum(1 for s in scores if s.get("passed"))
                results.append(
                    {
                        "case": case,
                        "response": response,
                        "scores": scores,
                        "elapsed_s": round(elapsed, 2),
                    }
                )
                print(f"{passes}/{len(scores)} pass  ({elapsed:.1f}s)")
            except Exception as exc:  # noqa: BLE001
                logger.exception("Case %s failed", case["id"])
                results.append({"case": case, "error": str(exc), "scores": []})
                print(f"ERROR: {exc}")

    summary = _aggregate(results)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = out_dir / f"run_{timestamp}.json"
    md_path = out_dir / f"run_{timestamp}.md"

    json_path.write_text(
        json.dumps({"summary": summary, "results": results}, indent=2, default=str)
    )
    md_path.write_text(_render_markdown(summary, results))

    print("\n=== SUMMARY ===\n")
    print("Per metric:")
    for m, v in summary["per_metric"].items():
        print(
            f"  {m:30s}  pass {v['pass_rate']:.0%}  avg {v['avg_score']:.2f}  (n={v['n']})"
        )
    print("\nPer type:")
    for t, v in summary["per_type"].items():
        print(
            f"  {t:30s}  all-metrics-pass {v['pass_rate']:.0%}  (n={v['n']})"
        )

    print(f"\nReport JSON: {json_path}")
    print(f"Report MD:   {md_path}")


if __name__ == "__main__":
    asyncio.run(main())
