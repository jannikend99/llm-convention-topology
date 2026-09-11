#!/bin/bash
# Thesis counted-path job. vLLM pin: v0.28.0 (stable as of 2026-09-11).
# Prefer VLLM_SIF=${SCRATCH}/images/vllm-openai-v0.28.0.sif after apptainer pull.
# Override with VLLM_MODULE / VLLM_SIF / VLLM_LAUNCH. #SBATCH -C is an operator fill after a fit.
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
# Operator GPU feature after fit (leave commented until then):
# #SBATCH -C "GPU_MODEL:...."

set -euo pipefail
cd "${SLURM_SUBMIT_DIR}"

SCRATCH="/scratch/shared/${USER}"
if [[ ! -d "${SCRATCH}" && -d "/yen/scratch/shared/${USER}" ]]; then
  SCRATCH="/yen/scratch/shared/${USER}"
fi
if SCRATCH_REAL="$(readlink -f "${SCRATCH}" 2>/dev/null)" && [[ -d "${SCRATCH_REAL}" ]]; then
  SCRATCH="${SCRATCH_REAL}"
fi
VLLM_PIN="${VLLM_PIN:-v0.28.0}"
DEFAULT_SIF="${SCRATCH}/images/vllm-openai-${VLLM_PIN}.sif"
HF_HOME="${SCRATCH}/models"
export HF_HOME
export HUGGINGFACE_HUB_CACHE="${HF_HOME}/hub"
export TRANSFORMERS_CACHE="${HF_HOME}/transformers"
export HF_HUB_CACHE="${HF_HOME}/hub"
export XDG_CACHE_HOME="${HF_HOME}/xdg"
export TMPDIR="${SCRATCH}/tmp"
export HOME="${SCRATCH}/container-home"
export FLASHINFER_WORKSPACE_DIR="${SCRATCH}/flashinfer"
export TRITON_CACHE_DIR="${SCRATCH}/triton"
export TORCHINDUCTOR_CACHE_DIR="${SCRATCH}/torchinductor"
mkdir -p "${HF_HOME}" "${HUGGINGFACE_HUB_CACHE}" "${TRANSFORMERS_CACHE}" "${XDG_CACHE_HOME}" "${TMPDIR}" \
  "${HOME}" "${FLASHINFER_WORKSPACE_DIR}" "${TRITON_CACHE_DIR}" "${TORCHINDUCTOR_CACHE_DIR}"

module purge

# Client venv: requirements.txt needs networkx>=3.6 (Python 3.11+). Yen /usr/bin/python3 is 3.10.12.
PYTHON_MODULE="${PYTHON_MODULE:-python/3.11.3}"
module load "${PYTHON_MODULE}"

if [[ -z "${VLLM_MODULE:-}" && -z "${VLLM_SIF:-}" && -z "${VLLM_LAUNCH:-}" && -f "${DEFAULT_SIF}" ]]; then
  VLLM_SIF="${DEFAULT_SIF}"
fi

if [[ -n "${VLLM_MODULE:-}" ]]; then
  module load "${VLLM_MODULE}"
elif [[ -n "${VLLM_SIF:-}" ]]; then
  module load apptainer
elif [[ -n "${VLLM_LAUNCH:-}" ]]; then
  :
else
  echo "vLLM launch unset: pin is ${VLLM_PIN}. Pull docker://vllm/vllm-openai:${VLLM_PIN} to ${DEFAULT_SIF}, or export VLLM_MODULE, VLLM_SIF, or VLLM_LAUNCH, then resubmit." >&2
  exit 1
fi

if [[ -n "${VLLM_LAUNCH:-}" ]]; then
  read -r -a VLLM_BIN <<< "${VLLM_LAUNCH}"
elif [[ -n "${VLLM_SIF:-}" ]]; then
  # GPU nodes expose /scratch as a read-only mount. Bind the real shared tree and
  # drop host cache env so Hugging Face does not mkdir /scratch.
  VLLM_BIN=(
    apptainer exec --nv --cleanenv
    --bind "${SCRATCH}:${SCRATCH}"
    --env "HF_HOME=${HF_HOME}"
    --env "HUGGINGFACE_HUB_CACHE=${HUGGINGFACE_HUB_CACHE}"
    --env "TRANSFORMERS_CACHE=${TRANSFORMERS_CACHE}"
    --env "HF_HUB_CACHE=${HF_HUB_CACHE}"
    --env "XDG_CACHE_HOME=${XDG_CACHE_HOME}"
    --env "TMPDIR=${TMPDIR}"
    --env "HOME=${HOME}"
    --env "FLASHINFER_WORKSPACE_DIR=${FLASHINFER_WORKSPACE_DIR}"
    --env "TRITON_CACHE_DIR=${TRITON_CACHE_DIR}"
    --env "TORCHINDUCTOR_CACHE_DIR=${TORCHINDUCTOR_CACHE_DIR}"
    "${VLLM_SIF}" vllm
  )
else
  VLLM_BIN=(vllm)
fi

CAMPAIGN="${CAMPAIGN:-technical-smoke}"
ARTIFACT_ROOT="${SCRATCH}/runs/${CAMPAIGN}"
VENV="${SCRATCH}/venvs/thesis"
VLLM_LOG="${SCRATCH}/vllm/thesis_${SLURM_JOB_ID}.log"

: "${MODEL:?set MODEL to a config.yaml shorthand (from --print-jobs or a fit hand flag)}"
: "${SEED_TO:?set SEED_TO so a missing flag cannot run the full seed grid as technical-smoke}"
: "${TOPOLOGY:?set TOPOLOGY so a missing flag cannot run every topology as technical-smoke}"
export MODEL

mkdir -p "${ARTIFACT_ROOT}" "$(dirname "${VLLM_LOG}")" "$(dirname "${VENV}")"

if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "Creating thesis venv at ${VENV}"
  python3 -m venv "${VENV}"
  "${VENV}/bin/python" -m pip install -r requirements.txt
fi
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
PYTHON="${VENV}/bin/python"

eval "$(
  MODEL="${MODEL}" "${PYTHON}" - <<'PY'
import os
import shlex

from convention_topology.config import load_config, resolve_model

config = load_config()
spec = resolve_model(config, os.environ["MODEL"])
entry = config["models"][os.environ["MODEL"]]
extra = entry.get("vllm_extra_args") or []
if not isinstance(extra, list):
    extra = []
defaults = {
    "MODEL_ID": spec.model_id,
    "DTYPE": spec.dtype or "",
    "MAX_MODEL_LEN": str(spec.max_model_len),
    "MAX_NUM_SEQS": str(spec.max_num_seqs),
    "TP": str(spec.tp),
    "VLLM_EXTRA_ARGS": " ".join(str(part) for part in extra),
}
for key, value in defaults.items():
    if not os.environ.get(key):
        print(f"export {key}={shlex.quote(str(value))}")
PY
)"

if [[ -z "${MODEL_ID:-}" ]]; then
  echo "MODEL_ID is empty after profile lookup" >&2
  exit 1
fi

# Sidecar forensics (job_forensics): export versions from the known vLLM binary
# and a scheduler GPU-type env if present. Do not write device queries into config.yaml.
export GPU_TYPE="${GPU_TYPE:-${SLURM_GPU_TYPE:-}}"
if [[ -z "${VLLM_VERSION:-}" ]]; then
  set +e
  VLLM_VERSION="$("${VLLM_BIN[@]}" --version 2>/dev/null)"
  _vllm_ver_rc=$?
  set -e
  if [[ ${_vllm_ver_rc} -ne 0 ]]; then
    VLLM_VERSION=""
  fi
  export VLLM_VERSION
fi

PORT="$("${PYTHON}" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
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

trap stop_vllm EXIT
trap on_pretimeout USR1 TERM INT

VLLM_EXTRA=()
if [[ -n "${VLLM_EXTRA_ARGS:-}" ]]; then
  read -r -a VLLM_EXTRA <<< "${VLLM_EXTRA_ARGS}"
fi

"${VLLM_BIN[@]}" serve "${MODEL_ID}" \
  --host 127.0.0.1 \
  --port "${PORT}" \
  --dtype "${DTYPE}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --max-num-seqs "${MAX_NUM_SEQS}" \
  --tensor-parallel-size "${TP}" \
  "${VLLM_EXTRA[@]}" \
  >"${VLLM_LOG}" 2>&1 &
VLLM_PID=$!

# Wait until /v1/models answers within SERVE_WAIT_TIMEOUT.
"${PYTHON}" - <<'PY'
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

RUNNER_ARGS=(
  "${PYTHON}" run_main.py
  --model "${MODEL}"
  --program "${PROGRAM:-emergence}"
  --artifact-root "${ARTIFACT_ROOT}"
  --base-url "${BASE_URL}"
  --campaign "${CAMPAIGN}"
)
if [[ -n "${SEED_FROM:-}" ]]; then
  RUNNER_ARGS+=(--seed-from "${SEED_FROM}")
fi
RUNNER_ARGS+=(--seed-to "${SEED_TO}")
RUNNER_ARGS+=(--topology "${TOPOLOGY}")
if [[ -n "${K:-}" ]]; then
  RUNNER_ARGS+=(--k "${K}")
fi

"${RUNNER_ARGS[@]}" &
RUNNER_PID=$!
wait "${RUNNER_PID}"
stop_vllm
