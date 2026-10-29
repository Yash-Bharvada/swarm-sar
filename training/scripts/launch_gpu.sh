#!/usr/bin/env bash
# One-command entrypoint. Inspect logs in training/runs/gpu_pipeline_* on the host.
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "GPU launch requires the Linux NVIDIA host. Use run_gpu_pipeline.py --plan on the Mac."
  exit 2
fi
if [[ "$(git branch --show-current)" != "rashiyaom" ]]; then
  echo "Checkout the audited rashiyaom branch before launch."
  exit 2
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Repository contains uncommitted changes. Use a clean clone of rashiyaom."
  exit 2
fi
command -v nvidia-smi >/dev/null || { echo "NVIDIA driver tools are missing."; exit 2; }
command -v timeout >/dev/null || { echo "GNU timeout is required for bounded setup."; exit 2; }
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
if [[ "$(df -Pk . | awk 'NR==2 {print $4}')" -lt 52428800 ]]; then
  echo "At least 50 GiB free space is required before installing CUDA packages."
  exit 2
fi
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
SWARM_PIPELINE_STARTED_EPOCH="$(date +%s)"
mkdir -p training/runs
SWARM_BOOTSTRAP_LOG="training/runs/gpu_bootstrap_${SWARM_PIPELINE_STARTED_EPOCH}.log"
if [[ ! -x .venv-gpu/bin/python ]]; then
  python3 -m venv .venv-gpu
fi
timeout --signal=INT --kill-after=60s 1800s .venv-gpu/bin/python -m pip install torch==2.14.1+cu126 --index-url https://download.pytorch.org/whl/cu126 2>&1 | tee -a "$SWARM_BOOTSTRAP_LOG"
timeout --signal=INT --kill-after=60s 1800s .venv-gpu/bin/python -m pip install -r training/requirements-gpu.lock 2>&1 | tee -a "$SWARM_BOOTSTRAP_LOG"
timeout --signal=INT --kill-after=60s 300s .venv-gpu/bin/python -m pip install --no-deps -e . 2>&1 | tee -a "$SWARM_BOOTSTRAP_LOG"
exec .venv-gpu/bin/python training/scripts/run_gpu_pipeline.py --started-epoch "$SWARM_PIPELINE_STARTED_EPOCH" "$@"
