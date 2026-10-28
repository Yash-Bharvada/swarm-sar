"""Strict GPU host, repository, and expert-data readiness gate."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import ray
import torch

from swarm_sar.learning.demonstrations import dataset_summary, validate_dataset
from swarm_sar.policy_contract import policy_contract


EXPECTED_MANIFEST = "b4afe76df70480e24dba15ecc6b526044647fa94fd2efffbeefdbb2271fd2857"
EXPECTED_CONTRACT = "c5dff01368e1bb3a77112884c5d545457830097b11aefe54e0d412fc874c57c5"


def command(*parts: str) -> str:
    return subprocess.check_output(parts, text=True, stderr=subprocess.STDOUT).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("results/expert_train_gpu_v1"))
    parser.add_argument("--allow-cpu", action="store_true", help="Mac-only diagnostic; GPU handoff must omit this")
    parser.add_argument("--minimum-free-gib", type=float, default=50.0)
    args = parser.parse_args()
    checks = {}
    failures = []
    checks["python"] = sys.version.split()[0]
    checks["torch"] = torch.__version__
    checks["ray"] = ray.__version__
    checks["git_commit"] = command("git", "rev-parse", "HEAD")
    checks["git_status"] = command("git", "status", "--porcelain")
    if checks["git_status"]:
        failures.append("git_worktree_not_clean")
    checks["policy_contract_sha256"] = policy_contract()["sha256"]
    if checks["policy_contract_sha256"] != EXPECTED_CONTRACT:
        failures.append("policy_contract_hash_mismatch")
    if not args.dataset.exists():
        failures.append("expert_dataset_missing")
    else:
        validate_dataset(args.dataset)
        summary = dataset_summary(args.dataset)
        checks["expert_dataset"] = summary
        if summary["manifest_sha256"] != EXPECTED_MANIFEST:
            failures.append("expert_manifest_hash_mismatch")
        if summary["rows"] != 811652 or summary["episode_count"] != 2000:
            failures.append("expert_dataset_size_mismatch")
    checks["cuda_available"] = torch.cuda.is_available()
    checks["cuda_device_count"] = torch.cuda.device_count()
    if torch.cuda.is_available():
        checks["cuda_devices"] = [
            {
                "name": torch.cuda.get_device_name(index),
                "memory_bytes": torch.cuda.get_device_properties(index).total_memory,
            }
            for index in range(torch.cuda.device_count())
        ]
        if checks["cuda_devices"][0]["memory_bytes"] < 20 * 1024**3:
            failures.append("gpu_memory_below_20_gib")
    elif not args.allow_cpu:
        failures.append("cuda_unavailable")
    checks["nvidia_smi_present"] = shutil.which("nvidia-smi") is not None
    checks["free_disk_bytes"] = shutil.disk_usage(Path.cwd()).free
    if checks["free_disk_bytes"] < args.minimum_free_gib * 1024**3:
        failures.append(f"free_disk_below_{args.minimum_free_gib:g}_gib")
    payload = {"passed": not failures, "failures": failures, "checks": checks}
    print(json.dumps(payload, indent=2))
    if failures:
        raise SystemExit("FAIL: " + ", ".join(failures))


if __name__ == "__main__":
    main()
