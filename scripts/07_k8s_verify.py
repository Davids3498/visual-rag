"""Step 6 — verify the Kubernetes deployment actually schedules and serves.

"The YAML applied cleanly" is not evidence. This checks the things that are actually easy to
get wrong on a GPU node: that the device plugin is advertising `nvidia.com/gpu`, that the pod
was scheduled *with* a GPU rather than silently without one, that the model server passed its
startup probe, and that a real multimodal request comes back through the Service.

Writes reports/k8s.json.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime

from rich.console import Console
from rich.table import Table

from visual_rag import config, generation

console = Console()
NAMESPACE = "visual-rag"


def kubectl(*args, timeout: int = 60) -> tuple[int, str]:
    result = subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=timeout)
    return result.returncode, (result.stdout or result.stderr).strip()


def kubectl_json(*args) -> dict | None:
    code, out = kubectl(*args, "-o", "json")
    if code != 0:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def check(name: str, ok: bool, detail: str, checks: list) -> bool:
    checks.append({"check": name, "pass": bool(ok), "detail": detail})
    return bool(ok)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-port", type=int, default=30800)
    parser.add_argument(
        "--host",
        default=None,
        help="node address for the NodePort (default: auto-detect, minikube ip then localhost)",
    )
    parser.add_argument("--skip-generation", action="store_true")
    args = parser.parse_args()

    config.ensure_dirs()
    checks: list[dict] = []
    facts: dict = {}

    if shutil.which("kubectl") is None:
        console.print("[red]kubectl not found[/red]")
        return 1
    # `kubectl version` succeeds with no cluster (it prints the client build), so ask the
    # API server something only it can answer.
    code, out = kubectl("get", "--raw=/readyz", timeout=30)
    if code != 0:
        console.print(
            "[red]no reachable cluster[/red] — "
            f"{out.splitlines()[0] if out else 'kubectl could not reach an API server'}\n"
            "bring one up with:  make k8s-install  (needs sudo, one time)"
        )
        return 1

    # --- the node must be advertising GPUs, or nothing else can work
    nodes = kubectl_json("get", "nodes") or {"items": []}
    node = nodes["items"][0] if nodes["items"] else {}
    capacity = node.get("status", {}).get("capacity", {})
    allocatable = node.get("status", {}).get("allocatable", {})
    gpus = int(allocatable.get("nvidia.com/gpu", 0))
    facts["node"] = {
        "name": node.get("metadata", {}).get("name"),
        "kubelet": node.get("status", {}).get("nodeInfo", {}).get("kubeletVersion"),
        "runtime": node.get("status", {}).get("nodeInfo", {}).get("containerRuntimeVersion"),
        "gpu_capacity": capacity.get("nvidia.com/gpu"),
        "gpu_allocatable": allocatable.get("nvidia.com/gpu"),
    }
    check(
        "node advertises nvidia.com/gpu",
        gpus > 0,
        f"{gpus} allocatable (1 physical card; >1 means time-slicing is active)",
        checks,
    )

    # How the GPU reaches the container differs by cluster: k3s routes GPU pods through an
    # `nvidia` RuntimeClass, while minikube's docker driver makes the NVIDIA runtime the node
    # default. Neither is required for correctness — what matters is that a pod requesting
    # `nvidia.com/gpu` actually gets a device, which the checks below establish.
    runtime_classes = kubectl_json("get", "runtimeclass") or {"items": []}
    names = [item["metadata"]["name"] for item in runtime_classes["items"]]
    facts["runtime_classes"] = names
    facts["gpu_delivery"] = "nvidia RuntimeClass" if "nvidia" in names else "node default runtime"

    plugin = kubectl_json("get", "daemonset", "-n", "kube-system", "nvidia-device-plugin-daemonset")
    ready = (plugin or {}).get("status", {}).get("numberReady", 0)
    check("device plugin daemonset ready", ready >= 1, f"{ready} ready", checks)

    # --- workloads
    pods = kubectl_json("get", "pods", "-n", NAMESPACE) or {"items": []}
    pod_rows = []
    vllm_pod = None
    for pod in pods["items"]:
        statuses = pod.get("status", {}).get("containerStatuses") or []
        row = {
            "name": pod["metadata"]["name"],
            "phase": pod["status"].get("phase"),
            "ready": all(s.get("ready") for s in statuses) and bool(statuses),
            "restarts": sum(s.get("restartCount", 0) for s in statuses),
            "node": pod["spec"].get("nodeName"),
            "gpu_limit": (
                pod["spec"]["containers"][0]
                .get("resources", {})
                .get("limits", {})
                .get("nvidia.com/gpu")
            ),
        }
        started = pod["status"].get("startTime")
        conditions = {c["type"]: c for c in pod["status"].get("conditions", [])}
        if started and "Ready" in conditions and conditions["Ready"].get("lastTransitionTime"):
            fmt = "%Y-%m-%dT%H:%M:%SZ"
            row["seconds_to_ready"] = round(
                (
                    datetime.strptime(conditions["Ready"]["lastTransitionTime"], fmt)
                    - datetime.strptime(started, fmt)
                ).total_seconds()
            )
        pod_rows.append(row)
        if pod["metadata"]["labels"].get("app") == "vllm":
            vllm_pod = row
    facts["pods"] = pod_rows

    check(
        "pgvector pod ready",
        any(r["ready"] for r in pod_rows if r["name"].startswith("pgvector")),
        next((r["name"] for r in pod_rows if r["name"].startswith("pgvector")), "not found"),
        checks,
    )
    check(
        "vllm pod ready",
        bool(vllm_pod and vllm_pod["ready"]),
        f"{vllm_pod['name']} ({vllm_pod.get('seconds_to_ready', '?')}s to ready, "
        f"{vllm_pod['restarts']} restarts)"
        if vllm_pod
        else "not found",
        checks,
    )
    check(
        "vllm pod holds a GPU allocation",
        bool(vllm_pod and vllm_pod["gpu_limit"]),
        f"nvidia.com/gpu: {vllm_pod['gpu_limit']}" if vllm_pod else "no pod",
        checks,
    )

    # --- does it actually serve, through the Service rather than the container port
    #
    # With minikube's docker driver the NodePort lives on the node container's IP, not on
    # localhost; on k3s the node *is* localhost. Try both rather than making the caller know.
    hosts = [args.host] if args.host else []
    if not hosts:
        code, out = kubectl(
            "get",
            "nodes",
            "-o",
            "jsonpath={.items[0].status.addresses[?(@.type=='InternalIP')].address}",
        )
        if code == 0 and out:
            hosts.append(out.strip())
        hosts.append("localhost")

    serving, base_url = False, f"http://{hosts[0]}:{args.node_port}/v1"
    for host in hosts:
        candidate = f"http://{host}:{args.node_port}/v1"
        if generation.health(generation.VLMConfig(base_url=candidate)):
            serving, base_url = True, candidate
            break
    cfg = generation.VLMConfig(base_url=base_url)
    check("model server answers /health via NodePort", serving, base_url, checks)

    models = []
    if serving:
        import requests

        try:
            models = [
                m["id"] for m in requests.get(f"{base_url}/models", timeout=10).json()["data"]
            ]
        except Exception as exc:  # noqa: BLE001
            models = [f"error: {exc}"]
    facts["served_models"] = models

    if serving and not args.skip_generation:
        from visual_rag import data

        eval_set = data.load_eval_set()
        corpus_ds, id_to_row = data.load_corpus_images()
        meta = eval_set.corpus.set_index("corpus_id")
        run_path = config.DATA_DIR / "runs" / "visual_two_stage.json"
        run = json.loads(run_path.read_text())
        query_id = int(next(iter(run["run"])))
        query = eval_set.queries.loc[eval_set.queries.query_id == query_id, "query"].iloc[0]
        top = sorted(run["run"][str(query_id)].items(), key=lambda kv: -kv[1])[:1]
        pages = [
            {
                "corpus_id": int(cid),
                "image": corpus_ds[id_to_row[int(cid)]]["image"],
                "doc_id": meta.loc[int(cid), "doc_id"],
                "page_number": int(meta.loc[int(cid), "page_number_in_doc"]),
            }
            for cid, _ in top
        ]
        result = generation.answer(query, pages, cfg)
        facts["smoke_test"] = {
            "query_id": query_id,
            "latency_ms": round(result.latency_ms, 1),
            "cited": result.cited_pages,
            "answer_preview": result.text[:200],
        }
        check(
            "end-to-end multimodal request through the cluster",
            bool(result.text),
            f"{result.latency_ms:.0f} ms, cited {result.cited_pages}",
            checks,
        )

    table = Table(box=None)
    table.add_column("", width=4)
    table.add_column("check", style="cyan")
    table.add_column("detail")
    for entry in checks:
        table.add_row(
            "[green]ok[/green]" if entry["pass"] else "[red]FAIL[/red]",
            entry["check"],
            entry["detail"],
        )
    console.print(table)

    verdict = "PASS" if all(entry["pass"] for entry in checks) else "FAIL"
    console.print(f"\n[bold]{verdict}[/bold]")

    report = {"verdict": verdict, "checks": checks, **facts}
    path = config.REPORTS_DIR / "k8s.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    console.print(f"[green]wrote[/green] {path}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
