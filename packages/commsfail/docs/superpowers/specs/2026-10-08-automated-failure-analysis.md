# Automated Failure Analysis

## Goal

Run communication-failure analysis without human annotation. For each multi-agent research record, two independent annotator agents produce incident candidates, a judge settles the record, and a final grade-aware verdict attributes lost rubric items.

## Production contract

- Input: a SharedNet goal-run record with `episode.json`, `room.ndjson`, `wakes.ndjson`, `checks.ndjson`, `score.json`, agent logs, and `workspace.git`.
- Scope for the first batch: `/mnt/data0/ldav/RAC-exp/exp2/repeat1/records/research__*__n[234]__r1`, exactly 30 records. The ten `n1` records remain baselines and are not communication-incident inputs.
- Runner: `gpt-6-luna`, reasoning effort `high`, three retries after the first attempt, image `commsfail-agent-annotator:0.1`.
- Concurrency: two records at a time. Within one record, annotators A and B remain independent and run in parallel; judge and verdict follow serially.
- Every attempt uses a fresh record output directory. Existing output is never silently reused or mixed with a new bundle.
- A graded record is complete only when `annotation.json` names `commsfail/annotation.v1`, matches the source run id, has evidence level E3, and contains a non-null verdict; all expected component files must exist.
- A failed record remains on disk for diagnosis. A later batch invocation preserves it before opening a fresh attempt.
- Batch output includes per-record logs and a machine-readable summary. The process exits nonzero if any selected record is incomplete.
- The outputs are automated annotations, not human gold. A/B agreement, retries, rejections, and undecidable classes travel with all aggregate results.

## Repository boundary

The per-record pipeline and batch runner live in `commsfail`. Cross-record statistics and paper figures may consume its records elsewhere, but must not reimplement the annotator.
