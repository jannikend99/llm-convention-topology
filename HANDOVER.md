# Thesis reproduction package

This neutral supplement contains the experiment source, current analysis
producers, frozen research inputs and fits, and project-generated figures.
The separate Main-data archive contains all 2,560 attempted runs: 639 usable
Study 1 trajectories and 1,912 completed Study 2 trajectories at interaction
1,500, plus nine failed prefixes. The October 2 backup is historical.

The source and data archives restore into the same `thesis-reproduction/`
folder. They do not require access to the private authoring repositories.
The top-level `SOURCE_MANIFEST.json` records each source/input/output hash,
the underlying Git revision, and the exact manuscript/figure state. The
manuscript text itself is not redistributed. Refresh the snapshot if the
manuscript or its retained analyses change before submission.

## Restore and verify

Allow at least 25 GB free for both archives, extracted inputs and isolated
analysis copies. The raw tree alone is 11.14 GB. Use Python 3.12 and a C
compiler at `/usr/bin/clang`; the unchanged, source-hashed population engine
expects that path. The tested analysis additions include CFFI. No GPU, model
weights or provider credentials are needed for these reconstruction commands.
The current environment snapshot is not a historical Yen lock.

Verify both supplied archive checksums against the delivery checksum file,
then extract them into an empty destination:

```bash
tar -xzf thesis-reproduction-source.tar.gz -C /path/to/empty-destination
tar -xzf main_raw_data.tar.gz -C /path/to/empty-destination
cd /path/to/empty-destination/thesis-reproduction
python3.12 -m venv /tmp/thesis-analysis-env
. /tmp/thesis-analysis-env/bin/activate
python -m pip install -r 02_Topic/Experiment_Code/llm-convention-topology/requirements-analysis.txt
python 02_Topic/Experiment_Code/llm-convention-topology/jobs/reproduce_thesis.py integrity --package-root .
python 02_Topic/Experiment_Code/llm-convention-topology/jobs/reproduce_thesis.py doctor --package-root .
```

The doctor actually compiles and executes the frozen CFFI engine in a fresh
temporary cache. It compares 3,120 saved-function probabilities with the
unchanged Python basis, checks saved first-return hazards, and exercises the
compiled population and metric backends on two bounded synthetic trajectories.
Those are numerical implementation checks, not new LLM observations or a full
population-study rerun.

The raw archive can also be verified without extracting an additional copy:

```bash
python specs/working-packages/experiment-source-handover/raw-data/verify_raw_archive.py \
  /path/to/main_raw_data.tar.gz /path/to/DATA_MANIFEST.json
```

The external data manifest is supplied alongside the archives. Its archive
checksum is intentionally outside the archive to avoid a self-referential
checksum. The verifier reads every member and checks its size and SHA-256.
The included pickle files are the supplied research artifacts; check their
archive integrity before loading them.

## Reproduce the reporting

The explicit producer/input/output map and costly-stage recipes are in
`02_Topic/Experiment_Code/llm-convention-topology/jobs/reproduction-stages.json`.
Inspect the runnable stages with:

```bash
python 02_Topic/Experiment_Code/llm-convention-topology/jobs/reproduce_thesis.py list
python 02_Topic/Experiment_Code/llm-convention-topology/jobs/reproduce_thesis.py report \
  --package-root . --work-dir /tmp/thesis-report
```

The work directory must not exist and must be outside the immutable package
and any authoring Git checkout. The runner copies the selected source into
that directory, creates zero-copy hardlinks to the supplied raw data as input, deletes each declared
output in the new work copy, executes the actual producer, and checks the
new result against its supplied reference. Original research inputs and
archive contents are not overwritten.

The default reporting pass regenerates primary H1/H2 summaries, current
role-adjusted reporting, qualitative aggregates, saved visible response
figures, human comparisons, and the retained Study 1/Study 2, GLM and network
figures. CSV and scientific JSON outputs use explicit numeric tolerances
(rtol 1e-9, atol 1e-11). PDF checks compare page count, page size and displayed
text; relevant numeric plotted data are checked separately. PDF byte or pixel
identity is not claimed. Each stage has a log and an explicit comparison
record in `reproduction-report.json`. Approved outputs are copied immediately
into `reproduced-figures/` using the explicit manuscript-to-producer map. The
full reporting pass requires all twenty project-generated thesis PDFs there;
extra side outputs from older renderer variants cannot replace that set.
Interword dash extraction is normalized for PDF text comparison; numeric
minus signs remain significant. No plotted geometry or pixel identity is
inferred from extracted text.

Use repeated `--stage NAME` flags for a smaller declared subset. For example,
the fixed-horizon and qualitative aggregate stages use supplied research
inputs and can run without the raw archive:

```bash
python 02_Topic/Experiment_Code/llm-convention-topology/jobs/reproduce_thesis.py report \
  --package-root . --work-dir /tmp/thesis-small-report \
  --stage fixed-horizon --stage qualitative
```

## Reconstruct from raw records

```bash
python 02_Topic/Experiment_Code/llm-convention-topology/jobs/reproduce_thesis.py reconstruct \
  --package-root . --work-dir /tmp/thesis-raw-reconstruction
```

This executes the raw endpoint census and compares all usable Main final
windows and CM strict events with the retained reference rows. It also reruns
matched human windows, role sensitivities, threshold/stability analyses and
label ecology. The endpoint audit checks pickle/metadata consistency and
event-file presence. Full event-stream correspondence is a separate data
integrity check, recorded in the supplied raw verification evidence; it is
not silently inferred from file presence.

For a low-disk author check, `--raw-data /existing/experiment` uses an existing
campaign instead of extracting a second raw tree. The work directory and raw
input must be on the same filesystem for zero-copy hardlinks. These preserve
the original relative provenance paths without duplicating 11 GB of data.
Included analysis producers read this input; they do not modify the campaign.
Hardlinks are not an operating-system write sandbox.

Qualitative adjudicated codes, codebooks and sample metadata are supplied
research inputs. The aggregate stage reruns their deterministic aggregation;
it does not recreate the reviewed annotations. Saved response parameters and
population outputs retain their original source/protocol hashes. Costly full
refits and 51,020-trajectory population reruns are provided as explicit recipes
in the stage map and are not included in a quick check. Their time cost is
separate from deterministic reporting. No exact replay of historical model
sampling is claimed.

## Source refresh and release decisions

Authors can refresh the neutral source archive from the authoring checkout:

```bash
python 02_Topic/Experiment_Code/llm-convention-topology/jobs/build_reproduction_package.py \
  --project-root /path/to/master-thesis \
  --selection /path/to/master-thesis/02_Topic/Experiment_Code/llm-convention-topology/jobs/reproduction-selection.json \
  --archive /path/to/new/thesis-reproduction-source.tar.gz
```

The builder streams selected files, detects input/manuscript changes and
refuses to overwrite an existing archive. It preserves the existing relative
workspace layout so sealed producers need no source edits. The current root
`analyze.py` remains the earlier first-gate/cap pipeline; the stage map points
to the actual fixed-1,500 producer and current retrospective analyses.

`THIRD_PARTY_NOTICES.md` preserves the complete upstream Ashery MIT notice.
`CITATION.cff` provides software citation metadata without an invented DOI or
release. No new license is granted for original code or data. The external
Guilbeault Theory figure is excluded pending redistribution permission and
is listed in the manifest. No unrelated JEV/pilot raw dataset or private
working notes are supplied; mixed historical reference tables remain where
an included calculation requires them.

This preparation does not publish, submit, register a DOI or change repository
visibility. Original-code/data licensing, venue-specific anonymity and final
external access are separate release decisions. The package identifies its
current manuscript snapshot; it does not certify acceptance by a journal or
conference.
