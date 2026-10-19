# SharedNet CLI: recommended analysis capture

Reviewed `systemind-team/sharednet-client` branch `codex/bootstrap-base` at
`16d4a44d66f31e7a88720fe76c00f52a9d235e28`, after implementing and verifying
AgentTrace's experimental incident setup. These are proposals, not implemented
SharedNet flags or commands.

## Preserve existing evidence first

`goal run` already records `workspace.git`, raw turn streams and agents' session
files. These richer files were absent from the inspected PR export. Server-only
`goal export` exports room/goal data, not a reconstruction of local execution.
Add an opt-in **analysis export profile accepting the original run directory**.
Preserve workspace history, selected sanitized session records and full outputs;
do not distribute entire agent homes or assume credential-file removal makes
all transcript content safe.

## Add the missing associations

| Priority | Proposed change | What it enables |
| --- | --- | --- |
| P1 | Extend existing `routing.ndjson` delivery-ID records to every routing mode and the initial goal turn. Link run, seat, session, turn, wake, exact delivered IDs, sanitized content hashes and prompt reference. Record handoff/launch/completion separately, plus available context-compaction boundaries. | Separates publication from runner handoff and avoids treating a sequence range as an exact delivered set. Does not prove model understanding or complete resumed context. |
| P1 | Keep native harness streams unchanged; add timestamped event metadata with composite action IDs, UTC and monotonic collector times, native timestamps when available, input references and exit states. Distinguish observed time from actual execution time. | Establishes defensible ordering without dating an action by its later report. |
| P2 | Preserve existing workspace snapshots; add action-linked file-change evidence and final artifact manifests. Record overlapping writers/uncertain attribution rather than guessing from aggregate diffs. | Supports Action consequences, overwrites and verified recovery. |

Require a versioned completeness/redaction manifest: each evidence component
must be marked present, not captured, redacted, failed or unsupported, with
coverage bounds, hashes and runner provenance. Surface snapshot/session-copy
failures instead of leaving unexplained missing files.

Capture must not introduce acknowledgements, mention gates or new checks into
an experiment. Keep optional evaluation results separate from incident detection.
Test first-turn delivery, filtered/broadcast wakes, bounded reads, Unicode,
interrupted turns, concurrent writes and capture failures.

AgentTrace will need follow-on importers for new sidecars; the current setup
does not pretend to consume telemetry that does not yet exist.

Sources at the pinned revision: `docs/goal-mode.md`; `packages/cli/src/goal-run.ts`
(`runTurn`, `seatLoop`, `opening_prompt_sha256`, `scrubHome`);
`packages/cli/src/goal.ts` (`workspaceSnapshots`, `takeSnapshot`, `goalExport`).
