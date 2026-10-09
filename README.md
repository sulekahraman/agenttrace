# AgentTrace

AgentTrace combines the existing React trace explorer, reusable `commsfail`
analysis, and Inspect Scout in one monorepo. Structural metrics and offline
annotators work without a model; Scout runs only when explicitly requested.

| Path | Responsibility |
| --- | --- |
| `apps/web` | React, Observable Plot, linked filters, findings and evidence |
| `packages/commsfail` | Independently installable trace loaders, schemas, offline plugins and CLI |
| `packages/agenttrace-api` | FastAPI, persistent analysis runs, structural heuristics and Scout orchestration |
| `fixtures` | Shared sample trace and frozen pre-migration metric baseline |

The imported `commsfail` history and MIT license are preserved. AgentTrace's
offline heuristic plugin is registered through `commsfail.annotators`, rather
than adding application-specific dependencies to `commsfail`.

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
explicit failures. Traces and run history persist in
`.agenttrace/agenttrace.sqlite3`; prompt/result artifacts live under
`.agenttrace/runs/<run-id>/`. Interrupted jobs are marked failed on restart,
not retried automatically. Re-ingesting unchanged content reuses its trace;
changed content receives a new identifier.

| Variable | Purpose |
| --- | --- |
| `AGENTTRACE_DATA_DIR` | Override the SQLite and run-artifact directory |
| `AGENTTRACE_SOURCE_ROOT` | Allow local goal-run/export paths only within this directory |
| `AGENTTRACE_SCOUT_MODEL` | Default Scout `provider/model` identifier |
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
