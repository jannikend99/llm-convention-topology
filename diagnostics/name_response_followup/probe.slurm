#!/bin/bash
#SBATCH --job-name=name-followup
#SBATCH --partition=gpu
#SBATCH --gres=gpu:2
#SBATCH --constraint=GPU_MODEL:A40
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --time=24:00:00
#SBATCH --output=/scratch/shared/%u/vllm/name_followup_%A_%a.out
#SBATCH --error=/scratch/shared/%u/vllm/name_followup_%A_%a.err

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the repository root}"
source jobs/_yen_scratch.sh
resolve_yen_scratch
MODELS=(olmo31_32b qwen38_27b gemma4_31b glm4_32b)
EXPERIMENTS=(replication rules retention)
TASK_INDEX="${SLURM_ARRAY_TASK_ID:-0}"
[[ "${TASK_INDEX}" =~ ^[0-9]+$ ]] && (( TASK_INDEX <= 11 )) || { echo 'Array index must be 0–11'; exit 2; }
MODEL="${MODELS[$((TASK_INDEX % 4))]}"
EXPERIMENT="${EXPERIMENTS[$((TASK_INDEX / 4))]}"
REPEATS=''
SEED_BASE=20261008
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model|--experiment|--repeats|--seed-base) [[ $# -ge 2 ]] || { echo "Missing value for $1"; exit 2; } ;;
    *) echo "Unknown argument: $1"; exit 2 ;;
  esac
  case "$1" in
    --model|--experiment) [[ -z "${SLURM_ARRAY_TASK_ID:-}" ]] || { echo 'Do not combine --model/--experiment with an array'; exit 2; } ;;
  esac
  case "$1" in
    --model) MODEL="$2" ;;
    --experiment) EXPERIMENT="$2" ;;
    --repeats) REPEATS="$2" ;;
    --seed-base) SEED_BASE="$2" ;;
  esac
  shift 2
done
case "${MODEL}" in olmo31_32b|qwen38_27b|gemma4_31b|glm4_32b) ;; *) echo 'Unsupported model'; exit 2 ;; esac
case "${EXPERIMENT}" in
  replication) REPEATS="${REPEATS:-50}" ;;
  rules) REPEATS="${REPEATS:-25}" ;;
  retention) REPEATS="${REPEATS:-20}" ;;
  *) echo 'Unsupported experiment'; exit 2 ;;
esac
[[ "${REPEATS}" =~ ^[1-9][0-9]*$ ]] && (( REPEATS <= 200 )) || { echo 'repeats must be 1–200'; exit 2; }
[[ "${SEED_BASE}" =~ ^[0-9]+$ ]] && (( SEED_BASE <= 2147483447 )) || { echo 'Invalid seed base'; exit 2; }
PYTHON="${SCRATCH}/venvs/thesis/bin/python"
SIF="${VLLM_SIF:-${SCRATCH}/images/vllm-openai-v0.28.0.sif}"
[[ -x "${PYTHON}" && -f "${SIF}" ]] || { echo "Missing existing thesis venv or SIF: ${PYTHON}, ${SIF}"; exit 2; }
module purge
module load "${PYTHON_MODULE:-python/3.11.3}"
module load apptainer
export HF_HOME="${SCRATCH}/models"
# No unexpected downloads. Missing pinned cached checkpoints fail visibly.
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NCCL_P2P_DISABLE=1
TAG="${SLURM_JOB_ID}_${SLURM_ARRAY_TASK_ID:-single}"
WORK="${SCRATCH}/vllm/name_followup_${TAG}"
mkdir -p "${WORK}/home" "${WORK}/tmp"
export TMPDIR="${WORK}/tmp"
"${PYTHON}" diagnostics/name_response_followup/run.py --model "${MODEL}" --experiment "${EXPERIMENT}" --repeats "${REPEATS}" --seed-base "${SEED_BASE}" --dry-run
eval "$(MODEL="${MODEL}" "${PYTHON}" - <<'PY'
import os, shlex
from convention_topology.config import load_config, resolve_model
s = resolve_model(load_config('config.yaml'), os.environ['MODEL'])
for key, value in {'MODEL_ID': s.model_id, 'REVISION': s.revision,
                   'DTYPE': s.dtype, 'TP': s.tp, 'CONTEXT': s.max_model_len}.items():
    print(f'{key}={shlex.quote(str(value))}')
PY
)"
PORT="$("${PYTHON}" - <<'PY'
import socket
with socket.socket() as s:
    s.bind(('127.0.0.1', 0))
    print(s.getsockname()[1])
PY
)"
BASE_URL="http://127.0.0.1:${PORT}/v1"
SERVER_PID=''
cleanup() {
  if [[ -n "${SERVER_PID}" ]]; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 143' TERM INT
cat > "${WORK}/launch.sh" <<'SH'
#!/bin/bash
set -euo pipefail
exec vllm "$@"
SH
chmod +x "${WORK}/launch.sh"
echo "Model=${MODEL_ID} revision=${REVISION} experiment=${EXPERIMENT} repeats=${REPEATS} seed_base=${SEED_BASE} log=${WORK}/server.log"
apptainer exec --nv --home "${WORK}/home" --bind "${SCRATCH}:${SCRATCH}" \
  --env "HF_HOME=${HF_HOME},HF_HUB_OFFLINE=1,TRANSFORMERS_OFFLINE=1,NCCL_P2P_DISABLE=1" \
  "${SIF}" "${WORK}/launch.sh" serve "${MODEL_ID}" \
  --revision "${REVISION}" --tokenizer-revision "${REVISION}" \
  --host 127.0.0.1 --port "${PORT}" --dtype "${DTYPE}" \
  --tensor-parallel-size "${TP}" --max-model-len "${CONTEXT}" --max-num-seqs 8 \
  --disable-custom-all-reduce --enable-prefix-caching > "${WORK}/server.log" 2>&1 &
SERVER_PID=$!
export BASE_URL SERVER_PID
"${PYTHON}" - <<'PY'
import os, time, urllib.request
deadline = time.monotonic() + 1800
while time.monotonic() < deadline:
    try:
        os.kill(int(os.environ['SERVER_PID']), 0)
    except ProcessLookupError:
        raise SystemExit('vLLM exited during startup; inspect server.log')
    try:
        with urllib.request.urlopen(os.environ['BASE_URL'] + '/models', timeout=5):
            break
    except Exception:
        time.sleep(5)
else:
    raise SystemExit('vLLM startup timeout after 30 minutes; inspect server.log')
PY
"${PYTHON}" diagnostics/name_response_followup/run.py \
  --model "${MODEL}" --experiment "${EXPERIMENT}" --repeats "${REPEATS}" \
  --seed-base "${SEED_BASE}" --base-url "${BASE_URL}" \
  --output "${SCRATCH}/runs/name-response-followup"
"${PYTHON}" diagnostics/name_response_followup/analyze.py \
  --results-root "${SCRATCH}/runs/name-response-followup/live/${MODEL}/${EXPERIMENT}"
