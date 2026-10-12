# Automated Failure Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the incident annotator safe to run unattended over the 30 research n=2/3/4 records, publish it on a reviewable remote branch, and launch the batch.

**Architecture:** Harden the existing single-record pipeline at its two unsafe boundaries, then add a small Python batch orchestrator that selects records, runs two cases concurrently, validates completed artifacts, preserves failed attempts, and writes a summary. Keep model execution in the existing Docker runner and keep aggregation outside the single-record annotation logic.

**Tech Stack:** Python 3.10+, pytest, concurrent futures, subprocess, Docker, Codex CLI 0.160.1.

**Spec:** `docs/superpowers/specs/2026-10-08-automated-failure-analysis.md`

## Global Constraints

- Model `gpt-6-luna`, effort `high`, retries `3`, image `commsfail-agent-annotator:0.1`.
- Two records concurrently; A/B remain parallel inside each record.
- Graded success requires a non-null verdict and all component artifacts.
- Never mix output from separate attempts; preserve failures for audit.
- No human labels or human adjudication are part of this workflow.

## Review Focus

- Verdict exhausts all retries: the record must fail loudly, never report success with `null`.
- Nonempty output directory: annotation must stop before altering or mixing its contents.
- Interrupted batch followed by resume: valid records skip, incomplete records are preserved, and only incomplete work reruns.
- Malformed or mismatched annotation: post-validation rejects it and makes the batch exit nonzero.
- Worker failure: other selected records finish, the failure appears in the summary, and the overall exit is nonzero.

---

### Task 1: Harden one-record annotation

**Files:**
- Modify: `commsfail/annotators/standard/pipeline.py`
- Modify: `tests/test_annotation.py`

**Interfaces:**
- Consumes: existing `annotate(src, out, runner, grade=None, retries=3)`.
- Produces: the same interface, with a fresh-output precondition and a raised `RuntimeError` when graded verdict validation exhausts retries.

- [ ] Add a test proving a nonempty output directory is rejected without changing its sentinel file; run it and observe the expected failure.
- [ ] Add the minimal fresh-output check; run the focused test and observe it pass.
- [ ] Add a test whose verdict runner never returns valid output and assert `RuntimeError` plus no successful `annotation.json`; run it and observe the expected failure.
- [ ] Raise after verdict retry exhaustion and write `verdict.json` only for a valid verdict; run the focused test and the complete suite.

### Task 2: Add resumable batch execution and validation

**Files:**
- Create: `commsfail/annotators/standard/batch.py`
- Modify: `commsfail/annotators/standard/__init__.py`
- Modify: `commsfail/cli.py`
- Create: `tests/test_annotation_batch.py`

**Interfaces:**
- Produces: `validate_completed(out, expected_run, require_verdict=True) -> list[str]` and `run_batch(src_root, out_root, pattern, workers, model, effort, image, retries) -> dict`.
- CLI: `commsfail annotate-batch SRC_ROOT --out OUT_ROOT [--pattern ...] [--workers 2] [--model ...] [--effort high] [--image ...] [--retries 3]`.

- [ ] Write validation tests for complete, missing, malformed, wrong-run, wrong-evidence, and null-verdict outputs; verify RED.
- [ ] Implement `validate_completed`; verify GREEN.
- [ ] Write batch tests for selection, two-worker execution, resume, failed-attempt preservation, logs, summary, and nonzero CLI failure using a fake subprocess boundary; verify RED.
- [ ] Implement the minimal orchestrator and CLI; verify focused tests and then the complete suite.

### Task 3: Document and publish the automated protocol

**Files:**
- Modify: `commsfail/annotators/standard/README.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces: one canonical single-run command, one canonical 30-run command, acceptance rules, resume behavior, and the explicit automated-not-gold caveat.

- [ ] Update the documentation to match tested behavior and fill the currently empty validation/strength sections.
- [ ] Run documentation examples through CLI `--help`, run `git diff --check`, and run the full test suite.
- [ ] Commit, push `feat/agent-annotator`, create a PR against `feat/taxonomy-per-annotator`, and attach the PR to this task.

### Task 4: Launch and supervise the 30-record batch

**Files:**
- Output only: `/mnt/data0/xisen/workspace/runs/failure-analysis-auto-2026-10-08/research-main-v1/`

**Interfaces:**
- Consumes: the committed feature branch and the 40-record research source directory.
- Produces: 30 validated annotation folders, logs, and `summary.json`.

- [ ] Verify the source selector returns exactly 30 complete n=2/3/4 records and the Docker image/auth prerequisites exist.
- [ ] Launch `annotate-batch` in a durable background session with two workers.
- [ ] Inspect early progress and verify at least one completed record passes the same automatic validator.
- [ ] On completion, rerun incomplete records, generate the final summary, and report exact completed/failed counts and artifact paths.
