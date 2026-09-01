"""Step 0 — environment report.

Records the machine this project's numbers were produced on: Python, pinned package versions,
GPU + driver, free disk, HF cache. Written to reports/env_report.json so the serving numbers in
step 7 can be read next to the hardware that produced them.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from huggingface_hub import constants as hf_constants
from huggingface_hub import get_token
from rich.console import Console
from rich.table import Table

from visual_rag import config

console = Console()

TRACKED_PACKAGES = [
    "datasets",
    "huggingface-hub",
    "pandas",
    "pyarrow",
    "numpy",
    "pillow",
    # present only after `uv sync --extra retrieval`
    "torch",
    "transformers",
    "sentence-transformers",
    "colpali-engine",
]


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in TRACKED_PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def gpu_info() -> dict:
    """Query nvidia-smi directly: works whether or not torch is installed yet."""
    if shutil.which("nvidia-smi") is None:
        return {"available": False, "reason": "nvidia-smi not found"}
    query = "name,memory.total,memory.used,driver_version,compute_cap"
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "reason": str(exc)}

    gpus = []
    for line in out.splitlines():
        name, total, used, driver, cap = (p.strip() for p in line.split(","))
        gpus.append(
            {
                "name": name,
                "memory_total": total,
                "memory_used": used,
                "driver_version": driver,
                "compute_capability": cap,
            }
        )
    return {"available": True, "count": len(gpus), "gpus": gpus}


def torch_info() -> dict:
    try:
        import torch
    except ImportError:
        return {"installed": False, "note": "install with `uv sync --extra retrieval`"}
    return {
        "installed": True,
        "version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_version": torch.version.cuda,
        "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
    }


def disk_info(path: Path) -> dict:
    usage = shutil.disk_usage(path)
    return {
        "path": str(path),
        "total_gb": round(usage.total / 1e9, 1),
        "free_gb": round(usage.free / 1e9, 1),
    }


def hf_cache_info() -> dict:
    cache = Path(hf_constants.HF_HUB_CACHE)
    size_gb = None
    if cache.exists():
        size_gb = round(sum(f.stat().st_size for f in cache.rglob("*") if f.is_file()) / 1e9, 2)
    return {
        "hub_cache": str(cache),
        "exists": cache.exists(),
        "size_gb": size_gb,
        "token_present": bool(get_token()),
    }


def main() -> int:
    config.ensure_dirs()
    report = {
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "in_venv": sys.prefix != sys.base_prefix,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "packages": package_versions(),
        "gpu": gpu_info(),
        "torch": torch_info(),
        "disk": disk_info(config.PROJECT_ROOT),
        "huggingface": hf_cache_info(),
    }

    table = Table(title="environment", show_header=False, box=None)
    table.add_column(style="cyan")
    table.add_column()
    table.add_row("python", f"{report['python']['version']} (venv: {report['python']['in_venv']})")
    table.add_row("platform", f"{platform.system()} {platform.release()} / {platform.machine()}")
    if report["gpu"]["available"]:
        for gpu in report["gpu"]["gpus"]:
            table.add_row(
                "gpu",
                f"{gpu['name']} — {gpu['memory_total']} "
                f"(in use {gpu['memory_used']}), driver {gpu['driver_version']}",
            )
    else:
        table.add_row("gpu", f"[red]none[/red] ({report['gpu']['reason']})")
    table.add_row("torch", report["torch"].get("version") or "not installed (step 2+)")
    table.add_row("disk", f"{report['disk']['free_gb']} GB free at {report['disk']['path']}")
    table.add_row(
        "hf cache",
        f"{report['huggingface']['hub_cache']} "
        f"({report['huggingface']['size_gb']} GB, token: "
        f"{'yes' if report['huggingface']['token_present'] else 'no'})",
    )
    installed = {k: v for k, v in report["packages"].items() if v}
    table.add_row("packages", ", ".join(f"{k}=={v}" for k, v in installed.items()))
    console.print(table)

    out = config.REPORTS_DIR / "env_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    console.print(f"\n[green]wrote[/green] {out}")

    problems = []
    if not report["gpu"]["available"]:
        problems.append("no GPU visible — steps 3/5/6 need one")
    if report["disk"]["free_gb"] < 15:
        problems.append("less than 15 GB free; the corpus alone is ~2 GB")
    for problem in problems:
        console.print(f"[yellow]warning:[/yellow] {problem}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
