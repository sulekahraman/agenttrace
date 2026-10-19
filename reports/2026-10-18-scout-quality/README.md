# Scout quality audit and GPT-6.1 Sol prompt replay

**October 18, 2026 — descriptive comparison, not a validated benchmark**

- `index.html`: self-contained report, with all paired explanations in an
  interactive appendix and per-turn message-type disagreements.
- `quality-report.pdf`: print edition of the report's six core sections.
- `comparison.json`: calculated counts, all 27 paired collaboration judgments,
  all 70 paired message labels, provenance, and validation results.
- `audit.json`: single-reviewer, non-blind **AI** evidence audit; not human gold.
- `replays/E1.json` through `E9.json`: new GPT-6.1 Sol outputs.
- `replays/E2.initial.json`: retained first-pass output with seven invalid short
  addressee IDs; `E2.json` explicitly records their full-roster-ID repair.
- `inputs.json`: frozen source paths, Git blob IDs, SHA-256 checksums, and sizes.
- `replay-provenance.json`: execution method, requested model, agent IDs, context
  differences, and repair disclosure.
- `build_report.py`: standard-library-only verification and report builder.

The comparison includes SHA-256 digests of every replay file, the audit, and
the execution-provenance file, tying its calculated results to these artifacts.

## What was run

The user explicitly approved **Copilot prompt replay**, because this terminal
had no Scout environment or provider API credentials. Nine agents were explicitly
configured with `gpt-6.1-sol`, one per trace.

Each agent read the original saved message prompts in chronological order and
persisted each annotation before reading the next prompt. The agent retained
earlier history, unlike independent native Scout calls. The original
collaboration prompt was read last, with its **original GPT-5.4-mini annotation
index and candidate evidence held fixed**. The new message labels did not
regenerate candidates. By the collaboration stage the agent had already seen
the message-stage prompts, so collaboration context was not perfectly isolated
either. Embedded source messages were treated as data, not instructions.

This produced **70 new message annotations and 27 new category judgments**.
It is not a native Scout API run, an end-to-end candidate-selection rerun, or a
controlled model-only comparison. No baseline outputs were overwritten, and
the replay agents were not given the saved collaboration findings.

## Baseline

The comparison uses the nine runs selected in the October 16 progress report:

- Baseline model: **`openai/gpt-5.4-mini`** for all nine.
- Eight runs: analyzer 2.1.0 / prompt 3.
- E7: analyzer 2.0.0 / prompt 2.
- Data commit: `fd0be2ee134c2a355de55f3442c167652840bedd`.
- Progress-report commit: `18a4494b46dbab49867167cf671a7e00816a84be`.

There are 70 visible posts: 59 agent posts and 11 task/operator posts. Both
versions preserve all 70 targets; agreement is also reported on agent posts
alone. Two solo traces and one task-only trace are not counted as clean
collaboration negatives. The archive contains no independent task grades,
per-agent execution logs, reliable artifact-write timeline, or native Scout
generation-event/token logs.

## How to interpret quality

The clearest baseline errors are duplicated-work flags in E6 and E9: deliberate,
requested verification is explicitly excluded by the scanner definition.
Other cells depend on how to interpret ownership overlap, asynchronous
visibility, and recovered information mismatches.

The parent assistant reviewed all visible agent posts and all 27 category
cells. That reviewer had already seen parts of the baseline report, so the
audit is explicitly **non-blind**, AI-generated, and provisional. The audit is
not independent human ground truth, including when it disagrees with the Sol
replay. Neither model disagreement nor agreement with this audit establishes
accuracy.

Do not infer a population false-positive/false-negative rate, precision,
recall, causal model improvement, or distinct failure-episode count from the
raw flag totals. Message-type agreement is not message-classification accuracy.
The report retains ambiguity rather than forcing uncertain cells into a
confusion matrix.

## Rebuild the comparison without any model calls

From the repository root, with Python 3 and an authenticated GitHub CLI:

```bash
python3 reports/2026-10-18-scout-quality/build_report.py \
  --inputs .agenttrace/scout-quality-baseline \
  --download-baseline --self-test
```

The downloader retrieves only the pinned public evidence needed for these
nine traces and verifies each file against its Git blob ID. Later rebuilds
reuse that cache and verify both Git blob IDs and SHA-256 checksums:

```bash
python3 reports/2026-10-18-scout-quality/build_report.py \
  --inputs .agenttrace/scout-quality-baseline --self-test
```

The builder recalculates comparison JSON and HTML from the **saved** replay
outputs. It does not reproduce model generations or regenerate the PDF.
Inspect the HTML in Chrome and use **Print → Save as PDF** (A4, background
graphics enabled, browser headers/footers disabled) for its print edition.
The HTML appendix is intentionally omitted from print; full raw explanations
remain in the HTML and JSON.
The saved PDF's local artifact links were converted from machine-specific
`file:` URLs to relative paths; its frozen GitHub source links remain absolute.

To repeat inference, use the pinned original prompts and explicitly document
the new execution surface, model, settings, context isolation, costs, failures,
and any output repairs. For a controlled native comparison, configure a real
Inspect-supported provider outside chat, keep code/prompts/caps/settings fixed,
and evaluate against independently adjudicated labels.
