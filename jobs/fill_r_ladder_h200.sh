#!/usr/bin/env bash
# H200 fill probe. One GPU (tp=1). Does not change the counted A40 default.
# Serial chain so we never ask for both H200s. Queue behind yq2411 / jyw is expected.
#
#   bash jobs/fill_r_ladder_h200.sh --dry-run
#   bash jobs/fill_r_ladder_h200.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
# shellcheck source=jobs/_yen_scratch.sh
source "${ROOT}/jobs/_yen_scratch.sh"
resolve_yen_scratch

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

WALL="${FILL_LADDER_WALL:-2:00:00}"
# Pilot: prompt max 586, p99 ~573; completion up to 512. 2048 ≈ 2× that, vs YAML 8192.
MAX_MODEL_LEN="${MAX_MODEL_LEN:-2048}"
MANIFEST_DIR="${SCRATCH}/runs/fill-ladder-h200"
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
    campaign="gpu-fill-h200-${model}-c${r}"
    artifact="${SCRATCH}/runs/${campaign}"
    jobname="h200-${model}-c${r}"
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
    unset FILL_MAX_CONCURRENT_RUNS FILL_MAX_NUM_SEQS FILL_IN_FLIGHT_LIMIT TP
    prev="${jid}"
    python3 -c "import json,sys; print(json.dumps({
      'job_id': sys.argv[1], 'model': sys.argv[2], 'R': int(sys.argv[3]),
      'max_num_seqs': int(sys.argv[4]), 'in_flight_limit': int(sys.argv[5]),
      'n_cells': int(sys.argv[4]), 'campaign': sys.argv[6],
      'artifact_root': sys.argv[7], 'wall': sys.argv[8], 'gpu': 'H200', 'tp': 1,
    }))" "${jid}" "${model}" "${r}" "${seqs}" "${inflight}" "${campaign}" "${artifact}" "${WALL}" >> "${MANIFEST}"
    echo "submitted ${jid}"
  done
}

# 2× A40 leftover KV is ~30–35 GB (31B BF16 sharded). One H200 is ~80 GB after
# weights, so start near 2× the A40 working R and step by 32, not +6.
echo "=== H200 chain (gemma then olmo) ==="
submit_chain \
  gemma4_31b:96 gemma4_31b:128 gemma4_31b:160 \
  olmo31_32b:128 olmo31_32b:160 olmo31_32b:192

if [[ "${DRY}" -eq 0 ]]; then
  echo "manifest ${MANIFEST}"
  echo "squeue -u jendress"
fi
