# Shared Yen scratch resolution. Source from jobs/*.sh / thesis_vllm.slurm.
# Sets SCRATCH. Honours an existing SCRATCH if it is already a directory.

resolve_yen_scratch() {
  if [[ -z "${SCRATCH:-}" || ! -d "${SCRATCH}" ]]; then
    SCRATCH="/scratch/shared/${USER}"
    if [[ ! -d "${SCRATCH}" && -d "/yen/scratch/shared/${USER}" ]]; then
      SCRATCH="/yen/scratch/shared/${USER}"
    fi
  fi
  if SCRATCH_REAL="$(readlink -f "${SCRATCH}" 2>/dev/null)" && [[ -d "${SCRATCH_REAL}" ]]; then
    SCRATCH="${SCRATCH_REAL}"
  fi
  export SCRATCH
}
