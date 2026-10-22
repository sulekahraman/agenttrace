# AgentTrace

AgentTrace combines the existing React trace explorer, reusable `commsfail`
analysis, and Inspect Scout in one monorepo. Structural metrics and offline
annotators work without a model; Scout and experimental communication-incident
analysis run only when explicitly requested.

| Path | Responsibility |
| --- | --- |
| `apps/web` | React, Observable Plot, linked filters, findings and evidence |
| `packages/commsfail` | Independently installable trace loaders, schemas, offline plugins and CLI |
| `packages/agenttrace-api` | FastAPI, persistent analysis runs, structural heuristics and Scout orchestration |
| `fixtures` | Shared sample trace and frozen pre-migration metric baseline |
| `data/teammate-traces` | Approved public dataset: nine teammate traces, saved analyses and restoration instructions |
| `data/programbench-pr10` | Twelve public ProgramBench Goal Runs, saved offline/Scout results, logs and combined viewing links |

The imported `commsfail` history and MIT license are preserved. AgentTrace's
offline heuristic plugin is registered through `commsfail.annotators`, rather
than adding application-specific dependencies to `commsfail`.

## Saved teammate results

**Latest: [Fresh Scout + communication v0.3 — October 21 cohort](reports/2026-10-21-v03-12-runs/README.md)**:
fresh Scout annotations and seven-metric results for all 12 ProgramBench runs,
with per-run AgentTrace visualization links and downloadable evidence.
**Mixed communication-review protocol:** six runs completed independent A/B
reviews plus a judge; after nine review jobs failed, the user approved direct,
non-blind parent-session recovery for the other six. Those recoveries inspected
all agent posts and selected full native details, not the complete A/B windows.
The report distinguishes these methods and explains each Unknown; this is not
a uniform independent-review benchmark.

**[Richer-evidence reassessment — October 19](reports/2026-10-19-richer-evidence-12-runs/README.md)**:
all seven metrics across the same 12 ProgramBench runs, with explicit metric
definitions, Yes / No / Unknown decisions, and per-run annotator A/B versus
final-adjudicator comparisons. The communication rerun retains nine supported
failure incidents and six unresolved candidates; Scout flags are unchanged.
Download the report HTML to share its tables and expandable findings.
Visualization links require a local or shared AgentTrace viewer.

**[ProgramBench addendum — October 17](reports/2026-10-17-programbench/README.md)**:
12 additional runs (nine xsv, three yj), 60 selected completed analyses, and a
six-page presentation PDF/HTML. Includes execution-log coverage, an audit of
all four facts_v1 flags, and explicit Scout citation/label limitations.
There are now **21 traces and 96 selected analyses** across two separate cohorts.
[Restore both datasets without model calls](data/programbench-pr10/README.md)
and use the [combined local result links](data/programbench-pr10/batch/all-cohorts.html).
See [repository roles and future experiment storage](docs/experiment-storage.md).

**[Professor-facing progress report](reports/2026-10-16-progress/README.md)**:
eight briefing pages plus an evidence/reproducibility appendix, available as a
presentation PDF and self-contained HTML. It covers the inspected experiments,
analysis method, preliminary observations, and limitations without treating
Scout judgments as verified task failures.

[Browse the public dataset and restore instructions](data/teammate-traces/README.md)
for the nine analyzed teammate traces: 27 selected offline analyses, nine
completed Scout analyses, 70 message annotations and 27 collaboration-category
judgments. The checked-in SQLite snapshot restores the saved history into a
separate local working directory. JSON reports and transcripts are readable
directly on GitHub. Viewing the saved results, including regenerated native
Scout replays, requires no model API key or new inference.

## Run locally

Use Python 3.10+ and Node 22+. From the repository root:

```bash
python3 -m venv .venv
make install
npm start
```

Open `http://127.0.0.1:3000`. Choose a SharedNet public share link or upload a
SharedNet share JSON file. To try the UI without network access, upload
`fixtures/ui-share.json`.

For development, run these in separate terminals:

```bash
make api
make dev
```

The Vite development server proxies `/api` to the Python server on port 3000.
The production Python server serves the built `apps/web/dist` directly.
The old Node HTTP server and browser-side analysis engine have been removed.

## Analysis

Ingestion stores a canonical `commsfail.Trace` and runs
`agenttrace_heuristics_v1` and `regex_v1` offline. The UI preserves the timeline,
contribution chart, transition matrix, search, filters and expandable messages.
Offline communication findings and Scout findings have separate result panels;
evidence buttons jump to the cited original message.

Annotator availability is checked against the loaded trace. `facts_v1`
compares what agents said with their own execution logs, so it is disabled
for public share links and share JSON. Use `regex_v1` for those sources;
`facts_v1` requires a local goal-run record containing per-agent logs.

The selector uses descriptive cards: **Conversation patterns** (`regex_v1`)
and **Claims vs. actions** (`facts_v1`). Cards show source requirements,
availability and run status; installed plugins remain selectable.

Scout defaults to `openai/gpt-5.4-mini`. Select **Run Scout** for asynchronous
message annotation and collaboration scanning, or edit the `provider/model`
identifier to use another provider. `AGENTTRACE_SCOUT_MODEL` overrides the
default. Missing Scout dependencies or a missing OpenAI key open setup
instructions without creating an analysis run. **Provider setup** also opens
these instructions on demand. The check verifies package/key presence, not
key validity, billing or model access.

Create an OpenAI key in the API dashboard and enable API billing/credits;
a ChatGPT subscription does not include API usage. Stop the existing server
with Ctrl+C in its terminal. If it is running in the background, identify and
stop that specific AgentTrace process; do not reuse a PID from old instructions.

From the repository root, activate the Python environment where you installed
AgentTrace (`source .venv/bin/activate` for the default setup; use your
environment's name if different). Use a hidden prompt to avoid typing the key
directly into command history, then restart from that same terminal.

macOS / zsh:

```zsh
read -s "OPENAI_API_KEY?Paste your OpenAI API key: "; echo
export OPENAI_API_KEY
agenttrace
```

Bash / Linux:

```bash
read -r -s -p "Paste your OpenAI API key: " OPENAI_API_KEY; echo
export OPENAI_API_KEY
agenttrace
```

Setup commands use the activated environment, not machine-specific paths.
Keep the server terminal open, refresh the UI and click
**Run Scout**. The key is inherited by the server process, not saved to a
configuration file; a new terminal does not automatically inherit it.
For other providers, configure their server-side
credentials according to Inspect's provider guide.
Never paste API keys into chat, browser storage or exports, or commit them to Git.
**Scout sends trace content to that provider and may incur charges.** The
application does not invoke a model during ingestion.

Scout checks duplicated work, weak handoffs and unintegrated information.
Results include coverage, citations, model/prompt/package provenance and
explicit failures. Invalid message annotations receive validation feedback
and are regenerated up to three attempts per message; each attempt may incur
provider charges. Evidence must still match the target message verbatim,
with at most three spans total. Exhausted retries fail the run rather than
discarding invalid evidence or reporting success. Provider errors are not
retried by this annotation-validation loop. Correction feedback identifies
rejected spans and allowed reply IDs; candidate prompts explicitly map Scout
display citations to original turn IDs, which can have gaps. Saved results
retain their original versions; structural validation does not guarantee that
narrative citations or semantic judgments are correct. Traces and run history persist in
`.agenttrace/agenttrace.sqlite3`; prompt/result artifacts live under
`.agenttrace/runs/<run-id>/`. Interrupted jobs are marked failed on restart,
not retried automatically. Re-ingesting unchanged content reuses its trace;
changed content receives a new identifier.

### Communication failure incidents (experimental)

**Run communication analysis** selects the separate `communication_failures_v1`
setup: Disclosure, Delivery, Reading and Action. Scout's three collaboration
flags and historical results are unchanged. The new setup uses independent
A/B evidence searches, full-window reviews and adjudication, exact evidence validation, and the first
failed transition per incident. Results distinguish supported failures,
assessable searches with no failure found, undecidable attribution and
solo/not-applicable input. Repaired failures still count, with recovery recorded.
A directly observed breakdown can count without proven downstream harm;
impact and uncertainty reasons are recorded separately.

The default model is `openai/gpt-5.4-mini`; set
`AGENTTRACE_COMMUNICATION_MODEL` or edit **Communication model** to override it.
Use **Communication provider setup** for dependency/credential checks. The
same API `scout` extra supplies Inspect provider support; this does not run
Scout's scanners. Five model steps are required for multi-agent traces:
two independent searches, two independent reviews and one judge, with up to
three validation attempts per step (normally 5, at most 15 application generation
attempts; solo input uses 0). Provider errors fail explicitly instead of becoming negatives.
**Running sends supplied messages and execution evidence to the configured
provider and may incur charges.** Ingestion and viewing saved results do not.

Allowlisted local ingestion freezes full supported Codex command outputs
alongside normalized operations. Existing saved traces without this snapshot
use normalized evidence only, never arbitrary paths in stored source metadata.
When present, the v0.2 communication importer also validates input/action
manifests against native sessions and imports batch workspace snapshots.
Receipt comes from recorded model-visible outputs, not merely command stdout.
Core summaries precede lower-priority full-detail events in the bounded input;
clipping and omissions remain explicit. In v0.3, detail discovery is actor-balanced;
requested actor/time windows restore full evidence without clipping. Scoped
completeness, rather than unrelated omissions elsewhere, governs absence claims
and negative searches. Over-budget retrieval fails explicitly, never silently
truncates evidence. Re-ingest an enriched local export to
refresh its saved evidence; historical analysis records remain unchanged.
Each run retains its evidence hash, configuration hash, taxonomy/prompt versions,
supplied excerpts and A/B/judge records. The UI shows severity, recovery,
transition evidence, action quotations and message jumps. Saved-run links and
reloads do not start inference. This implements four classes, **not** the
unavailable full pattern supplement, and has not been accuracy-calibrated.
See the [short evidence-gap report](docs/communication-evidence.md).
The [annotator-flow diagram and exact prompt reference](docs/communication-analysis-flow.html)
explain both Scout and communication pipelines. The saved October 19 results
remain v0.2/prompt 2; they have **not** been rerun with this v0.3 protocol.
The [SharedNet capture recommendations](docs/sharednet-capture-recommendations.md)
separate already-recorded evidence from proposed CLI instrumentation.

To opt in from batch:

```bash
.venv/bin/python -m agenttrace.batch traces.json \
  --output .agenttrace/communication-export --communication --model openai/gpt-5.4-mini
```

`--communication` is independent of `--scout`; `--model` applies to both when
both are selected. Compatible communication runs are reused only when model,
analyzer/prompt/taxonomy versions and evidence hash match. Use `--rerun` for
fresh judgments. `GET /api/communication/setup?trace_id=...` reports setup and
source coverage; explicitly start with
`POST /api/traces/{trace_id}/analyses/communication_failures_v1`.

### Scout's native viewer

Completed Scout runs have an **Open in Scout** link. It opens the exact saved
analysis in Scout's native UI in a new tab, with message annotations,
collaboration findings and navigable message references. It exports saved
judgments, **does not call a model**, and reuses the export on subsequent visits.
It also works without a provider API key.

Install the API's Scout extra, then run the official viewer in another terminal
using the **same data directory as AgentTrace**:

```bash
source .venv/bin/activate
DATA_DIR="${AGENTTRACE_DATA_DIR:-$PWD/.agenttrace}"
mkdir -p -m 700 "$DATA_DIR/scout-view" "$DATA_DIR/scout-view/transcripts" "$DATA_DIR/scout-view/scans"
scout view --transcripts "$DATA_DIR/scout-view/transcripts" \
  --scans "$DATA_DIR/scout-view/scans" --host 127.0.0.1 --port 7576
```

If the API loads `AGENTTRACE_DATA_DIR` from `.env`, that does not set the variable
in this terminal: set `DATA_DIR` explicitly to that directory instead.
For a different port, set the API server's `AGENTTRACE_SCOUT_VIEWER_URL` to the
matching loopback HTTP origin before restarting the API. The link reports an
explicit error if the viewer is stopped or serving the wrong directories.
Keep both servers on loopback; the native viewer also exposes editing/scanning
features and is not an authenticated shared hosting service.

Native files and a per-run export manifest persist in
`.agenttrace/scout-view/`. Include this directory in a private data-sharing
bundle, not in Git. The approved public dataset instead regenerates these
machine-specific files from its saved results. Native scans are labeled
saved-result replays and use `mockllm/model` as a no-provider recording model; the **original model,
prompt version and run ID** are retained in scan metadata. Original model-call
events, token accounting and generation logs cannot be reconstructed from
these saved judgments. Opening the viewer does not start inference; explicitly
running a new scan from its own controls is a separate action.

### Batch analysis and result links

Run all available offline annotators without clicking through the UI. Start
the API against the database you want to use, then run:

```bash
.venv/bin/python -m agenttrace.batch traces.json --output .agenttrace/batch-export
```

The input is an array, or an object containing a `traces` array. Each entry
contains a saved `trace_id`, a SharedNet `url`, or the API's structured `source`
object. An optional `name` or `slug` labels the export. Existing inventory
manifests with `trace_id` fields can be used directly:

```json
{
  "traces": [
    {"name": "saved-example", "trace_id": "trace_0123456789abcdef"},
    {"name": "uploaded-example", "source": {"type": "share_json", "value": {"room": {"name": "Example"}, "members": [], "messages": []}}}
  ]
}
```

The structured-source example shows the input shape; supply a real, nonempty
share to analyze it. Saved IDs must exist in the running server's database.
The output directory contains `index.json`, a clickable `links.html`, per-trace reports, and individual
analysis records. The index includes browser links for traces
(`?trace=...`) and specific analysis runs (`?trace=...&run=...`). Links require
the same server/database to be running; they are not public hosted links.
Specific-run links display the linked result rather than substituting a newer
run of the same analyzer. Exports can contain sensitive trace content and
share capabilities: keep them private and out of Git.
Only publish a reviewed dataset with explicit permission, as documented for
the approved snapshot in `data/teammate-traces`.

To explicitly include Scout's message annotations and collaboration scanners:

```bash
.venv/bin/python -m agenttrace.batch traces.json \
  --output .agenttrace/batch-export --scout --model openai/gpt-5.4-mini
```

Scout must be installed and its provider credentials configured on the
**running server**, not just in the batch command's shell. `--scout` authorizes
provider disclosure and potential API charges. Completed runs are reused by
default (Scout only when the model matches); add `--rerun` to repeat them.
Active runs are polled rather than duplicated. Unavailable annotators, setup
failures, analysis failures and timeouts are recorded explicitly. An incomplete
batch exits nonzero while preserving successful exports. A polling timeout
does not cancel the server job; repeating the command resumes waiting.

`--server` selects a localhost HTTP origin (default `http://127.0.0.1:3000`).
`--wait-timeout` limits waiting per analysis, and `--poll-interval` controls
polling. The installed `agenttrace-batch` console command is equivalent to
`python -m agenttrace.batch`.

| Variable | Purpose |
| --- | --- |
| `AGENTTRACE_DATA_DIR` | Override the SQLite and run-artifact directory |
| `AGENTTRACE_SOURCE_ROOT` | Allow local goal-run/export paths only within this directory |
| `AGENTTRACE_SCOUT_MODEL` | Default Scout `provider/model` identifier |
| `AGENTTRACE_COMMUNICATION_MODEL` | Default experimental communication-incident `provider/model` |
| `OPENAI_API_KEY` | Server-side key for the default OpenAI provider |
| `AGENTTRACE_WEB_DIST` | Explicit built frontend path, useful for an installed API wheel |
| `PORT` | Console server port; defaults to 3000 |

Local file ingestion is disabled unless `AGENTTRACE_SOURCE_ROOT` is set. Public
share ingestion validates the SharedNet URL and uses a bounded, fixed-host JSON
API request, not HTML scraping. Uploaded JSON and public responses are limited
to 5 MB.

For a model-free installation, replace `make install` with:

```bash
npm install
.venv/bin/python -m pip install -e ./packages/commsfail -e ./packages/agenttrace-api
```

## Tests

```bash
make test
make build
```

Optional real-browser tests exercise the running UI and API with mocked Scout
generation, without model charges:

```bash
.venv/bin/python -m pip install -e "./packages/agenttrace-api[browser]"
.venv/bin/python -m playwright install chromium
make test-browser
```

Root CI runs the Python suites, frontend tests, build, browser flow and
standalone package/plugin checks. See [DESIGN.md](DESIGN.md) for contracts,
[METRICS.md](METRICS.md) for formulas and migration differences, and
[MESSAGE_ANNOTATION.md](MESSAGE_ANNOTATION.md) for Scout semantics.

## Scope

This is a **single-process, localhost research application**, not a public
multi-user service. It has no authentication, shared-worker queue or cohort
dashboard. Run one API worker. SQLite preserves history, but does not make
in-process Scout tasks resumable.

`commsfail`'s existing model-backed standard pipeline remains available through
its own CLI; it is not silently treated as an offline annotator or exposed as a
Scout replacement in the UI. The optional [Scout bridge](scout/README.md)
remains available for standalone Scout transcript databases.
