#!/usr/bin/env bash
# A40 fill with a tighter max_model_len (default 2048 from the cap-1500 prompt stats).
# Does not edit config.yaml. Two -G 2 chains = Yen 4-GPU cap; H200 jobs stay PD until a slot frees.
#
#   bash jobs/fill_r_ladder_a40_len.sh --dry-run
#   bash jobs/fill_r_ladder_a40_len.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
# shellcheck source=jobs/_yen_scratch.sh
source "${ROOT}/jobs/_yen_scratch.sh"
resolve_yen_scratch

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

WALL="${FILL_LADDER_WALL:-2:00:00}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-2048}"
MANIFEST_DIR="${SCRATCH}/runs/fill-ladder-a40-len${MAX_MODEL_LEN}"
MANIFEST="${MANIFEST_DIR}/manifest.jsonl"
SLURM_FILE="${ROOT}/jobs/thesis_vllm.slurm"

if [[ ! -f "${SLURM_FILE}" ]]; then
  echo "missing ${SLURM_FILE}" >&2
  exit 1
fi

if [[ "${DRY}" -eq 0 ]]; then
  mkdir -p "${MANIFEST_DIR}"
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
    campaign="gpu-fill-a40-len${MAX_MODEL_LEN}-${model}-c${r}"
    artifact="${SCRATCH}/runs/${campaign}"
    jobname="a40l-${model}-c${r}"
    jobname="${jobname:0:32}"
    echo "A40 len=${MAX_MODEL_LEN} R=${r} model=${model} seqs=${seqs} campaign=${campaign} wall=${WALL} after=${prev:-none}"
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
    export MAX_MODEL_LEN
    jid="$(sbatch --parsable --export=ALL -G 2 --mem=128G -t "${WALL}" --mail-type=FAIL \
      --job-name="${jobname}" "${dep[@]}" "${SLURM_FILE}" -- \
      --campaign "${campaign}" --model "${model}" --task "emergence:mixing:0-${seqs}")"
    unset FILL_MAX_CONCURRENT_RUNS FILL_MAX_NUM_SEQS FILL_IN_FLIGHT_LIMIT
    prev="${jid}"
    python3 -c "import json,sys; print(json.dumps({
      'job_id': sys.argv[1], 'model': sys.argv[2], 'R': int(sys.argv[3]),
      'max_num_seqs': int(sys.argv[4]), 'in_flight_limit': int(sys.argv[5]),
      'n_cells': int(sys.argv[4]), 'campaign': sys.argv[6],
      'artifact_root': sys.argv[7], 'wall': sys.argv[8],
      'gpu': 'A40', 'tp': 2, 'max_model_len': int(sys.argv[9]),
    }))" "${jid}" "${model}" "${r}" "${seqs}" "${inflight}" "${campaign}" "${artifact}" "${WALL}" "${MAX_MODEL_LEN}" >> "${MANIFEST}"
    echo "submitted ${jid}"
  done
}

# Working A40 R, then two steps up (JSON/KV broke Gemma near 60 at len 8192).
echo "=== A40 chain A (gemma) ==="
submit_chain gemma4_31b:48 gemma4_31b:64 gemma4_31b:80

echo "=== A40 chain B (olmo) ==="
submit_chain olmo31_32b:76 olmo31_32b:96 olmo31_32b:112

if [[ "${DRY}" -eq 0 ]]; then
  echo "manifest ${MANIFEST}"
  echo "squeue -u jendress"
fi
