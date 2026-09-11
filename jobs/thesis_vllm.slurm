#!/bin/bash
# Thesis counted-path job. Account paths and GPU feature are submit-time fills.
# Not the repo-root Ollama smoke.
#SBATCH --job-name=thesis-vllm
#SBATCH -p gpu
#SBATCH -G 1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH -t 12:00:00
#SBATCH -o jobs/thesis_vllm_%j.out
#SBATCH -e jobs/thesis_vllm_%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=jannik.endress@stanford.edu
#SBATCH --signal=B:USR1@300
# Submit-time GPU feature example: #SBATCH -C "GPU_MODEL:H200"

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"

module purge
# Load the vLLM stack after purge (module or container; submit-time fill).
# module load apptainer

SCRATCH="/scratch/shared/${USER}"
CAMPAIGN="${CAMPAIGN:-slate-a}"
ARTIFACT_ROOT="${SCRATCH}/runs/${CAMPAIGN}"
VLLM_LOG="${SCRATCH}/vllm/thesis_${SLURM_JOB_ID}.log"
HF_HOME="${SCRATCH}/models"
export HF_HOME
mkdir -p "${ARTIFACT_ROOT}" "$(dirname "${VLLM_LOG}")"

PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
export PORT
export BASE_URL="http://127.0.0.1:${PORT}/v1"
export SERVE_WAIT_TIMEOUT="${SERVE_WAIT_TIMEOUT:-600}"

VLLM_PID=""
RUNNER_PID=""

stop_vllm() {
  if [[ -n "${VLLM_PID}" ]] && kill -0 "${VLLM_PID}" 2>/dev/null; then
    kill "${VLLM_PID}" 2>/dev/null || true
    wait "${VLLM_PID}" 2>/dev/null || true
  fi
}

on_pretimeout() {
  if [[ -n "${RUNNER_PID}" ]] && kill -0 "${RUNNER_PID}" 2>/dev/null; then
    kill -TERM "${RUNNER_PID}" 2>/dev/null || true
    wait "${RUNNER_PID}" 2>/dev/null || true
  fi
  stop_vllm
  exit 0
}

trap on_pretimeout USR1 TERM INT

vllm serve "${HF_MODEL:?set HF_MODEL}" \
  --host 127.0.0.1 \
  --port "${PORT}" \
  --tensor-parallel-size "${TP:-1}" \
  >"${VLLM_LOG}" 2>&1 &
VLLM_PID=$!

# Wait until /v1/models answers within SERVE_WAIT_TIMEOUT.
python3 - <<'PY'
import os, sys, time, urllib.request
url = os.environ["BASE_URL"] + "/models"
timeout = float(os.environ["SERVE_WAIT_TIMEOUT"])
deadline = time.time() + timeout
last = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status < 500:
                sys.exit(0)
            last = resp.status
    except Exception as exc:
        last = exc
    time.sleep(2)
print(f"timed out waiting for {url}: {last}", file=sys.stderr)
sys.exit(1)
PY

python3 run_main.py \
  --model "${MODEL:?set MODEL}" \
  --program "${PROGRAM:-emergence}" \
  --artifact-root "${ARTIFACT_ROOT}" \
  --base-url "${BASE_URL}" \
  ${SEED_FROM:+--seed-from "${SEED_FROM}"} \
  ${SEED_TO:+--seed-to "${SEED_TO}"} &
RUNNER_PID=$!
wait "${RUNNER_PID}"
stop_vllm
