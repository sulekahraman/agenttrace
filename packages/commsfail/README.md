# commsfail

Communication-failure analysis for multi-agent message boards.

When several agents work through one shared log, much of what goes wrong is visible in the log and in the agents' own records: a claim nobody read, an ask nobody answered, a review of work that was never delivered, a "tests pass" that the agent's own log contradicts. `commsfail` reads one board into a `Trace`, runs an **annotator** over it, and writes a **record**: the annotator's output, in the annotator's own schema, inside one common envelope.

The default input is a SharedNet trace. Anyone can contribute an annotator: a set of rules, a model as judge, a classifier, an importer of human labels. Each annotator decides what it reports and states it as a JSON Schema.

## Install

```bash
pip install git+https://github.com/xisen-w/commsfail
```

Python 3.10 or newer. One dependency: `jsonschema`.

## Use

```bash
commsfail trace runs/rom_abc                       # what the source holds: posts, seats, ops, checks
commsfail analyse runs/rom_abc --markdown          # the default annotator, regex_v1, as a short table
commsfail analyse runs/rom_abc -o record.json      # the full record
commsfail analyse runs/rom_abc --annotator my_v1   # another annotator
commsfail validate record.json                     # the output against its annotator's schema
commsfail annotators                               # every annotator, built in and plugins, with its schema id
commsfail schema regex_v1                          # an annotator's output schema
commsfail taxonomy regex_v1                        # an annotator's failure modes
```

```python
from commsfail import load, run, validate_record

trace = load("runs/rom_abc")
record = run("regex_v1", trace)
assert validate_record(record) == []
print(record["output"]["metrics"])
```

## Input: SharedNet traces

`commsfail.sources.sharednet` reads every SharedNet source into the same `Trace`. A source shows what it has. A field it cannot show stays empty.

| source | made by | what it shows |
|---|---|---|
| record folder | `sharednet goal run --out DIR` | posts, seats, checks, wakes, each seat's own harness log, the episode summary |
| goal-export folder | `sharednet goal watch`, `sharednet goal export` | posts, the episode summary, sometimes checks |
| `room.ndjson` file | one file of a record | posts and seats |
| share JSON or share link | a share page | posts and seats; no ids, no artifacts, no ops |

A record folder holds these files. `commsfail` reads all of them except the workspace history and the agents' homes.

| file | what it holds |
|---|---|
| `episode.json` | the goal, the end conditions, `ended_by`, each agent's turns and tokens, the totals |
| `room.ndjson` | every message in the Room, in order |
| `checks.ndjson` | every check: when, why, the exit code, the output |
| `wakes.ndjson` | every turn: which seat, woken by what, the messages it was handed, the tokens |
| `agents/<seat>/turn-NNN.jsonl` | each turn's raw stream from the harness (Codex and Claude Code are parsed into ops) |

The `Trace`:

```
room       {id, name, created_at, latest_sequence, state}
seats      [{handle, label, driver, model, joined_at, principal, member_id}]
posts      [{seq, id, who, text, created_at, reply_to, type, role}]  role: goal | agent | runner | other | None
artifacts  [{id, by, created_at, name, sha256}]
ops        {seat: [{turn, i, kind, command, exit_code, output, posted, paths, query, name, text}]}
           posted: the post a `sharednet say` command made, so each post is tied to its author's log
checks     [{at, trigger, command, cause, exit_code, passed, sequence, output}]
wakes      [{seat, turn, fired, from, through, messages, started_at, ended_at, exit_code, failed, tokens}]
episode    the run's own summary
source     {kind, path or redacted token, room_id, loaded_at}
```

Tools in `commsfail.sources.sharednet` for annotators:

| tool | what it gives |
|---|---|
| `ops_before(trace, seq)` | what the author of post `seq` had done before writing it, in order |
| `post_ops(trace)` | for each post, the seat, turn and command that made it |
| `view_at(trace, seq)` | the board as it was right after post `seq` |
| `agent_posts`, `posts_by`, `commands`, `is_board_command` | posts and commands, filtered |
| `cites`, `mentions` | the `#n` a text cites, the `@names` it addresses |
| `summary`, `redact`, `parse_ts` | a quick look at a source; safe excerpts; timestamps |

Another format is a **source plugin**: a function from a path to a `Trace`, announced by an entry point (see [examples/plugin](examples/plugin)).

## Output: a record

```json
{
  "record": "commsfail/record.v1",
  "annotator": {"name": "regex_v1", "version": "0.2.0", "schema": "comms-failure/analysis.v1"},
  "source": {"kind": "goal-run", "path": "runs/rom_abc", "room_id": "rom_abc", "loaded_at": "..."},
  "output": {"...": "whatever the annotator's schema describes"}
}
```

The envelope is the same for every annotator. The `output` is the annotator's own. `validate` checks both.

## Annotators

| annotator | output schema | taxonomy | what it reports |
|---|---|---|---|
| [`regex_v1`](commsfail/annotators/regex_v1) | `comms-failure/analysis.v1` | `ten_modes` | the ten failure modes, from text patterns; works on any source |
| [`facts_v1`](commsfail/annotators/facts_v1) | `commsfail/facts_v1/v1` | `ten_modes` | said versus did: each post checked against its author's own log; needs a goal-run record |
| [`example_kickstart`](commsfail/annotators/example_kickstart) | `commsfail/example_kickstart/v1` | `state_gap` | open questions and bare claims; **the annotator to copy** with `commsfail new` |
| yours | yours | a choice | see [CONTRIBUTING.md](CONTRIBUTING.md) |

### Taxonomies

People cut communication failures in different ways, so there is more than one taxonomy. There is still only one place where failures are defined. [taxonomy-choices](commsfail/annotators/taxonomy-choices) holds two things:
- **`patterns.json`**, a catalog in which every failure pattern is defined once, with a definition a person can label with and an example;
- **the choices**, the ways to group those patterns into classes.

| Choice | Classes | Complete |
|---|---|---|
| `ten_modes` | the paper's three groups: not read, not binding, never done | no: ten patterns, the reference |
| `state_gap` | by which two states of the run disagree: unsaid, unreceived, misread, disagreement, ungrounded, stalled | yes |
| `decision_point` | by which decision an agent got wrong: disclose, claim, specify, hand off, report and verify, progress and close | yes |

An annotator names its choice in one line, `taxonomy = "state_gap"`, and reports pattern ids. Every choice groups the same patterns, so findings and human labels read under any choice. A complete choice must place every pattern of the catalog, in a class or explicitly out of scope, and the tests check this. When a new pattern is added, every complete taxonomy has to say where it goes.

The ten patterns of `ten_modes`, which regex_v1 reports:

| id | mode | what happened to the message |
|---|---|---|
| R1 | Open-set decay | not read: a seat re-claims or re-does an item an earlier post settled |
| R2 | Replacement re-does work | not read: a late joiner redoes what the log already holds |
| REP | Step repetition | not read: the same post, again |
| B1 | Belief without commitment | not binding: a hedged claim, or an ask nobody answered |
| B2 | Identity drift | not binding: who speaks, or who leads, changes under one handle |
| D1 | Unattested action | never done: "pushed", "uploaded", "tests pass" with no proof in the record |
| D2 | Review of nothing | never done: a review passed on an item never delivered |
| D3 | Closure before budget | never done: the board ends in a pause, an open ask or a heartbeat, with items open |
| D4 | Capability not routed | never done: a request for an action only another seat can take, left there |
| HB | Heartbeat cost | never done: status posts with no new information |

## Human labels: `commsfail audit`

To check an annotator, or to build training data, you need labels that people agree on. `commsfail audit` makes them in three steps:
1. **Export** a blind file, one row per agent post, with no path, Room id, model or grade.
2. **Compare** the labels that two people put on the rows, with Cohen's kappa per label.
3. **Finalize** a gold file once every disagreement has been adjudicated.

```bash
commsfail audit export runs/ep-* --salt "$STUDY_SALT" --out blind.jsonl --key key.jsonl
commsfail audit compare a.jsonl b.jsonl --report report.json --adjudicate todo.jsonl
commsfail audit finalize a.jsonl b.jsonl --adjudicated todo.jsonl --key key.jsonl --out gold.jsonl
```

A codebook can be:
- `modes_v1`: regex_v1's ten modes, as yes-or-no labels per post.
- `discourse_v1`: accept, result and review_pass.
- a taxonomy choice, such as `state_gap`, labelled by pattern, or `state_gap:groups`, labelled by class;
- an annotator's name, which gives the taxonomy it reports in;
- a JSON file holding a codebook. The procedure and the rules for annotators are in [commsfail/audit](commsfail/audit).

## Failure incidents by agents: `commsfail annotate`

`commsfail annotate` annotates the failure incidents of one goal-run record with agents.
1. Two Codex agents annotate it independently, each from a bundle that holds no grade.
2. Deterministic checks send any reply that fails back to its agent, with the reasons.
3. A judge agent settles the final record.
4. With `--grade`, a last agent then says what cost each rubric item.

The unit is an incident: one to n posts, with an anchor, a `state_gap` class and pattern, a cause, a consequence and a severity from 1 to 5.

```bash
docker build -t commsfail-agent-annotator:0.1 tools/agent-annotator
commsfail annotate runs/goal-run --out out/goal-run --grade runs/goal-run/score.json --effort high
```

For fully automated research analysis, use `commsfail annotate-batch RECORDS --out FRESH_BATCH --workers 2 --effort high`. It selects n=2/3/4 by default, validates every result, and resumes failed cases while preserving their previous attempts. See the [batch runbook](commsfail/annotators/standard/README.md#fully-automated-research-batch).

The record format, the steps, the checks, and how far it can be trusted are in [commsfail/annotation](commsfail/annotators/standard).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before you open a pull request. It covers:
- the discipline every change follows: a pull request, tests in the same pull request, extending the existing tests, versions and the changelog;
- the ten rules every annotator obeys;
- the steps to add an annotator, a sample or a codebook;
- the data rules.

## Repository layout

```
commsfail/
  trace.py                 the Trace
  sources/
    sharednet.py           everything about SharedNet: the readers and the tools
  annotators/
    base.py                the contract: schema loading, validation, the record envelope
    taxonomy.py            load and check the catalog and the choices; regroup counts; analysis.v1 helpers
    taxonomy-choices/      patterns.json (every pattern, once) and the choices: ten_modes, state_gap, decision_point
    regex_v1/              one annotator: __init__.py, schema.json, README.md
    facts_v1/              said versus did, from each seat's own log
    standard/              standard automated failure analysis: bundle, A/B, judge, verdict, batch
    example_kickstart/     a working sample, read in state_gap: what `commsfail new` copies
  audit/                   human labels: blind export, kappa, adjudication, gold; the built-in codebooks
  cli.py
tests/
  fixtures/goal_run/       a synthetic goal-run record folder
  fixtures/share.json      a synthetic share
  test_contract.py         the rules, on every annotator and every sample
  test_audit.py            the audit steps, the export on every sample
  test_annotation.py       the bundle, the checks, agreement, and the pipeline with a fake agent
  test_taxonomy.py         the catalog, the choices, and the completeness check
  annotators/              one behaviour test file per annotator
examples/plugin/           an annotator and a source in a separate package
tools/agent-annotator/     the image the annotation agents run in
```

## License

MIT.
