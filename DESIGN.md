# AgentTrace Architecture

## One repository, separate responsibilities

```text
SharedNet JSON / allowlisted local goal-run or export
                        |
                commsfail.Trace
                        |
       +----------------+-------------------+
       |                |                   |
UI view model     offline plugins     Scout pipeline
structural metrics   commsfail.run    bounded annotation
       |                |            candidate findings
       +----------------+-------------------+
                        |
            SQLite traces + analysis runs
                        |
             FastAPI / React explorer
```

`commsfail` remains independently installable and network-free for offline
analysis. Scout, HTTP serving, persistence and application heuristics belong
to `agenttrace-api`. The application consumes canonical traces, not parsed
HTML or another JavaScript analysis implementation.

## Contracts

Canonical trace JSON uses `commsfail/trace.v1`. The compatible UI projection
uses `schemaVersion: "2.0"` and includes `traceId`, messages, participants,
metrics, transitions, structural flags and namespaced `analyses`.

Offline plugins preserve the standard `commsfail/record.v1` contract and are
validated before storing successful runs. They are discovered through the
`commsfail.annotators` entry-point group.

Every run uses `agenttrace/analysis-run.v1`:

```json
{
  "schema": "agenttrace/analysis-run.v1",
  "id": "run_...",
  "trace_id": "trace_...",
  "analyzer": {"name": "scout_collaboration_v1", "version": "2.0.0", "kind": "pipeline"},
  "status": "completed",
  "provenance": {"model": "provider/model", "prompt_version": "2"},
  "output": {},
  "error": null
}
```

The actual schema also records creation/start/completion times and package
versions. Checked-in JSON schemas are shipped in the API wheel. The run schema
is generated from Pydantic and tested for drift. Offline `output` contains the
complete `commsfail` record; Scout `output` contains findings, annotations and
coverage. Model results never replace deterministic metrics.

## API

| Endpoint | Behavior |
| --- | --- |
| `GET /api/analyzers` | Offline plugins and Scout availability; `?trace_id=...` checks source requirements |
| `GET /api/scout/setup` | Package/key-presence check and setup instructions for `?model=provider/model`; never returns credentials |
| `POST /api/traces` | Ingest `{"source":{"type":"share_json","value":{...}}}`; also accepts `sharednet_share` and `local` |
| `GET /api/traces/{id}` | UI projection and latest run per analyzer |
| `GET /api/traces/{id}/raw` | Canonical trace |
| `GET /api/traces/{id}/analyses` | Complete persisted run history |
| `POST /api/traces/{id}/analyses/{name}` | Explicit offline run or queued Scout run with `{"model":"provider/model"}` |
| `GET /api/analysis-runs/{id}` | Poll one run |

`POST /api/analyze` remains a compatibility alias. Unknown API routes return
JSON errors rather than frontend HTML. `create_app` is an application factory;
there is no module-global database or worker.

## Persistence and execution

Trace identity is a hash of the canonical content, excluding ingestion
timestamps. Analysis records reference an immutable trace version. SQLite
connections are short-lived and all run states are explicit:
`queued`, `running`, `completed` or `failed`.

Scout jobs run asynchronously behind a single-process semaphore. Duplicate
active requests for the same trace reuse the active run to reduce accidental
charges. Startup marks interrupted runs failed; shutdown cancels and records
active jobs. There are no automatic paid retries or process-external workers.

## UI and validation

React owns linked search, agent, transition and turn filters. Observable Plot
renders deterministic aggregates; filters select evidence rather than
recomputing research metrics. Evidence jumps and Scout polling preserve
original sequence numbers, including gaps caused by excluded goal/runner posts.
The URL's `trace` query parameter reloads persisted reports.

Tests cover the frozen original metric baseline, heuristic thresholds, source
boundaries, persistence/restart, schemas, plugin discovery, mocked Scout's real
structured-result parser, frontend API/export contracts and a live browser flow.
Real provider judgments still require human-labeled research validation.
