#!/usr/bin/env bash
# Run manually in the Yen Jupyter Terminal. No GPU allocation or inference.
# Current image inspection is not proof of historical image identity.
set -u

audit_yen_runtime() {
  date -u
  printf '\nHistorical Slurm allocations (including metadata job IDs)\n'
  if command -v sacct >/dev/null 2>&1; then
    sacct -u jendress -S 2026-09-21 -E 2026-10-09 \
      -j 634199,634200,634201,634202,634203,634204,634205,634206,634211,634212,634213,634214,634215,634216,634217,647273,647274,677641,709333,709335 \
      --format=JobID,JobName%24,Start,End,State,NodeList%24,ReqTRES%60,AllocTRES%60 \
      --parsable2
  else
    printf 'sacct unavailable in this shell.\n'
  fi

  printf '\nHistorical job/server log evidence\n'
  for audit_job_id in 634199 634200 634201 634202 634203 634204 634205 634206 634211 634212 634213 634214 634215 634216 634217 647273 647274 677641 709333 709335; do
    for audit_log_path in \
      "/scratch/shared/jendress/vllm/thesis_vllm_${audit_job_id}.out" \
      "/scratch/shared/jendress/vllm/thesis_vllm_${audit_job_id}.err" \
      "/scratch/shared/jendress/vllm/thesis_${audit_job_id}.log"; do
      if [ -r "$audit_log_path" ]; then
        if command -v rg >/dev/null 2>&1; then
          rg -n -i -m 25 'A40|NVIDIA|GPU|torch|pytorch|cuda|driver|vllm|apptainer|\.sif' "$audit_log_path"
        else
          grep -n -i -m 25 -E 'A40|NVIDIA|GPU|torch|pytorch|cuda|driver|vllm|apptainer|\.sif' "$audit_log_path"
        fi
      else
        printf 'Missing or unreadable: %s\n' "$audit_log_path"
      fi
    done
  done

  printf '\nRetained container: current inspection only\n'
  audit_image_path=/scratch/shared/jendress/images/vllm-openai-v0.28.0.sif
  if [ ! -r "$audit_image_path" ]; then
    printf 'Container missing or unreadable: %s\n' "$audit_image_path"
    return
  fi
  if ! command -v apptainer >/dev/null 2>&1 && type module >/dev/null 2>&1; then
    module load apptainer
  fi
  if ! command -v apptainer >/dev/null 2>&1; then
    printf 'Apptainer unavailable. Load the cluster module and rerun.\n'
    return
  fi
  stat "$audit_image_path"
  apptainer inspect "$audit_image_path"
  apptainer exec --cleanenv --no-home "$audit_image_path" python3 - <<'PY'
import platform
from importlib import metadata

print('Inference-container Python:', platform.python_version())
for package in ('vllm', 'torch', 'transformers'):
    try:
        print(package + ':', metadata.version(package))
    except metadata.PackageNotFoundError:
        print(package + ': not installed')
try:
    import torch
    print('PyTorch CUDA build:', torch.version.cuda)
except Exception as exc:
    print('PyTorch import unavailable:', type(exc).__name__, str(exc))
PY
  printf '\nThese versions describe the retained image now. Historical use requires matching job/log evidence.\n'
  printf 'Metadata job IDs may not cover every resumed segment. AllocTRES may omit GPU model.\n'
}

audit_yen_runtime 2>&1 | tee yen-runtime-audit-2026-10-26.txt
exit "${PIPESTATUS[0]}"
