#!/usr/bin/env bash
# Short H200 ladder for GLM only. One GPU (tp=1).
# Qwen already has attempts at 128/160/192; evaluate that manifest, do not rerun it.
# GLM wrote no attempts. Three optimistic steps, not a walk up from the A40 freeze (82):
#   160 / 192 / 224
# Each step sets R, max_num_seqs=2R, in_flight=2R+2, tp=1, max_model_len=2048.
# Wall 40 min. vLLM start is ~10 min; USR1 fires 5 min before the wall.
# Does not touch fill-ladder-h200-qwen-glm/ or config.yaml.
#
#   bash jobs/fill_r_ladder_h200_hi.sh --dry-run
#   bash jobs/fill_r_ladder_h200_hi.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
# shellcheck source=jobs/_yen_scratch.sh
source "${ROOT}/jobs/_yen_scratch.sh"
resolve_yen_scratch

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

WALL="${FILL_LADDER_WALL:-40:00}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-2048}"
MANIFEST_DIR="${SCRATCH}/runs/fill-ladder-h200-hi"
MANIFEST="${MANIFEST_DIR}/manifest.jsonl"
SLURM_FILE="${ROOT}/jobs/thesis_vllm.slurm"

if [[ ! -f "${SLURM_FILE}" ]]; then
  echo "missing ${SLURM_FILE}" >&2
  exit 1
fi

if [[ "${DRY}" -eq 0 ]]; then
  mkdir -p "${MANIFEST_DIR}"
  if [[ -s "${MANIFEST}" ]]; then
    echo "manifest already has rows: ${MANIFEST}" >&2
    echo "refusing to overwrite. Move it aside or set a new SCRATCH." >&2
    exit 1
  fi
  : > "${MANIFEST}"
fi

submit_chain() {
  local prev=""
  local spec model r seqs inflight campaign artifact jobname jid
  for spec in "$@"; do
    model="${spec%%:*}"
    r="${spec##*:}"
    seqs=$((2 * r))
    inflight=$((2 * r + 2))
    campaign="gpu-fill-h200-hi-${model}-c${r}"
    artifact="${SCRATCH}/runs/${campaign}"
    jobname="h200hi-${model}-c${r}"
    jobname="${jobname:0:32}"
    echo "H200 R=${r} model=${model} seqs=${seqs} in_flight=${inflight} campaign=${campaign} wall=${WALL} after=${prev:-none}"
    if [[ "${DRY}" -eq 1 ]]; then
      prev="${model}-c${r}"
      continue
    fi
    local dep=()
    if [[ -n "${prev}" ]]; then
      dep=(--dependency="afterany:${prev}")
    fi
    export FILL_MAX_CONCURRENT_RUNS="${r}"
    export FILL_MAX_NUM_SEQS="${seqs}"
    export FILL_IN_FLIGHT_LIMIT="${inflight}"
    export TP=1
    export MAX_MODEL_LEN
    jid="$(sbatch --parsable --export=ALL -G 1 --mem=128G -t "${WALL}" \
      -C "GPU_MODEL:H200" --mail-type=FAIL --job-name="${jobname}" \
      "${dep[@]}" "${SLURM_FILE}" -- \
      --campaign "${campaign}" --model "${model}" --task "emergence:mixing:0-${seqs}")"
    unset FILL_MAX_CONCURRENT_RUNS FILL_MAX_NUM_SEQS FILL_IN_FLIGHT_LIMIT TP MAX_MODEL_LEN
    prev="${jid}"
    python3 -c "import json,sys; print(json.dumps({
      'job_id': sys.argv[1], 'model': sys.argv[2], 'R': int(sys.argv[3]),
      'max_num_seqs': int(sys.argv[4]), 'in_flight_limit': int(sys.argv[5]),
      'n_cells': int(sys.argv[4]), 'campaign': sys.argv[6],
      'artifact_root': sys.argv[7], 'wall': sys.argv[8], 'gpu': 'H200', 'tp': 1,
      'max_model_len': int(sys.argv[9]),
    }))" "${jid}" "${model}" "${r}" "${seqs}" "${inflight}" "${campaign}" "${artifact}" "${WALL}" "${MAX_MODEL_LEN}" >> "${MANIFEST}"
    echo "submitted ${jid}"
  done
  if [[ "${DRY}" -eq 0 && -n "${prev}" ]]; then
    echo "after the chain:"
    echo "  FILL_LADDER_MANIFEST=${MANIFEST} ${SCRATCH}/venvs/thesis/bin/python jobs/fill_r_ladder_eval.py"
  fi
}

echo "=== H200 GLM 160 / 192 / 224 ==="
submit_chain glm4_32b:160 glm4_32b:192 glm4_32b:224

if [[ "${DRY}" -eq 0 ]]; then
  echo "manifest ${MANIFEST}"
  echo "squeue -u jendress"
fi
