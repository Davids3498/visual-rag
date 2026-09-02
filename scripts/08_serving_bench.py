"""Step 7 — the serving numbers: latency, throughput, GPU saturation, cost per 1k queries.

This is what separates the project from a notebook. It load-tests the deployed generator at
concurrency 1 / 4 / 16 with *distinct* payloads (see loadtest.py for why that matters), samples
the GPU throughout, reads vLLM's own counters, and turns the measured energy into a cost per
1,000 queries next to what the same workload would cost on a hosted API.

Writes reports/serving.json.
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np
from rich.console import Console
from rich.table import Table

from visual_rag import config, data, generation, loadtest

console = Console()

# --- cost assumptions, all overridable, all stated rather than buried -----------------------
# Electricity: Israeli domestic tariff ~0.63 ILS/kWh ≈ $0.17/kWh (2026).
DEFAULT_KWH_PRICE = 0.17
# GPU draw is not system draw: CPU, RAM, PSU losses. 1.4x is the usual rule of thumb for a
# desktop under GPU load, and it is applied explicitly so the reader can disagree with it.
DEFAULT_SYSTEM_OVERHEAD = 1.4
# Renting a comparable GPU instead of owning one, for the "what would this cost in a cloud"
# line. An L4/A10G-class on-demand instance is the honest comparison for a 3090.
DEFAULT_CLOUD_GPU_USD_PER_HOUR = 1.00


def build_payloads(count: int, pages_per_query: int, model: str, max_tokens: int, seed: int):
    """One distinct (question, page images) pair per request, pre-encoded before timing."""
    eval_set = data.load_eval_set()
    corpus_ds, id_to_row = data.load_corpus_images()
    meta = eval_set.corpus.set_index("corpus_id")
    run = json.loads((config.DATA_DIR / "runs" / "visual_two_stage.json").read_text())["run"]

    rng = np.random.default_rng(seed)
    query_ids = [int(q) for q in eval_set.queries["query_id"] if str(q) in run]
    chosen = rng.permutation(query_ids)[:count]

    cfg = generation.VLMConfig(model=model, max_pages=pages_per_query, max_tokens=max_tokens)
    payloads = []
    for query_id in chosen:
        question = eval_set.queries.loc[eval_set.queries.query_id == query_id, "query"].iloc[0]
        top = sorted(run[str(query_id)].items(), key=lambda kv: -kv[1])[:pages_per_query]
        pages = [
            {
                "corpus_id": int(cid),
                "image": corpus_ds[id_to_row[int(cid)]]["image"],
                "doc_id": meta.loc[int(cid), "doc_id"],
                "page_number": int(meta.loc[int(cid), "page_number_in_doc"]),
            }
            for cid, _ in top
        ]
        payloads.append(
            {
                "model": model,
                "messages": generation.build_messages(question, pages, cfg),
                "max_tokens": max_tokens,
                "temperature": 0.0,
                # Fixed output length: tokens/second is meaningless if answers vary in length.
                "ignore_eos": True,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
        )
    return payloads


def cost_block(summary: dict, args) -> dict:
    """Cost per 1,000 queries, three ways, from the energy actually measured."""
    requests_done = summary["requests"] - summary["failed"]
    if not requests_done:
        return {}
    energy_wh = summary["gpu"].get("energy_wh", 0.0)
    wh_per_query = energy_wh / requests_done
    kwh_per_1k = wh_per_query * args.system_overhead * 1000 / 1000

    seconds_per_1k = summary["wall_seconds"] / requests_done * 1000
    cloud_usd_per_1k = seconds_per_1k / 3600 * args.cloud_gpu_usd_per_hour

    prompt_per_query = summary["tokens"]["prompt_total"] / requests_done
    completion_per_query = summary["tokens"]["completion_total"] / requests_done
    hosted = {
        name: round(
            (prompt_per_query * price["input"] + completion_per_query * price["output"])
            / 1e6
            * 1000,
            3,
        )
        for name, price in args.hosted_prices.items()
    }
    return {
        "gpu_energy_wh_per_query": round(wh_per_query, 3),
        "kwh_per_1k_queries": round(kwh_per_1k, 4),
        "electricity_usd_per_1k": round(kwh_per_1k * args.kwh_price, 4),
        "gpu_seconds_per_1k": round(seconds_per_1k, 1),
        "cloud_gpu_rental_usd_per_1k": round(cloud_usd_per_1k, 3),
        "hosted_api_usd_per_1k": hosted,
        "tokens_per_query": {
            "prompt": round(prompt_per_query),
            "completion": round(completion_per_query),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("VRAG_VLLM_URL", "http://localhost:8000/v1"),
        help="model endpoint; for k3s use http://<node-ip>:30800/v1 (`kubectl get nodes -o wide`)",
    )
    parser.add_argument("--model", default=generation.DEFAULT_MODEL)
    parser.add_argument("--concurrency", default="1,4,16")
    parser.add_argument("--requests", type=int, default=32, help="requests per concurrency level")
    parser.add_argument("--pages", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--kwh-price", type=float, default=DEFAULT_KWH_PRICE)
    parser.add_argument("--system-overhead", type=float, default=DEFAULT_SYSTEM_OVERHEAD)
    parser.add_argument(
        "--cloud-gpu-usd-per-hour", type=float, default=DEFAULT_CLOUD_GPU_USD_PER_HOUR
    )
    args = parser.parse_args()
    args.hosted_prices = HOSTED_PRICES  # priced from the claude-api skill's current table

    levels = [int(c) for c in args.concurrency.split(",")]
    cfg = generation.VLMConfig(base_url=args.base_url, model=args.model)
    if not generation.health(cfg):
        console.print(f"[red]no model server at {args.base_url}[/red]")
        return 1

    config.ensure_dirs()
    console.print(
        f"building {args.requests * len(levels)} distinct payloads "
        f"({args.pages} page images each, {args.max_tokens} output tokens fixed)…"
    )
    payloads = build_payloads(
        args.requests * len(levels) + args.warmup,
        args.pages,
        args.model,
        args.max_tokens,
        args.seed,
    )

    if args.warmup:
        console.print(f"warming up with {args.warmup} requests")
        for payload in payloads[: args.warmup]:
            loadtest.send(payload, args.base_url)
        payloads = payloads[args.warmup :]

    runs = []
    for index, concurrency in enumerate(levels):
        batch = payloads[index * args.requests : (index + 1) * args.requests]
        console.print(f"\n[bold]concurrency {concurrency}[/bold] — {len(batch)} requests")
        result = loadtest.run_load(batch, concurrency, args.base_url)
        summary = result.summary()
        summary["cost"] = cost_block(summary, args)
        runs.append(summary)
        console.print(
            f"  p50 {summary['latency_ms']['p50']:.0f} ms · "
            f"p95 {summary['latency_ms']['p95']:.0f} ms · "
            f"{summary['throughput_req_per_s']:.2f} req/s · "
            f"{summary['output_tokens_per_s']:.0f} out tok/s · "
            f"GPU {summary['gpu'].get('utilization_mean', 0):.0f}% · "
            f"cache hits {summary['engine'].get('prefix_cache_hit_rate')}"
        )

    table = Table(box=None, title="serving benchmark", title_justify="left")
    for column in (
        "concurrency",
        "p50 ms",
        "p95 ms",
        "p99 ms",
        "TTFT p50",
        "req/s",
        "out tok/s",
        "GPU %",
        "power W",
    ):
        table.add_column(column, justify="right")
    for summary in runs:
        table.add_row(
            str(summary["concurrency"]),
            f"{summary['latency_ms']['p50']:.0f}",
            f"{summary['latency_ms']['p95']:.0f}",
            f"{summary['latency_ms']['p99']:.0f}",
            f"{summary['ttft_ms']['p50']:.0f}",
            f"{summary['throughput_req_per_s']:.2f}",
            f"{summary['output_tokens_per_s']:.0f}",
            f"{summary['gpu'].get('utilization_mean', 0):.0f}",
            f"{summary['gpu'].get('power_w_mean', 0):.0f}",
        )
    console.print(table)

    cost_table = Table(box=None, title="cost per 1,000 queries", title_justify="left")
    cost_table.add_column("concurrency", justify="right")
    cost_table.add_column("GPU-seconds", justify="right")
    cost_table.add_column("electricity", justify="right")
    cost_table.add_column("cloud GPU rental", justify="right")
    for name in args.hosted_prices:
        cost_table.add_column(name, justify="right")
    for summary in runs:
        cost = summary["cost"]
        cost_table.add_row(
            str(summary["concurrency"]),
            f"{cost['gpu_seconds_per_1k']:.0f}",
            f"${cost['electricity_usd_per_1k']:.2f}",
            f"${cost['cloud_gpu_rental_usd_per_1k']:.2f}",
            *[f"${cost['hosted_api_usd_per_1k'][name]:.2f}" for name in args.hosted_prices],
        )
    console.print(cost_table)

    report = {
        "endpoint": args.base_url,
        "model": args.model,
        "quantization": "AWQ int4",
        "gpu": "NVIDIA RTX 3090 24GB",
        "workload": {
            "pages_per_query": args.pages,
            "max_tokens": args.max_tokens,
            "ignore_eos": True,
            "distinct_payload_per_request": True,
            "requests_per_level": args.requests,
        },
        "assumptions": {
            "kwh_price_usd": args.kwh_price,
            "system_overhead_factor": args.system_overhead,
            "cloud_gpu_usd_per_hour": args.cloud_gpu_usd_per_hour,
            "hosted_prices_usd_per_million_tokens": args.hosted_prices,
        },
        "runs": runs,
    }
    path = config.REPORTS_DIR / "serving.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    console.print(f"\n[green]wrote[/green] {path}")
    return 0


# Hosted vision-capable models to price the same workload against, USD per million tokens.
# Source: the bundled claude-api skill's current model table (cached 2026-06-24). Haiku is the
# fair capability comparison for a self-hosted 7B; Sonnet is the mid-tier reference.
#
# Comparability caveat, stated because it is the weak point of any such comparison: the token
# counts are vLLM's, using Qwen2.5-VL's image encoder (~1,700 tokens per 1.2 MP page here).
# Anthropic's documented image estimate is width*height/750, which for the same page is ~1,600
# tokens — within ~6%. So the hosted figures are estimates, but not loose ones.
HOSTED_PRICES: dict[str, dict[str, float]] = {
    "claude-haiku-4.5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
}

if __name__ == "__main__":
    raise SystemExit(main())
