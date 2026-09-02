"""Load generation and instrumentation for the serving benchmark.

Three things this has to get right, because each one silently flatters the numbers:

1. **Distinct payloads.** vLLM caches multimodal inputs and prompt prefixes. Replaying one
   query at concurrency 16 measures the cache, not the model — an early run reported 128 tok/s
   that way against 24 tok/s honest. Every request here carries a different question and
   different page images, and the prefix-cache hit rate is reported so the claim is checkable.
2. **Fixed output length.** Tokens/second is not comparable across runs whose answers differ in
   length, so the sweep pins `max_tokens` and sets `ignore_eos`.
3. **Client-side work outside the timer.** JPEG encoding and base64 of three page images costs
   tens of milliseconds; payloads are built before the clock starts.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import threading
import time
from dataclasses import dataclass, field

import requests


@dataclass
class Result:
    latency_ms: float
    ttft_ms: float | None
    prompt_tokens: int
    completion_tokens: int
    ok: bool
    error: str | None = None


@dataclass
class GpuSample:
    utilization: float
    memory_mb: float
    power_w: float


class GpuSampler:
    """Polls nvidia-smi in the background for the whole-card view.

    Whole-card rather than per-process on purpose: the question is whether the *box* saturates,
    and under Kubernetes the work runs in another container's namespace anyway.
    """

    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self.samples: list[GpuSample] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _poll(self) -> None:
        query = "utilization.gpu,memory.used,power.draw"
        while not self._stop.is_set():
            try:
                out = (
                    subprocess.run(
                        ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=True,
                    )
                    .stdout.strip()
                    .splitlines()[0]
                )
                utilization, memory, power = (float(p) for p in out.split(","))
                self.samples.append(GpuSample(utilization, memory, power))
            except Exception:  # noqa: BLE001 - a dropped sample must not kill the benchmark
                pass
            self._stop.wait(self.interval)

    def __enter__(self):
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def summary(self) -> dict:
        if not self.samples:
            return {}
        utilization = [s.utilization for s in self.samples]
        power = [s.power_w for s in self.samples]
        return {
            "samples": len(self.samples),
            "utilization_mean": round(statistics.mean(utilization), 1),
            "utilization_p95": round(percentile(utilization, 95), 1),
            "utilization_max": round(max(utilization), 1),
            "memory_mb_max": round(max(s.memory_mb for s in self.samples)),
            "power_w_mean": round(statistics.mean(power), 1),
            "power_w_max": round(max(power), 1),
        }

    def energy_wh(self, seconds: float) -> float:
        if not self.samples:
            return 0.0
        return statistics.mean([s.power_w for s in self.samples]) * seconds / 3600


def percentile(values, q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(round(q / 100 * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[index]


def scrape_metrics(base_url: str) -> dict[str, float]:
    """Pull vLLM's Prometheus counters. Deltas across a run say what the engine actually did."""
    url = base_url.replace("/v1", "/metrics")
    wanted = (
        "vllm:prefix_cache_queries_total",
        "vllm:prefix_cache_hits_total",
        "vllm:num_requests_running",
        "vllm:num_requests_waiting",
        "vllm:generation_tokens_total",
        "vllm:prompt_tokens_total",
        "vllm:request_queue_time_seconds_sum",
        "vllm:request_queue_time_seconds_count",
    )
    out: dict[str, float] = {}
    try:
        text = requests.get(url, timeout=10).text
    except requests.RequestException:
        return out
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        name = line.split("{")[0].split(" ")[0]
        if name in wanted:
            try:
                out[name] = out.get(name, 0.0) + float(line.rsplit(" ", 1)[1])
            except (ValueError, IndexError):
                continue
    return out


def send(payload: dict, base_url: str, timeout: float = 300.0) -> Result:
    """One streamed chat completion; TTFT is the first token off the wire."""
    started = time.perf_counter()
    ttft = None
    prompt_tokens = completion_tokens = 0
    try:
        with requests.post(
            f"{base_url}/chat/completions", json=payload, timeout=timeout, stream=True
        ) as response:
            response.raise_for_status()
            for raw in response.iter_lines():
                if not raw or not raw.startswith(b"data: "):
                    continue
                chunk = raw[6:]
                if chunk == b"[DONE]":
                    break
                body = json.loads(chunk)
                choices = body.get("choices") or []
                if ttft is None and choices and choices[0].get("delta", {}).get("content"):
                    ttft = (time.perf_counter() - started) * 1000
                if body.get("usage"):
                    prompt_tokens = body["usage"].get("prompt_tokens", 0)
                    completion_tokens = body["usage"].get("completion_tokens", 0)
    except Exception as exc:  # noqa: BLE001
        return Result((time.perf_counter() - started) * 1000, ttft, 0, 0, False, str(exc)[:120])
    return Result(
        (time.perf_counter() - started) * 1000, ttft, prompt_tokens, completion_tokens, True
    )


@dataclass
class LoadResult:
    concurrency: int
    results: list[Result] = field(default_factory=list)
    wall_seconds: float = 0.0
    gpu: dict = field(default_factory=dict)
    metrics_delta: dict = field(default_factory=dict)

    def summary(self) -> dict:
        ok = [r for r in self.results if r.ok]
        latencies = [r.latency_ms for r in ok]
        ttfts = [r.ttft_ms for r in ok if r.ttft_ms is not None]
        completion = sum(r.completion_tokens for r in ok)
        prompt = sum(r.prompt_tokens for r in ok)
        return {
            "concurrency": self.concurrency,
            "requests": len(self.results),
            "failed": len(self.results) - len(ok),
            "wall_seconds": round(self.wall_seconds, 2),
            "throughput_req_per_s": round(len(ok) / self.wall_seconds, 3)
            if self.wall_seconds
            else 0,
            "output_tokens_per_s": round(completion / self.wall_seconds, 1)
            if self.wall_seconds
            else 0,
            "prompt_tokens_per_s": round(prompt / self.wall_seconds, 1) if self.wall_seconds else 0,
            "latency_ms": {
                "p50": round(percentile(latencies, 50), 1),
                "p95": round(percentile(latencies, 95), 1),
                "p99": round(percentile(latencies, 99), 1),
                "mean": round(statistics.mean(latencies), 1) if latencies else 0,
            },
            "ttft_ms": {
                "p50": round(percentile(ttfts, 50), 1),
                "p95": round(percentile(ttfts, 95), 1),
            },
            "tokens": {"prompt_total": prompt, "completion_total": completion},
            "gpu": self.gpu,
            "engine": self.metrics_delta,
        }


def run_load(payloads: list[dict], concurrency: int, base_url: str) -> LoadResult:
    """Issue `payloads` with `concurrency` workers in flight, one payload each."""
    from concurrent.futures import ThreadPoolExecutor

    before = scrape_metrics(base_url)
    result = LoadResult(concurrency=concurrency)
    with GpuSampler() as sampler:
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            result.results = list(pool.map(lambda p: send(p, base_url), payloads))
        result.wall_seconds = time.perf_counter() - started
    result.gpu = sampler.summary()
    result.gpu["energy_wh"] = round(sampler.energy_wh(result.wall_seconds), 4)

    after = scrape_metrics(base_url)
    queries = after.get("vllm:prefix_cache_queries_total", 0) - before.get(
        "vllm:prefix_cache_queries_total", 0
    )
    hits = after.get("vllm:prefix_cache_hits_total", 0) - before.get(
        "vllm:prefix_cache_hits_total", 0
    )
    result.metrics_delta = {
        "prefix_cache_queries": queries,
        "prefix_cache_hits": hits,
        "prefix_cache_hit_rate": round(hits / queries, 3) if queries else None,
        "queue_time_seconds_total": round(
            after.get("vllm:request_queue_time_seconds_sum", 0)
            - before.get("vllm:request_queue_time_seconds_sum", 0),
            3,
        ),
    }
    return result
