#!/bin/bash
# Thesis counted-path job. vLLM pin: v0.28.0 (stable as of 2026-09-11).
# Keeper / counted / pilot-run submit: sbatch -G 2 --mem=128G (Yen fill freeze 2026-09-13).
# Header -G 1 --mem=64G stays for technical-smoke E2B.
# Not the repo-root Ollama smoke.
#SBATCH --job-name=thesis-vllm
#SBATCH -p gpu
#SBATCH -G 1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH -t 1-00:00:00
#SBATCH -o /scratch/shared/%u/vllm/thesis_vllm_%j.out
#SBATCH -e /scratch/shared/%u/vllm/thesis_vllm_%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=jannik.endress@stanford.edu
#SBATCH --signal=B:USR1@300
#SBATCH -C "GPU_MODEL:A40"

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
WRAP_HOME="${SCRATCH}/container-home"
export HF_HOME
export NCCL_P2P_DISABLE="${NCCL_P2P_DISABLE:-1}"
mkdir -p "${HF_HOME}" "${WRAP_HOME}" "${SCRATCH}/tmp" "${SCRATCH}/vllm"

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
  # Yen forbids APPTAINERENV_HOME. Bake HOME into a scratch wrapper instead.
  WRAP="${SCRATCH}/vllm_wrap.sh"
  cat > "${WRAP}" <<EOF
#!/bin/bash
export HOME=${WRAP_HOME}
export HF_HOME=${HF_HOME}
export NCCL_P2P_DISABLE=${NCCL_P2P_DISABLE}
exec vllm "\$@"
EOF
  chmod +x "${WRAP}"
  VLLM_BIN=(
    apptainer exec --nv
    --env "NCCL_P2P_DISABLE=${NCCL_P2P_DISABLE}"
    --bind "${SCRATCH}:${SCRATCH}"
    "${VLLM_SIF}"
    "${WRAP}"
  )
else
  VLLM_BIN=(vllm)
fi

VENV="${SCRATCH}/venvs/thesis"
VLLM_LOG="${SCRATCH}/vllm/thesis_${SLURM_JOB_ID}.log"

# Parse argv after `--` (sbatch ... thesis_vllm.slurm -- --campaign … --task …).
if [[ "${1:-}" == "--" ]]; then
  shift
fi
COUNTED_MODEL=""
COUNTED_CAMPAIGN=""
COUNTED_ARTIFACT_ROOT=""
HAS_TASK=0
HAS_TECH_CHECK=0
HAS_BASE_URL=0
HAS_ARTIFACT_ROOT=0
_parse_i=0
_parse_args=("$@")
while [[ ${_parse_i} -lt ${#_parse_args[@]} ]]; do
  _arg="${_parse_args[${_parse_i}]}"
  case "${_arg}" in
    --model)
      COUNTED_MODEL="${_parse_args[$((_parse_i + 1))]:-}"
      _parse_i=$((_parse_i + 2))
      ;;
    --model=*)
      COUNTED_MODEL="${_arg#--model=}"
      _parse_i=$((_parse_i + 1))
      ;;
    --campaign)
      COUNTED_CAMPAIGN="${_parse_args[$((_parse_i + 1))]:-}"
      _parse_i=$((_parse_i + 2))
      ;;
    --campaign=*)
      COUNTED_CAMPAIGN="${_arg#--campaign=}"
      _parse_i=$((_parse_i + 1))
      ;;
    --task)
      HAS_TASK=1
      _parse_i=$((_parse_i + 2))
      ;;
    --task=*)
      HAS_TASK=1
      _parse_i=$((_parse_i + 1))
      ;;
    --tech-check)
      HAS_TECH_CHECK=1
      _parse_i=$((_parse_i + 1))
      ;;
    --tech-check=*)
      HAS_TECH_CHECK=1
      _parse_i=$((_parse_i + 1))
      ;;
    --artifact-root)
      COUNTED_ARTIFACT_ROOT="${_parse_args[$((_parse_i + 1))]:-}"
      HAS_ARTIFACT_ROOT=1
      _parse_i=$((_parse_i + 2))
      ;;
    --artifact-root=*)
      COUNTED_ARTIFACT_ROOT="${_arg#--artifact-root=}"
      HAS_ARTIFACT_ROOT=1
      _parse_i=$((_parse_i + 1))
      ;;
    --base-url)
      HAS_BASE_URL=1
      _parse_i=$((_parse_i + 2))
      ;;
    --base-url=*)
      HAS_BASE_URL=1
      _parse_i=$((_parse_i + 1))
      ;;
    *)
      _parse_i=$((_parse_i + 1))
      ;;
  esac
done

if [[ -n "${DIAG_LADDER:-}" && "${HAS_TASK}" -eq 1 ]]; then
  echo "DIAG_LADDER cannot be combined with --task" >&2
  exit 1
fi
if [[ -n "${DIAG_LADDER:-}" && "${HAS_TECH_CHECK}" -eq 1 ]]; then
  echo "DIAG_LADDER cannot be combined with --tech-check" >&2
  exit 1
fi
if [[ "${HAS_TASK}" -eq 1 && "${HAS_TECH_CHECK}" -eq 1 ]]; then
  echo "--tech-check cannot be combined with --task" >&2
  exit 1
fi

if [[ -n "${DIAG_LADDER:-}" ]]; then
  : "${MODEL:?set MODEL to a config.yaml shorthand (from --print-jobs or a fit hand flag)}"
  : "${SEED_TO:?set SEED_TO so a missing flag cannot run the full seed grid as technical-smoke}"
  : "${TOPOLOGY:?set TOPOLOGY so a missing flag cannot run every topology as technical-smoke}"
  export MODEL
  if [[ -n "${CAMPAIGN:-}" ]]; then
    echo "DIAG_LADDER cannot be combined with CAMPAIGN; the ladder sets one campaign per cell" >&2
    exit 1
  fi
  if [[ -n "${DIAG_TECH_INTERACTIONS:-}" ]]; then
    echo "DIAG_LADDER cannot be combined with DIAG_TECH_INTERACTIONS" >&2
    exit 1
  fi
  case "${DIAG_LADDER}" in
    ab|one-factor) ;;
    *)
      echo "DIAG_LADDER must be ab or one-factor" >&2
      exit 1
      ;;
  esac
  if [[ "${DIAG_LADDER}" == one-factor ]]; then
    : "${DIAG_DECODE:?set DIAG_DECODE to parse or json_schema after the A/B readout}"
    if [[ "${DIAG_DECODE}" != parse && "${DIAG_DECODE}" != json_schema ]]; then
      echo "DIAG_DECODE must be parse or json_schema" >&2
      exit 1
    fi
  fi
  ARTIFACT_ROOT="${SCRATCH}/runs"
elif [[ "${HAS_TASK}" -eq 1 ]]; then
  if [[ -z "${COUNTED_MODEL}" ]]; then
    echo "counted job requires --model" >&2
    exit 1
  fi
  if [[ -z "${COUNTED_CAMPAIGN}" ]]; then
    echo "counted job requires --campaign" >&2
    exit 1
  fi
  MODEL="${COUNTED_MODEL}"
  CAMPAIGN="${COUNTED_CAMPAIGN}"
  export MODEL
  if [[ "${CAMPAIGN}" == diag-ashery-* || "${CAMPAIGN}" == diag-h12-* || "${CAMPAIGN}" == diag-n48-* || "${CAMPAIGN}" == diag-strings-* ]]; then
    : "${DIAG_N:?set DIAG_N for this diag campaign}"
    : "${DIAG_H:?set DIAG_H for this diag campaign}"
    : "${DIAG_POOL:?set DIAG_POOL for this diag campaign}"
    : "${DIAG_DECODE:?set DIAG_DECODE for this diag campaign}"
    : "${DIAG_CAP:?set DIAG_CAP for this diag campaign}"
  fi
  if [[ "${HAS_ARTIFACT_ROOT}" -eq 1 ]]; then
    ARTIFACT_ROOT="${COUNTED_ARTIFACT_ROOT}"
  else
    ARTIFACT_ROOT="${SCRATCH}/runs/${CAMPAIGN}"
  fi
elif [[ "${HAS_TECH_CHECK}" -eq 1 ]]; then
  if [[ -z "${COUNTED_MODEL}" ]]; then
    echo "counted job requires --model" >&2
    exit 1
  fi
  if [[ "${COUNTED_CAMPAIGN}" == "experiment" ]]; then
    echo "--tech-check refuses campaign experiment" >&2
    exit 1
  fi
  MODEL="${COUNTED_MODEL}"
  CAMPAIGN="${COUNTED_CAMPAIGN:-tech-check}"
  export MODEL
  if [[ "${HAS_ARTIFACT_ROOT}" -eq 1 ]]; then
    ARTIFACT_ROOT="${COUNTED_ARTIFACT_ROOT}"
  else
    ARTIFACT_ROOT="${SCRATCH}/runs/${CAMPAIGN}"
  fi
  if ! scontrol update JobId="${SLURM_JOB_ID}" TimeLimit=1:00:00; then
    echo "tech-check failed to set TimeLimit=1:00:00; refusing 24 h slot" >&2
    exit 1
  fi
else
  echo "submit requires --task or --tech-check on the counted path, or DIAG_LADDER" >&2
  exit 1
fi

# Yen does not always export SLURM_TIMELIMIT; copy TimeLimit for the heartbeat header.
if [[ -z "${SLURM_TIMELIMIT:-}" && -n "${SLURM_JOB_ID:-}" ]]; then
  SLURM_TIMELIMIT="$(scontrol show job "${SLURM_JOB_ID}" 2>/dev/null | tr ' ' '\n' | sed -n 's/^TimeLimit=//p' | head -n 1 || true)"
fi
export SLURM_TIMELIMIT="${SLURM_TIMELIMIT:-}"

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
}
for key, value in defaults.items():
    if key == "MAX_NUM_SEQS" or not os.environ.get(key):
        print(f"export {key}={shlex.quote(str(value))}")
# Keep model YAML extras; append operator VLLM_EXTRA_ARGS (do not replace).
merged = [str(part) for part in extra]
env_extra = os.environ.get("VLLM_EXTRA_ARGS", "")
if env_extra.strip():
    merged.extend(shlex.split(env_extra))
print(f"export VLLM_EXTRA_ARGS={shlex.quote(' '.join(merged))}")
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
export VLLM_LOG
export SERVE_WAIT_TIMEOUT="${SERVE_WAIT_TIMEOUT:-1800}"
export SERVE_HANG_SECONDS="${SERVE_HANG_SECONDS:-420}"

VLLM_PID=""
RUNNER_PID=""
METRICS_PID=""

stop_vllm() {
  if [[ -n "${VLLM_PID}" ]] && kill -0 "${VLLM_PID}" 2>/dev/null; then
    kill "${VLLM_PID}" 2>/dev/null || true
    wait "${VLLM_PID}" 2>/dev/null || true
  fi
}

stop_metrics_scrape() {
  if [[ -n "${METRICS_PID:-}" ]] && kill -0 "${METRICS_PID}" 2>/dev/null; then
    kill "${METRICS_PID}" 2>/dev/null || true
    wait "${METRICS_PID}" 2>/dev/null || true
  fi
  METRICS_PID=""
}

start_metrics_scrape() {
  local runner_pid="$1"
  export METRICS_RUNNER_PID="${runner_pid}"
  "${PYTHON}" - <<'PY' &
import os
import time
import urllib.request
from datetime import datetime, timezone

pid = int(os.environ["METRICS_RUNNER_PID"])
port = os.environ["PORT"]
log_path = os.environ["VLLM_LOG"]
url = f"http://127.0.0.1:{port}/metrics"
interval = 20


def runner_alive() -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


while runner_alive():
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        body = f"metrics scrape failed: {exc}\n"
    try:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"=== vLLM /metrics {stamp} ===\n")
            handle.write(body)
            if body and not body.endswith("\n"):
                handle.write("\n")
    except OSError:
        pass
    deadline = time.time() + interval
    while time.time() < deadline and runner_alive():
        time.sleep(1)
PY
  METRICS_PID=$!
}

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
# INFO: request id + SamplingParams (served temperature). Prompts stay DEBUG.
if [[ " ${VLLM_EXTRA[*]} " != *" --enable-log-requests "* ]]; then
  VLLM_EXTRA+=(--enable-log-requests)
fi
# Shared prompt prefix for fill and counted serve (keepers: gemma4_31b, olmo31_32b, qwen38_27b, glm4_32b).
if [[ " ${VLLM_EXTRA[*]} " != *" --enable-prefix-caching "* ]]; then
  VLLM_EXTRA+=(--enable-prefix-caching)
fi
# Ampere TP=2: custom all-reduce can hang after CUDA graphs (Gemma 31B).
if [[ " ${VLLM_EXTRA[*]} " != *" --disable-custom-all-reduce "* ]]; then
  VLLM_EXTRA+=(--disable-custom-all-reduce)
fi

echo "NCCL_P2P_DISABLE=${NCCL_P2P_DISABLE} TP=${TP} serve extras: ${VLLM_EXTRA[*]}"
echo "vLLM log: ${VLLM_LOG}"

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

# Wait until /v1/models answers. Abort Ampere TP=2 hangs (shm_broadcast / worker wait, no startup).
"${PYTHON}" - <<'PY'
import os, re, sys, time, urllib.request

url = os.environ["BASE_URL"] + "/models"
timeout = float(os.environ["SERVE_WAIT_TIMEOUT"])
hang_limit = float(os.environ["SERVE_HANG_SECONDS"])
log_path = os.environ["VLLM_LOG"]
deadline = time.time() + timeout
hang_re = re.compile(
    r"shm_broadcast|has not responded|hasn't responded|waiting for gpu worker|waiting for engine",
    re.I,
)
startup_re = re.compile(r"application startup complete|uvicorn running", re.I)
first_hang = None
last = None


def log_text() -> str:
    try:
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


while time.time() < deadline:
    text = log_text()
    started = bool(startup_re.search(text))
    if hang_re.search(text) and not started:
        if first_hang is None:
            first_hang = time.time()
        elif time.time() - first_hang >= hang_limit:
            print(
                "Ampere TP=2 hang: engine wait / shm_broadcast without startup complete "
                f"for {int(hang_limit)}s. Do not wait for SERVE_WAIT_TIMEOUT. "
                "Need NCCL_P2P_DISABLE=1 and --disable-custom-all-reduce on this job.",
                file=sys.stderr,
            )
            sys.exit(1)
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

run_counted_slice() {
  local campaign="$1"
  export CAMPAIGN="${campaign}"
  local cell_root="${SCRATCH}/runs/${CAMPAIGN}"
  mkdir -p "${cell_root}"
  echo "[diag-ladder] campaign=${CAMPAIGN} N=${DIAG_N:-} H=${DIAG_H:-} pool=${DIAG_POOL:-} decode=${DIAG_DECODE:-} cap=${DIAG_CAP:-}"
  local program="${PROGRAM:-emergence}"
  local seed_from="${SEED_FROM:-0}"
  local task_spec="${program}:${TOPOLOGY}:${seed_from}-${SEED_TO}"
  if [[ "${program}" == cm ]]; then
    task_spec="${task_spec}:k=${K}"
  fi
  local runner_args=(
    "${PYTHON}" run_main.py
    --model "${MODEL}"
    --artifact-root "${cell_root}"
    --base-url "${BASE_URL}"
    --campaign "${CAMPAIGN}"
    --task "${task_spec}"
  )
  "${runner_args[@]}" &
  RUNNER_PID=$!
  start_metrics_scrape "${RUNNER_PID}"
  set +e
  wait "${RUNNER_PID}"
  local rc=$?
  set -e
  stop_metrics_scrape
  RUNNER_PID=""
  return "${rc}"
}

if [[ -n "${DIAG_LADDER:-}" ]]; then
  export DIAG_CAP="${DIAG_CAP:-400}"
  ladder_rc=0
  if [[ "${DIAG_LADDER}" == ab ]]; then
    export DIAG_N=24 DIAG_H=5 DIAG_POOL=letters
    export DIAG_DECODE=parse
    run_counted_slice "diag-ashery-parse-${MODEL}" || ladder_rc=$?
    export DIAG_DECODE=json_schema
    run_counted_slice "diag-ashery-schema-${MODEL}" || ladder_rc=$?
  else
    decode_tag=parse
    if [[ "${DIAG_DECODE}" == json_schema ]]; then
      decode_tag=schema
    fi
    export DIAG_N=24 DIAG_H=12 DIAG_POOL=letters
    run_counted_slice "diag-h12-${decode_tag}-${MODEL}" || ladder_rc=$?
    export DIAG_N=48 DIAG_H=5 DIAG_POOL=letters
    run_counted_slice "diag-n48-${decode_tag}-${MODEL}" || ladder_rc=$?
    export DIAG_N=24 DIAG_H=5 DIAG_POOL=strings
    run_counted_slice "diag-strings-${decode_tag}-${MODEL}" || ladder_rc=$?
  fi
  stop_vllm
  exit "${ladder_rc}"
fi

RUNNER_ARGS=("${PYTHON}" run_main.py "$@")
if [[ "${HAS_BASE_URL}" -eq 0 ]]; then
  RUNNER_ARGS+=(--base-url "${BASE_URL}")
fi
if [[ "${HAS_ARTIFACT_ROOT}" -eq 0 ]]; then
  RUNNER_ARGS+=(--artifact-root "${ARTIFACT_ROOT}")
fi

"${RUNNER_ARGS[@]}" &
RUNNER_PID=$!
start_metrics_scrape "${RUNNER_PID}"
wait "${RUNNER_PID}"
stop_metrics_scrape
stop_vllm
