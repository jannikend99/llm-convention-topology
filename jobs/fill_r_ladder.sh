#!/usr/bin/env bash
# Fill ladder: three +6 R steps per keeper from the last stable R.
# Caps: max_num_seqs=2R, in_flight=2R+2, cells=2R (task emergence:mixing:0-2R).
# Wall default 25:00 — vLLM start is 5–8 min; remaining ~10–15 min is fill.
# Two chains in parallel (Yen 4-GPU cap = two -G 2 jobs):
#   A: gemma 54/60/66 then qwen 70/76/82
#   B: olmo 70/76/82 then glm 70/76/82
#
#   bash jobs/fill_r_ladder.sh
#   bash jobs/fill_r_ladder.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

WALL="${FILL_LADDER_WALL:-25:00}"
SCRATCH="${SCRATCH:-/scratch/shared/${USER}}"
MANIFEST_DIR="${SCRATCH}/runs/fill-ladder"
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
    campaign="gpu-fill-ladder-${model}-c${r}"
    artifact="${SCRATCH}/runs/${campaign}"
    jobname="lad-${model}-c${r}"
    jobname="${jobname:0:32}"
    echo "R=${r} model=${model} seqs=${seqs} in_flight=${inflight} cells=${seqs} campaign=${campaign} wall=${WALL} after=${prev:-none}"
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
    }))" "${jid}" "${model}" "${r}" "${seqs}" "${inflight}" "${campaign}" "${artifact}" "${WALL}" >> "${MANIFEST}"
    echo "submitted ${jid}"
  done
}

echo "=== chain A (gemma then qwen) ==="
submit_chain \
  gemma4_31b:54 gemma4_31b:60 gemma4_31b:66 \
  qwen38_27b:70 qwen38_27b:76 qwen38_27b:82

echo "=== chain B (olmo then glm) ==="
submit_chain \
  olmo31_32b:70 olmo31_32b:76 olmo31_32b:82 \
  glm4_32b:70 glm4_32b:76 glm4_32b:82

if [[ "${DRY}" -eq 0 ]]; then
  echo "manifest ${MANIFEST}"
  echo "when squeue is empty:"
  echo "  /scratch/shared/${USER}/venvs/thesis/bin/python jobs/fill_r_ladder_eval.py"
fi
