# yj multi-agent traces (2026-10-15)

Three runs of the ProgramBench task `sclevine__yj.8016400`, a command-line tool for converting between YAML, TOML, JSON, and HCL: one run each with two, three, and four agents.
This sample contains selected files copied byte-for-byte from the local experiment archive. The experiments were not rerun, and no messages or records were rewritten or synthesized.
`manifest.json` records each copied file's original relative path, destination relative path, size in bytes, and SHA-256 hash.

## Experiment setup

According to the original experiment notes and episode records:

- All agents used Codex CLI with `gpt-5.6-luna`.
- Runs used `sharednet goal run` with `broadcast` message routing and DONE consensus enabled.
- Each agent ran in its own container with a shared workspace. Network access was limited to SharedNet and the model API.
- Runs stopped on DONE consensus for the current workspace, a 30-minute limit, or a three-million-token limit. All three runs ended with the `said DONE` trigger; the original notes report consensus completion.
- Idle reminders were enabled with a two-minute interval. An agent's DONE acknowledgment becomes invalid when that agent posts again or the workspace changes, so a run can contain multiple DONE messages.
- The task included instructions to use the protected reference executable at `/reference/executable` and test against it before saying DONE. Full instructions are preserved in each run's `TASK.md`.
- The original experiments were evaluated against ProgramBench hidden tests. This copy contains traces only, without evaluation scores or failure-analysis results.

## Runs

`n2`, `n3`, and `n4` denote the agent count. `round1` denotes the first run for that agent count; it is an experiment repetition number, not a conversation turn. This sample contains one run per configuration.

| Run | Agents | Room posts | Turn log files |
|---|---:|---:|---:|
| [n2-round1](n2-round1/record-run/) | 2 | 33 | 5 |
| [n3-round1](n3-round1/record-run/) | 3 | 66 | 17 |
| [n4-round1](n4-round1/record-run/) | 4 | 77 | 25 |

## Directory layout

```text
yj-2026-10-15/
├── README.md
├── manifest.json
└── n2-round1/                 # The other two runs use the same layout
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
commsfail trace sample/yj-2026-10-15/n2-round1/record-run
commsfail analyse sample/yj-2026-10-15/n2-round1/record-run --annotator facts_v1 -o /tmp/yj-facts.json
commsfail validate /tmp/yj-facts.json
pytest tests/test_contract.py tests/test_audit.py -k yj
```

## Verification and known limitations

All 62 copied files were checked for byte equality and SHA-256 integrity. All newline-delimited JSON records parse when split on the JSONL newline delimiter (`\n`).
The existing SharedNet reader loaded all three runs: 176 room posts and 47 turn log files, with consistent agent identities and wake/turn pairs.
Of 171 agent posts, 169 were linked to their posting operations. Both `regex_v1` and `facts_v1` ran successfully on each copied record, and all six outputs passed schema validation.
The existing contract and audit tests selected with `-k yj` passed: 57 tests passed, with 299 unrelated tests deselected. The full test suite was not run.

Two DONE posts are present in the raw command outputs but are not linked by the current reader:

- `n3-round1`: post #58, from `agents/codex-1/turn-004.jsonl`.
- `n4-round1`: post #72, from `agents/codex-1/turn-004.jsonl`.

Each affected shell command calls `sharednet say` twice, but the current parser extracts only the first returned message ID. Analyses that depend on posting-operation links may skip the second post.

There is also a Unicode line-splitting limitation in `n4-round1/record-run/agents/codex-4/turn-001.jsonl`:
newline-delimited records 25 and 26 contain a literal U+2028 character inside the command string for `item_11` (the started and completed events).
These are valid JSON records, but the reader uses Python's `str.splitlines()`, which also splits on U+2028. It then skips the resulting fragments as invalid JSON, omitting one completed command from the parsed operations.
The copied trace preserves these bytes; a successful load does not imply that every event was retained.

## Included files

Included: room messages, episode metadata, wake records, check records, per-turn Codex JSONL event streams, and task instructions.
Excluded: agent home directories (configuration, SQLite databases, full sessions, and other state), stderr logs, gateway logs, `workspace.git`, evaluation files, and `.DS_Store` files.
This copy therefore lacks full model-input sessions and workspace snapshots. Consult the original experiment archive when that evidence is needed.
