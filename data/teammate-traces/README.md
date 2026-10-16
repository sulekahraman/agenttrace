# Public teammate trace dataset

This is a frozen, explicitly approved public snapshot of the nine teammate
traces analyzed with AgentTrace. Clone the repository to get the data and view
the saved results locally; no hosted service or provider API key is needed.

The project proposal and progress are tracked in
[xisen-w/multi-agent-training](https://github.com/xisen-w/multi-agent-training).
The nine SharedNet source links were supplied directly by teammates: four
from Aziz and five from Xiangqian/Forward. They were not discovered by
enumerating Slack, and this is not a complete inventory of the team's traces.
Xisen's traces and `xisen-w/rac` are outside this dataset.

## Contents

| Path | Contents |
| --- | --- |
| `manifest.json` | Source attribution, trace IDs, snapshot counts and file locations |
| `sources/<slug>/trace.json` | Original SharedNet share snapshot; available offline |
| `sources/<slug>/transcript.txt` | Plain-text conversation |
| `sources/<slug>/agent-only-metrics.json` | Metrics excluding task/operator posts |
| `batch/index.json` | Selected completed runs, provenance and local analysis links |
| `batch/trace-*/` | Readable JSON reports and the selected individual analysis records |
| `batch/links.html` | Clickable links to all 36 selected completed analyses |
| `agenttrace.sqlite3` | Consistent SQLite backup containing the nine canonical traces and their full saved run history |
| `runs/<run-id>/` | Saved Scout prompts and result artifacts, including incomplete historical attempts |
| `SHA256SUMS` | Checksums of the frozen data files |

Raw transcripts and prompt artifacts retain their original whitespace;
dataset-specific Git attributes prevent line-ending conversion and whitespace
cleanup from changing the saved evidence.

The selected cohort results comprise **27 offline analyses and nine completed
Scout analyses**, with **70 message annotations and 27 collaboration-category
judgments**. The offline results include nine optional `example_kickstart`
demo-plugin runs; these are examples, not an additional validated detector.
The snapshot database additionally retains earlier runs, including eight failed
Scout attempts. See `manifest.json` for the full historical run counts; failed
attempts are not counted as completed cohort results.

The traces contain 70 visible posts: 59 agent posts and 11 task/operator posts.
`facts_v1` is unavailable because the shares do not contain per-agent execution
logs. Scout's findings are model judgments, not verified failures or ground truth.
The model, analyzer/prompt versions and timestamps are preserved in each run.
Inspect Scout's original generation-event logs and token accounting were not
captured and cannot be reconstructed from these results.

## Restore and open the saved analyses

First follow the repository's [local installation instructions](../../README.md#run-locally).
With dependencies installed, run `make build` once to prepare the web UI.
Then run these commands from the repository root, with any previous AgentTrace
server stopped:

```bash
source .venv/bin/activate
export AGENTTRACE_DATA_DIR="$PWD/.agenttrace/teammates"
mkdir -p .agenttrace
mkdir -m 700 "$AGENTTRACE_DATA_DIR" &&
  cp data/teammate-traces/agenttrace.sqlite3 "$AGENTTRACE_DATA_DIR/" &&
  cp -R data/teammate-traces/runs "$AGENTTRACE_DATA_DIR/" &&
  agenttrace
```

The non-recursive `mkdir` intentionally refuses to overwrite an existing
restoration. Keep the checked-in snapshot unchanged; all subsequent API writes
belong in the ignored `.agenttrace/teammates` working copy.

Open <http://127.0.0.1:3000/> and then open
`data/teammate-traces/batch/links.html` in your browser. The links select the
original saved trace and run IDs. They work with the restored database on port
3000, not directly on GitHub.

On subsequent starts, do not copy the snapshot again:

```bash
source .venv/bin/activate
export AGENTTRACE_DATA_DIR="$PWD/.agenttrace/teammates"
agenttrace
```

To read the reports without running either service, browse the JSON files in
`batch/` or the plain-text transcripts in `sources/` directly on GitHub.

## Open the same saved judgments in native Scout

The standard `make install` includes Scout. If using a model-free minimal
installation, install `./packages/agenttrace-api[scout]` into the same virtual
environment first. In a second terminal, from the repository root:

```bash
source .venv/bin/activate
DATA_DIR="$PWD/.agenttrace/teammates"
mkdir -p "$DATA_DIR/scout-view/transcripts" "$DATA_DIR/scout-view/scans"
scout view --transcripts "$DATA_DIR/scout-view/transcripts" \
  --scans "$DATA_DIR/scout-view/scans" --host 127.0.0.1 --port 7576
```

In AgentTrace, open a completed Scout result and click **Open in Scout**.
AgentTrace regenerates the native viewer files from the saved judgments for
your filesystem. This replay uses `mockllm/model`, makes no provider model
calls, and retains the original model provenance. Machine-specific native
scan caches, absolute-path manifests and native deep links are deliberately
not committed.

Do not click **Run Scout** to view existing results: that starts a new analysis
and may incur provider charges. Native Scout's own new-scan controls are also
separate from viewing these saved replays. Keep both services on loopback.

## Provenance and publication boundary

This snapshot was exported on October 16, 2026, from results produced with
AgentTrace commit `2a118aac8bdbc1eed77bed47fc432146770d65e8`; individual runs
retain their own historical versions. The live working database was backed up
with SQLite's backup API, then the unrelated demonstration trace and its runs
were removed from the backup. The source database was not modified.

The original offline-era summary and presentation handout are not included:
the selected JSON exports and database are authoritative for the completed
Scout results. No `.env`, provider credentials, dependency environments or
native viewer caches are included.

These source links and conversation contents are intentionally public with
the dataset owner's approval. This is an exception for this dataset, not
permission to commit future private traces, share-link capabilities or keys.
Public availability does not grant additional rights in upstream tasks or
third-party content; respect their applicable terms.
