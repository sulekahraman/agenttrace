# xsv multi-agent traces (2026-10-15)

Nine runs of the ProgramBench task `burntsushi__xsv.f430466`: three runs each with two, three, and four agents.
This sample contains selected files copied byte-for-byte from the local experiment archive. The experiments were not rerun, and no messages or records were rewritten or synthesized.
`manifest.json` records each copied file's original relative path, destination relative path, size in bytes, and SHA-256 hash.

## Experiment setup

According to the original experiment notes and episode records:

- All agents used Codex CLI with `gpt-5.6-luna`.
- Runs used `sharednet goal run` with `broadcast` message routing, rather than serve communication mode.
- Each agent ran in its own container with a shared workspace. Network access was limited to SharedNet and the model API.
- Runs stopped on DONE consensus for the current workspace, a 30-minute limit, or a three-million-token limit. The original notes report that all nine runs ended by consensus.
- Idle reminders were enabled with a two-minute interval. An agent's DONE acknowledgment becomes invalid when that agent posts again or the workspace changes, so a run can contain multiple DONE messages.
- The original experiments were evaluated against ProgramBench hidden tests. This copy contains traces only, without evaluation scores or failure-analysis results.

## Runs

`round1`, `round2`, and `round3` denote the first, second, and third repeated runs for a given agent count, respectively. They are separate experiment runs, not conversation turns within a run.

| Run | Agents | Room posts | Turn log files |
|---|---:|---:|---:|
| [n2-round1](n2-round1/record-run/) | 2 | 23 | 6 |
| [n2-round2](n2-round2/record-run/) | 2 | 28 | 6 |
| [n2-round3](n2-round3/record-run/) | 2 | 30 | 6 |
| [n3-round1](n3-round1/record-run/) | 3 | 59 | 21 |
| [n3-round2](n3-round2/record-run/) | 3 | 43 | 16 |
| [n3-round3](n3-round3/record-run/) | 3 | 56 | 12 |
| [n4-round1](n4-round1/record-run/) | 4 | 61 | 16 |
| [n4-round2](n4-round2/record-run/) | 4 | 66 | 29 |
| [n4-round3](n4-round3/record-run/) | 4 | 76 | 36 |

## Directory layout

```text
xsv-2026-10-15/
├── README.md
├── manifest.json
└── n2-round1/                 # The other eight runs use the same layout
    ├── TASK.md               # Original task instructions
    └── record-run/           # Pass this directory to commsfail
        ├── episode.json
        ├── room.ndjson
        ├── wakes.ndjson
        ├── checks.ndjson
        └── agents/
            ├── codex-1/turn-*.jsonl
            └── codex-2/turn-*.jsonl
```

The paths match the test suite's `sample/*/*/record-*` discovery pattern.
Empty `checks.ndjson` files are expected: no runner check command was configured for these experiments.
Tests run by the agents themselves remain in their respective `turn-*.jsonl` files.

## Read and validate

From the repository root:

```bash
python3 -m pip install -e ".[dev]"
commsfail trace sample/xsv-2026-10-15/n2-round1/record-run
commsfail analyse sample/xsv-2026-10-15/n2-round1/record-run --annotator facts_v1 -o /tmp/xsv-facts.json
commsfail validate /tmp/xsv-facts.json
pytest
```

## Verification and known limitations

Every copied file was checked for byte equality and SHA-256 integrity. All nine runs were loaded with the existing SharedNet reader:
442 room posts and 148 turn log files, with consistent agent identities and wake/turn pairs.
Of 431 agent posts, 428 were linked to their posting operations.

Three posts are present in the raw command output but are not linked by the current reader:

- `n2-round3`: post #30.
- `n3-round3`: post #54.
- `n4-round1`: post #57.

Each affected shell command calls `sharednet say` twice, but the current parser extracts only the first returned message ID.
All three unlinked posts are the second message, DONE. The raw logs are unchanged; analyses that depend on posting-operation links may skip these posts.

Loading and message linking were checked for all nine runs. The `trace`, `analyse --annotator facts_v1`, and `validate` commands also passed for `n2-round1`.
The full pytest suite and output schema validation for the other eight runs have not been run.

## Included files

Included: room messages, episode metadata, wake records, check records, per-turn Codex JSONL event streams, and task instructions.
Excluded: agent home directories (configuration, SQLite databases, full sessions, and other state), stderr logs, gateway logs, `workspace.git`, evaluation files, and `.DS_Store` files.
This copy therefore lacks full model-input sessions and workspace snapshots. Consult the original experiment archive when that evidence is needed.

