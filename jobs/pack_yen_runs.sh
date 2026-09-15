#!/bin/bash
# Pack Yen campaign artifacts for download. Run in the Jupyter Terminal.
# Writes to scratch only — never $HOME (80 GB quota).
#
# All campaigns:
#   bash jobs/pack_yen_runs.sh
# One campaign:
#   bash jobs/pack_yen_runs.sh technical-smoke
#
# Then Jupyter file browser: scratch → exports → the .tar.gz (via ~/scratch symlink).

set -euo pipefail

# shellcheck source=jobs/_yen_scratch.sh
source "$(cd "$(dirname "$0")" && pwd)/_yen_scratch.sh"
resolve_yen_scratch

SRC="${SCRATCH}/runs"
OUT="${SCRATCH}/exports"
CAMPAIGN="${1:-}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

if [[ ! -d "${SRC}" ]]; then
  echo "No runs directory at ${SRC}" >&2
  exit 1
fi

mkdir -p "${OUT}"
chmod 700 "${SCRATCH}" "${OUT}" 2>/dev/null || true

if [[ -n "${CAMPAIGN}" ]]; then
  if [[ ! -d "${SRC}/${CAMPAIGN}" ]]; then
    echo "No campaign ${SRC}/${CAMPAIGN}" >&2
    echo "Present:" >&2
    ls -1 "${SRC}" >&2
    exit 1
  fi
  NAME="runs_${CAMPAIGN}_${STAMP}.tar.gz"
  echo "Source: ${SRC}/${CAMPAIGN}"
  du -sh "${SRC}/${CAMPAIGN}"
  tar -czf "${OUT}/${NAME}" \
    --exclude='*.lock' \
    --exclude='*.tmp' \
    -C "${SRC}" "${CAMPAIGN}"
else
  NAME="runs_all_${STAMP}.tar.gz"
  echo "Source: ${SRC}"
  du -sh "${SRC}"
  ls -1 "${SRC}"
  tar -czf "${OUT}/${NAME}" \
    --exclude='*.lock' \
    --exclude='*.tmp' \
    -C "${SCRATCH}" runs
fi

echo
ls -lh "${OUT}/${NAME}"
echo
echo "Archive: ${OUT}/${NAME}"
echo "Jupyter: ~/scratch/exports/${NAME}  (after: ln -sfn ${SCRATCH} ~/scratch)"
echo "If the file is too large for the browser, split it:"
echo "  split -b 1500m -d ${OUT}/${NAME} ${OUT}/${NAME}."
