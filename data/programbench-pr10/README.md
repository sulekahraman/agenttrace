# ProgramBench: commsfail PR #10

Twelve public Goal Run records from
[xisen-w/commsfail#10](https://github.com/xisen-w/commsfail/pull/10), pinned to
`913ad1805642a38e5248d67e5d8c3b83c48b51b5`.
The PR was open when acquired; this snapshot is not evidence of an upstream
merge. Nine `burntsushi__xsv.f430466` runs cover 2/3/4 agents with three
repetitions each. Three `sclevine__yj.8016400` runs cover 2/3/4 agents once each.
Experiments occurred on October 15, 2026; analysis was added October 17.

This cohort contains **618 raw room posts, 602 agent posts, 195 turn-log files,
2,322 parsed operations, and 1,874 completed commands**. There are no runner
check records or hidden-test evaluation scores. Every episode records a
`said DONE` stop with consensus enabled; that is not a task-success grade.

The [presentation addendum](../../reports/2026-10-17-programbench/) keeps these
records separate from the original nine conversation-only shares. The original
dataset and October 16 report remain unchanged. Across both cohorts there are
21 experiment traces, not 21 independent task types or a controlled comparison.

## Contents and provenance

| Path | Contents |
| --- | --- |
| `sources/{xsv,yj}-2026-10-15/` | Byte-identical source copies, task instructions, original READMEs and file manifests |
| `manifest.json` | Pinned upstream revision, inventory, reader source hash, and selected/history counts |
| `batch-input.json` | Stable saved trace IDs for the batch CLI |
| `batch/` | All 60 selected analyses and per-trace reports, with local viewing links |
| `batch/all-cohorts.html` | Local links to 96 selected results across both published cohorts |
| `history/` | Four earlier batch indices and all eight failed-attempt records |
| `agenttrace.sqlite3` | Frozen backup for these 12 traces and their complete analysis history |
| `runs/` | Saved Scout prompt/result artifacts, including incomplete attempts |
| `SHA256SUMS` | Integrity hashes; excludes this README and the checksum file itself |

There are 36 substantive offline analyses (12 structural, 12 regex, 12
`facts_v1`), 12 optional demo-plugin runs, and 12 completed Scout runs.
Demo output is not an additional validated detector. Failed attempts are
retained separately from the selected completed results.
The frozen snapshot contains **68 historical analyses: 60 completions and eight
failed Scout attempts**. Selected Scout versions are seven runs at 2.1.0 /
prompt 3, four at 2.1.1 / prompt 4, and one at 2.1.4 / prompt 7.

The original upstream copy manifests cover 255 raw files. Their hashes and
byte lengths were checked before analysis. Original source bytes were not
edited or experiments rerun.

Two reader corrections were needed in AgentTrace's imported commsfail:
split JSONL on `\n`, not Unicode-aware `str.splitlines()`, and link all message
IDs from compound `sharednet say` commands. This recovers one completed command
and five DONE-post links. All 602 agent posts now link to their operations;
all 1,874 raw completed command events are retained. Multiple posts from one
compound command share its operation boundary; intra-command timing is not
reconstructed. Raw command output in normalized operations is still capped at
500 characters; the full original streams remain in `sources/`.

The first Scout pass hit exact-evidence validation limits on five traces.
Retry feedback was enhanced to identify rejected spans and allowed reply
numbers, and the final scanner prompt explicitly maps candidate display labels
to original turn numbers. Validation was not relaxed or made unbounded.
Successful runs were reused. Selected
results retain their actual analyzer/prompt versions and dates; they are not
relabeled to a common version. The model is `openai/gpt-5.4-mini`.

Scout labels **602 agent messages**, not the 618 raw posts: the Goal Run loader
identifies goal/runner roles, which the UI/Scout adapter excludes. Earlier share
snapshots lacked those roles and their saved Scout results include task posts.
Do not silently pool these differing annotation denominators.

## Restore both cohorts without model calls

Follow the root installation instructions and build the frontend. From the
repository root, with port 3001 available:

```bash
source .venv/bin/activate
python3 tools/restore_results.py data/teammate-traces data/programbench-pr10 \
  --output .agenttrace/all-teammates
export AGENTTRACE_DATA_DIR="$PWD/.agenttrace/all-teammates"
export AGENTTRACE_SCOUT_VIEWER_URL=http://127.0.0.1:7577
PORT=3001 agenttrace
```

The restore command refuses an existing output directory or overlapping trace/
run IDs and never changes the checked-in snapshots. To restore only the new
cohort, omit `data/teammate-traces`. On subsequent starts, reuse the working
directory; do not restore over it.

Open <http://127.0.0.1:3001/> and open `batch/all-cohorts.html` locally for links
to every selected result. The links require this working copy and port 3001;
they are not a hosted website. The JSON reports can also be read directly on
GitHub without either service.

For the native viewer, in a second terminal with the same working directory:

```bash
source .venv/bin/activate
DATA_DIR="$PWD/.agenttrace/all-teammates"
mkdir -p "$DATA_DIR/scout-view/transcripts" "$DATA_DIR/scout-view/scans"
scout view --transcripts "$DATA_DIR/scout-view/transcripts" \
  --scans "$DATA_DIR/scout-view/scans" --host 127.0.0.1 --port 7577
```

Click **Open in Scout** on a completed result. This regenerates native viewer
files from saved judgments using `mockllm/model`, with no provider generation.
Do not click **Run Scout** merely to view the existing analysis.

## Reproduce analysis and preserve its limits

Offline reruns against the restored traces:

```bash
agenttrace-batch data/programbench-pr10/batch-input.json \
  --server http://127.0.0.1:3001 --output .agenttrace/pr10-offline-rerun --rerun
```

Adding `--scout --model openai/gpt-5.4-mini` explicitly sends the visible
messages to the provider and may incur charges. With `--rerun`, it requests
new completed Scout analyses too; without it, the batch CLI reuses saved
completed results.

Model judgments and rule flags are **not validated failure labels**.
The report's deterministic citation audit finds **20 of 36 Scout finding
records** whose narrative `[M#]` references are not fully represented in their
structured original-turn lists. Both representations are preserved unmodified;
saved native replay uses structured IDs, not an automatic repair of the
narrative. Check the original room posts rather than relying on those
click-through references for conclusions.
The report audits the four `facts_v1` flags and explains why their cited
evidence does not establish task failure. Zero flags elsewhere is not a pass.
Recorded runner runtime/token counters are not provider billing; raw usage
events should not be naively summed without confirming counter semantics.

Full sessions, workspace snapshots, evaluation artifacts and Scout generation
event/token logs are not included. Credentials, dependency environments and
machine-specific native viewer caches are excluded. This is a publication
mirror of already public PR inputs, not permission to publish future private
traces. See [future storage guidance](../../docs/experiment-storage.md).
