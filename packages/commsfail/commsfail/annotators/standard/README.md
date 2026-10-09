# standard

Failure incidents in one run, annotated by agents:
- Two agents annotate the run independently.
- A judge agent settles the final record.
- Every reply passes deterministic checks before it is kept. A reply that fails goes back to its agent with the reasons.
- Only after the record is final does a last agent see the grade, and it says what cost each rubric item.

`standard` is the standard automated failure-analysis pipeline, alongside the other methods in `commsfail/annotators/`. Run it with `commsfail annotate` or `commsfail annotate-batch`. It calls a model and writes `commsfail/annotation.v1`, preserving prompts and raw replies. The other methods run offline through `commsfail analyse --annotator NAME`.

## Running it

```bash
docker build -t commsfail-agent-annotator:0.1 tools/agent-annotator      # Codex CLI 0.160.1, once
commsfail annotate runs/goal-run --out out/fresh-goal-run \
  --grade runs/goal-run/score.json --model gpt-6-luna --effort high --retries 3
```

The agents run as Codex (`--model`, default `gpt-6-luna`; `--effort`) in a container:
- capped at one CPU and 2 GB;
- run as your user;
- with the bundle mounted read-only;
- with no web search;
- with nothing of the host except their own output folder and the Codex login (`~/.codex/auth.json`).

From Python, pass any `runner(workdir, prompt, tag) -> last message` in place of `DockerCodex`. The tests use a fake one.

## The input

The input is a goal-run record. It holds the posts, the runner's record (`wakes.ndjson`, `checks.ndjson`, `episode.json`, and `workspace.git` when present) and, when available, each agent's own log (`agents/<seat>/turn-NNN.jsonl`). The evidence level says what the input can show:

| level | input | what it can decide |
|---|---|---|
| E1 | posts only | every class except `unsaid`, from the text alone |
| E2 | + the runner's record | what each agent had received when it posted |
| E3 | + the agents' logs | `unsaid`, and claims checked against what the agent did |

Uploading the agents' logs is recommended. Without them, `unsaid` is listed in `undecidable`, and nothing is reported for it.

## What the agents read: the bundle

`bundle/` holds no grade and no condition:
- `timeline.md`: every post and turn boundary in time order. It also says how the runner ends a run and what the check tests, and next to each post, what its author had received when it posted. "Had received" is the turn's hand-off, plus the agent's own reads of the board during the turn.
- `agents/<seat>.md`: each agent's commands, file changes, reads and posts, with ids `<seat>:<turn>:<i>`.
- `workspace.md`: the files at the end, the snapshot after each post, the report, and the code.
- `task.md`: the goal post.
- `codebook.md`: the six classes of `state_gap`, their patterns, the rule that classes a failure, and the severity scale.

## The unit: an incident

An incident is one failure, spanning 1 to n posts:

```json
{"id": "I2", "posts": [33, 35, 37, 38], "anchor": 38, "actions": ["codex-2:2:14"],
 "class": "unreceived", "pattern": "premature_final",
 "class_reason": "1 holds: P35 asked for the fix. 2 fails: codex-2 had received up to P31 when it posted P38",
 "cause": "codex-2 did not read the board again before declaring done",
 "consequence": "the abstract kept the old AP; the rerun was cut",
 "severity": 4, "severity_reason": "4: a required part (the report's headline number) is wrong",
 "repaired": false, "source": "agents", "confidence": "high", "items": ["W3"]}
```

- `anchor` is the first step that broke. Ask the codebook's six questions in order: the class is the first one answered "no".
- `source` is `harness` when the runner caused the gap. An example is a run ended on a post that only mentioned the word DONE.
- `severity` measures what happened to the work, read from the trace:

| | |
|---|---|
| 1 Negligible | caught and resolved within the next exchange; nothing redone or lost |
| 2 Friction | time, tokens, or posts spent on the repair; the work is unchanged |
| 3 Waste | substantial work duplicated, discarded, or overwritten, or the product left inconsistent; every required part delivered |
| 4 Damage | a required part missing, wrong, or unreviewed because of it |
| 5 Breakdown | the core result not delivered, or invalid, or the run derailed |

## The steps

1. **Bundle.** It is built deterministically from the record.
2. **Annotators A and B**, in parallel. Each returns `items`, `incidents`, `undecidable`, and a `sweep`: one note for every agent post, naming the incidents that include it.
3. **Checks** (`check.py`). A reply that fails goes back with the list of problems, at most `--retries` times. The checks are:
   - the reply parses;
   - every post and action exists, and the anchor is one of the incident's posts;
   - the class is one of the six, and the pattern is in the catalog, belongs to that class, and is neither overhead nor out of scope;
   - the severity is 1 to 5, and its reason starts with the level;
   - `unsaid` appears only at E3;
   - an `unreceived` incident involves a post that its acting agent had not received;
   - the sweep covers every agent post exactly once and agrees with the incidents.
4. **Agreement** (`agree.py`) between A and B:
   - two incidents match when they share the anchor, or when half their posts overlap;
   - it reports incident F1, Cohen's kappa on class, and quadratic weighted kappa on severity.
   - With a handful of incidents per run, kappa is undefined or noisy. Pool it over a batch.
5. **Judge.**
   - It merges each pair, and keeps or rejects each unpaired incident, with a reason.
   - It may add an incident both annotators missed, citing evidence.
   - The checks require every A and B incident to be used exactly once.
   - A repaired gap is kept at a low severity; it is never rejected for doing no harm.
6. **Verdict**, only with `--grade`. It sees the grade only now, after the record is final. For each rubric item that lost points, it names the cause: `incident` (by id), `capability`, `collective_judgement`, `task_data`, `harness`, or `grader`. It also says whether the incidents explain the score.

## Output

```
out/bundle/          what the agents read
out/A.json B.json    the two annotations, after their checks
out/agreement.json   how far A and B agree
out/final.json       the judge's record
out/verdict.json     with --grade
out/annotation.json  all of it as commsfail/annotation.v1, with the attempts each step took
out/attempts/        every prompt and raw reply
```

## Fully automated research batch

No human annotation or adjudication is required. The production scope is the 30 research
main-experiment records with n=2/3/4; n=1 stays a baseline.

```bash
commsfail annotate-batch /mnt/data0/ldav/RAC-exp/exp2/repeat1/records \
  --out /mnt/data0/xisen/workspace/runs/failure-analysis-auto-2026-10-08/research-main-v1 \
  --pattern 'research__*__n[234]__r1' --workers 2 \
  --model gpt-6-luna --effort high --retries 3 --image commsfail-agent-annotator:0.1
```

Each case runs A/B in parallel, followed by judge and verdict. `--retries 3` means at most
four attempts per step. The batch checks all component JSON files, schema, run identity,
E3 evidence, incident checks, and a valid non-null verdict. Exhausted steps fail the case.
Two batches cannot own the same output root concurrently.

Repeat the same command to resume: validated cases are skipped; incomplete directories and
logs move to `failed-attempts/` before a fresh attempt. A configuration change requires a new
output root. Treat input records as immutable while running or resuming. A single-record
`annotate` command rejects nonempty output directories.

`summary.json` updates after each case with completed, failed and pending counts;
`logs/<run>.log` holds each process log. The batch finishes the other cases after a failure
and exits nonzero if any case failed. Preserve `config.json`, summaries, A/B agreement,
retries, rejections and undecidable classes with analyses. These are **automated annotations**.

## How it was checked

The offline test suite covers bundle construction, incident and sweep checks, judge accounting,
agreement, retries, verdict exhaustion, output preservation, batch selection, two-worker execution,
resume and malformed-output rejection. Run `.venv/bin/pytest` from the repository root.

The previous v7 evaluation completed eight research cases with `gpt-6-luna --effort high`.
Its comparison used a single-analyst reference, not a human gold standard. Live production
acceptance uses the same deterministic validator as batch resume.

## Good at, weak at

The pipeline can connect posts with agent actions and attribute lost rubric items after blind
incident annotation. Deterministic checks establish structural consistency and evidence references;
they do not prove causal judgments. A/B can share model biases, incidents may be missed or split,
and class/severity agreement is noisy on small per-run samples. Report the automated provenance
and aggregate agreement alongside findings.

## Rules

1. The annotators and the judge never see the grade. The verdict step sees it, after the record is final, and cannot change the record.
2. Annotations are data. Keep them with the experiment, not in this repository.
3. A change to a prompt or a check changes the output for the same run. Say so in the CHANGELOG, and re-run the runs listed in "How it was checked".
