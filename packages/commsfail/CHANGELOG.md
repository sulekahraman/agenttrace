# Changelog

## Unreleased

- Move the standard automated annotator to `commsfail/annotators/standard/`; update imports and packaged prompts, and list it in `commsfail annotators`. The `annotate` and `annotate-batch` commands and output schema are unchanged.

- Add resumable `annotate-batch` with two workers, E3 artifact validation, per-case logs and incremental summaries. Reject nonempty single-run output directories and fail when graded verdict retries are exhausted.

- `commsfail annotate` and `commsfail.annotators.standard`: failure incidents annotated by agents
  (`commsfail/annotation.v1`):
  - the unit is an incident of 1 to n posts, with an anchor, a `state_gap` class and pattern, a cause, a
    consequence, and a severity from 1 to 5 read from the work;
  - two Codex annotators work from a bundle with no grade; deterministic checks send failing replies back
    (at most three times), including a sweep that must cover every agent post;
  - a judge settles the record; with `--grade`, a verdict step attributes each lost rubric item;
  - agreement between the annotators: incident F1, class kappa, and weighted severity kappa.
  The agents run in `tools/agent-annotator` (Codex CLI 0.160.1), capped and with the bundle read-only.
  Checked end to end on eight research runs; see `commsfail/annotators/standard/README.md`.

## 0.4.0

Taxonomies become choices. There is one catalog of failure patterns, each defined once, and several ways to
group it. Annotators pick one.

- `commsfail/annotators/taxonomy-choices/`:
  - `patterns.json`: 43 patterns, each with a kind (missing, wrong, timing, excess), a definition, an example
    and its MAST counterparts. The paper's ten modes keep their ids and definitions.
  - `ten_modes`: the paper's three groups. The reference; it is partial on purpose.
  - `state_gap` (proposal A): classes by which two states of the run disagree.
  - `decision_point` (proposal B): classes by which decision an agent got wrong.
- A choice marked `complete` must place every pattern of the catalog, in a class or out of scope with a reason.
  The tests check this, so adding a pattern means saying where it goes in every complete taxonomy.
- An annotator sets `taxonomy = "<choice>"` and implements `modes_in(output)`. The contract checks that a
  built-in annotator names a choice, keeps no taxonomy of its own, and reports only patterns of its choice.
  `regroup()` reads pattern counts in any choice.
- `regex_v1` and `facts_v1` read in `ten_modes`. Output is byte-identical to 0.3.0.
- `example_kickstart`: a working annotator, read in `state_gap`, that shows signals → patterns → classes.
  It is the one to copy: `commsfail new` copies it and its test, and the copy passes at once. It replaces
  `_template/`.
- `commsfail taxonomy` lists the choices; `commsfail taxonomy <choice | annotator>` prints one, resolved.
- `commsfail audit`: any choice is a codebook, by pattern (`state_gap`) or by class (`state_gap:groups`), and so
  is any annotator's taxonomy. `modes_v1` is built from `ten_modes`, with the same labels and definitions.
- Breaking: `commsfail.annotators.taxonomy.MODES` is gone; use `load_choice("ten_modes")` or
  `taxonomy_of(<annotator>)`. `_template/` is gone.

## 0.3.0

- `commsfail audit`: human labels you can trust. `export` writes a blind file, one row per agent post, with no
  path, Room id, model, check or grade, tokens scrubbed, a digest on every fixed field, and a private key.
  `compare` gives Cohen's kappa per label and the rows to adjudicate. `finalize` writes gold labels with the
  source restored. Two built-in codebooks: `modes_v1` (the ten modes, per post) and `discourse_v1` (accept,
  result, review_pass); any other codebook is a JSON file. Ported from the comms-failure paper's
  `labels/annotation_audit.py`, without the harness-specific rescoring.
- CONTRIBUTING.md holds the whole guide and the repository's discipline: every change through a pull
  request, tests in the same pull request, extend the existing tests before writing new ones, versions and
  this changelog. The README keeps a pointer.

## 0.2.0

The repository is now organised for many annotators from many people.

- `commsfail/sources/sharednet.py` holds everything about SharedNet. New: the `goal run` record folder is the
  default input (episode, room, checks, wakes, and each seat's Codex or Claude Code log as ops); a bare
  `room.ndjson`; tools `agent_posts`, `posts_by`, `commands`, `cites`, `mentions`, `view_at`, `summary`.
- One folder per annotator: `__init__.py`, `schema.json`, `README.md`. A folder registers itself.
- Each annotator owns its output schema (JSON Schema 2020-12). Every output goes in one envelope,
  `commsfail/record.v1`. `commsfail validate` checks the envelope and the output.
- The contract tests run on every annotator, built in or plugin, and on every sample in `tests/fixtures/`:
  conformance, determinism, no change to the trace, no network, real post numbers, no tokens.
- `commsfail new <name>` starts an annotator from the template. `commsfail trace` shows what a source holds.
- `regex_v1` 0.2.0: skips the goal post and the runner's reports. Its output on shares is unchanged.
- The source entry-point group is `commsfail.sources` (was `commsfail.loaders`). `--source` replaces `--loader`.
- New dependency: `jsonschema`.
- `facts_v1`: said versus did. Seven facts, each a post checked against its author's own log. On the bench run
  `ep-001` it finds all five problems found by reading the logs by hand, and nothing else.
- The SharedNet reader follows the real message rows: `reply_to_message_id`, `sender.kind` (runner, human),
  `sender_principal_id`. Each `sharednet say` command is linked to the post it made (`posted`), and
  `ops_before(trace, seq)` gives what a seat had done before a post.

## 0.1.0

First release.

- `Trace`: one board in a normalized shape (room, seats, posts, artifacts, per-seat ops, source).
- Loaders for the SharedNet formats: share link or token, saved share JSON, `room export` NDJSON, episode directory.
- `analysis.v1`: the record format, with `validate()`.
- `regex_v1`: the reference annotator for the ten modes (R1 R2 REP, B1 B2, D1 D2 D3 D4 HB).
- `commsfail` CLI: `analyse`, `annotators`, `loaders`, `schema`, `validate`.
- Plugin discovery through the `commsfail.annotators` and `commsfail.loaders` entry-point groups, resolved lazily; a broken plugin is skipped with a warning.
- `examples/plugin`: a complete plugin with one annotator and one loader.
