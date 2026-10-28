"""Verify source/data identity and execute an actual CUDA backward pass."""

import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import torch

from swarm_sar.learning.demonstrations import dataset_summary
from swarm_sar.learning.release import atomic_json, verify_source_manifest
from swarm_sar.policy_contract import policy_contract
from swarm_sar.utils.config import load_config


ROOT = Path(__file__).resolve().parents[1]


def host_resources():
    cpus = float(os.cpu_count() or 1)
    if hasattr(os, "sched_getaffinity"):
        cpus = min(cpus, len(os.sched_getaffinity(0)))
    quota_path = Path("/sys/fs/cgroup/cpu.max")
    if quota_path.exists():
        quota, period = quota_path.read_text().split()
        if quota != "max":
            cpus = min(cpus, int(quota) / int(period))
    memory = int(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    memory_limit = Path("/sys/fs/cgroup/memory.max")
    if memory_limit.exists() and memory_limit.read_text().strip().isdigit():
        memory = min(memory, int(memory_limit.read_text()))
    return {"available_cpu_capacity": cpus, "memory_capacity_bytes": memory}


def preflight(dataset: Path, *, allow_cpu=False, allow_dirty=False, minimum_free_gib=50.0, host_only=False):
    failures = []
    checks = {
        "python": sys.version.split()[0],
        "versions": {name: importlib.metadata.version(name) for name in ("torch", "ray", "numpy", "gymnasium")},
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "git_status": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip(),
        "policy_contract_sha256": policy_contract()["sha256"],
        "diagnostic": bool(allow_cpu or allow_dirty or minimum_free_gib < 50),
    }
    if checks["git_status"] and not allow_dirty:
        failures.append("git_worktree_not_clean")
    checks["host_resources"] = host_resources()
    requested_cpus = int(load_config(ROOT / "configs/training_gpu_a5000.yaml")["num_cpus"])
    if not allow_cpu and checks["host_resources"]["available_cpu_capacity"] < requested_cpus:
        failures.append(f"host_cpu_capacity_below_profile_{requested_cpus}")
    if not allow_cpu and checks["host_resources"]["memory_capacity_bytes"] < 32 * 1024**3:
        failures.append("host_memory_capacity_below_32_gib")
    try:
        checks["release"] = verify_source_manifest(ROOT)
    except (ValueError, OSError) as error:
        failures.append(f"release_manifest:{error}")
    checks["host_only"] = host_only
    if not host_only:
        try:
            summary = dataset_summary(dataset, display_path="results/expert_train_gpu_v2")
            checks["expert_dataset"] = summary
            expected = json.loads((ROOT / "artifacts/gpu_v2/expert_dataset_summary.json").read_text())
            if summary != expected:
                failures.append("expert_dataset_does_not_match_pinned_summary")
        except (OSError, ValueError, KeyError) as error:
            failures.append(f"expert_dataset:{error}")
    checks["cuda_available"] = torch.cuda.is_available()
    checks["torch_cuda_runtime"] = torch.version.cuda
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        checks["gpu"] = {"name": props.name, "total_memory_bytes": props.total_memory}
        if props.total_memory < 20 * 1024**3:
            failures.append("gpu_memory_below_20_gib")
        try:
            torch.cuda.reset_peak_memory_stats()
            matrix = torch.randn(512, 512, device="cuda", requires_grad=True)
            loss = (matrix @ matrix.T).square().mean()
            loss.backward()
            torch.cuda.synchronize()
            checks["cuda_backward_pass"] = bool(torch.isfinite(matrix.grad).all())
            checks["cuda_peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
            if not checks["cuda_backward_pass"]:
                failures.append("cuda_backward_nonfinite")
            del matrix, loss
            torch.cuda.empty_cache()
        except RuntimeError as error:
            failures.append(f"cuda_backward:{error}")
    elif not allow_cpu:
        failures.append("cuda_unavailable")
    if shutil.which("nvidia-smi"):
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20,
        )
        checks["nvidia_smi"] = result.stdout.strip() or result.stderr.strip()
        if result.returncode:
            failures.append("nvidia_smi_failed")
    checks["free_disk_bytes"] = shutil.disk_usage(dataset.parent if dataset.parent.exists() else ROOT).free
    if checks["free_disk_bytes"] < minimum_free_gib * 1024**3:
        failures.append("insufficient_disk_space")
    return {"passed": not failures, "failures": failures, "checks": checks}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("results/expert_train_gpu_v2"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--host-only", action="store_true", help="Check source and CUDA before generating missing data")
    parser.add_argument("--allow-cpu", action="store_true", help="Mac diagnostic only")
    parser.add_argument("--allow-dirty", action="store_true", help="Mac diagnostic only; source hashes still verified")
    parser.add_argument("--minimum-free-gib", type=float, default=50.0)
    args = parser.parse_args()
    report = preflight(args.dataset, allow_cpu=args.allow_cpu, allow_dirty=args.allow_dirty, minimum_free_gib=args.minimum_free_gib, host_only=args.host_only)
    if args.output:
        atomic_json(args.output, report)
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
