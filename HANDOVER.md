# Source handover

This repository is a private source handover. It contains the experiment
implementation, tests, diagnostic scripts, CI configuration, and retained
operator recipes. It does not deliver raw run data, current analysis outputs,
Yen execution, submission, or publication.

## Current analysis references

The final fixed-1500 Study 1 producer is maintained in the private meta-repo:
[fixed_horizon.py](https://github.com/jannikend99/master-thesis/blob/main/specs/results-analysis/main-runs-2026-10-05/audit-corrections/per18057/fixed_horizon.py).
The analysis index and scope are recorded in the
[results-analysis README](https://github.com/jannikend99/master-thesis/blob/main/specs/results-analysis/README.md).
This repository's `analyze.py` remains the historical first-gate/cap analysis;
it does not regenerate the current fixed-1500 H1/H2 results.

## Source-only archive

Create an archive from a verified source revision. The command records the
revision in the archive metadata and includes only the allowlisted source
paths:

```bash
REV="$(git rev-parse HEAD)"
ARCHIVE="/tmp/llm-convention-topology-${REV}.tar.gz"
git archive --format=tar.gz --output="$ARCHIVE" --prefix="llm-convention-topology-${REV}/" "$REV" -- \
  .github .gitignore .coveragerc README.md HANDOVER.md config.yaml requirements.txt \
  requirements-dev.txt requirements-repro.txt pytest.ini analyze.py run_main.py \
  run_one.py convention_topology tests diagnostics jobs/_yen_scratch.sh \
  jobs/thesis_vllm.slurm jobs/pack_yen_runs.sh jobs/yen_runtime_audit.sh
gzip -dc "$ARCHIVE" | git get-tar-commit-id
```

The archive omits `.git`, `archive/ops/`, tuning and other optional historical
job files, TypeSafe material, Graphify output, local data/results, caches,
credentials, and secrets. The omitted `archive/ops/` notes remain available in
the private working repository; the source bundle does not make those links
self-contained.

Because the archive has no `.git`, clone the private repository and check out
the recorded source revision before any campaign write. A source-only archive
is not the final data or analysis delivery.
