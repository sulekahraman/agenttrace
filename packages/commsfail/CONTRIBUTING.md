# Contributing

Most contributions are one of three kinds:
- **An annotator.** This is the most common kind: a new method, in its own folder.
- **A sample.** A new board in `tests/fixtures/`, which every annotator then runs on.
- **Shared code.** Sources, the contract, the taxonomy catalog and choices, `audit`, the CLI.

All three follow the same discipline. Read it once before your first pull request.

## The discipline

These hold for every change, by anyone, including maintainers.

1. **Every change goes through a pull request.** Nobody pushes to `main`. One topic per pull request. Name the branch after what it changes: `annotator/<name>`, `sample/<name>`, `fix/<topic>`, `feat/<topic>`, `docs/<topic>`.
2. **New behaviour comes with its tests, in the same pull request.** A pull request that adds behaviour without a test is sent back before review.
3. **A bug fix starts with a failing test.** First write the test that shows the bug, then the fix that makes it pass.
4. **Extend the tests that exist before you write new ones.** The suite is built to grow by adding rows, not files:
   - `tests/test_contract.py` runs every annotator on every sample. A new annotator or a new sample is checked by it with no new test code. Do not copy contract checks into your own test file.
   - A rule that must hold for every annotator, or every sample, belongs in the contract as one parametrized test. It does not belong in a single annotator's file.
   - A behaviour test names posts and says why. Follow `tests/annotators/test_facts_v1.py`: an expected list of `(seq, finding)` pairs, with a comment on each row.
   - Use the shared fixtures in `tests/conftest.py`: `sample`, `any_trace`, `goal_run`, `synthetic_trace` and `no_network`. When you need one exact case, build a small `Trace` inside the test, as `_trace()` in `test_facts_v1.py` does, instead of adding a sample.
   - When annotators need a new kind of board, add a sample (see [Adding a sample](#adding-a-sample)). Every annotator then runs on it.
5. **Tests are fast, offline and deterministic.** They make no network calls, read no clock, call no model, and use no randomness without a fixed seed. The whole suite runs in under a second today. Keep it in seconds.
6. **CI is green on Python 3.10 to 3.13 before merge.** Run `pytest` locally first.
7. **Versions say what changed.**
   - Change an annotator's `version` whenever its output for the same trace changes. Change its schema's `$id` when the output format changes.
   - Every pull request that changes behaviour adds a line under `## Unreleased` in [CHANGELOG.md](CHANGELOG.md).
8. **Shared code changes start with an issue.** The shared code is `trace.py`, `sources/`, `annotators/base.py`, `annotators/taxonomy.py`, `annotators/taxonomy-choices/`, `audit/`, `cli.py` and the record envelope.
   - A change to the envelope is a new `record` version.
   - A change to the audit rows is a new `audit-*` schema version.
9. **The core stays small.** It has one runtime dependency, `jsonschema`. A new runtime dependency needs a reason in the pull request. Heavy ones, such as a model SDK or numpy, go in an optional extra or in a plugin.
10. **Write like the code around you.** Use the same naming and the same density of comments. Docstrings say what a thing does and what it returns.
11. **The pull request says what you checked.** State what changed, why, and how you checked it: the commands you ran and the traces you read by hand.
12. **Review.** Every pull request needs one approving review from someone other than its author.
    - A change to shared code needs a maintainer's review.
    - A pull request that touches only its own annotator folder and its own test may be merged by its author once CI is green and it has been approved.

## Contributing an annotator

`commsfail/annotators/standard/` is the live automated pipeline, invoked with `annotate` or `annotate-batch`. Its `PIPELINE = True` marker keeps it out of offline discovery. The class/schema contract below applies to the offline `ANNOTATOR` methods used by `analyse`.

Different people bring different methods. All of them live side by side here, and the same tests check all of them. You do not need anyone's permission to design a new kind of annotator. You do need to follow the rules below.

### The rules

Every annotator, built in or plugin, must obey these rules. `tests/test_contract.py` checks each one, on every annotator and every sample in `tests/fixtures/`.

1. **One folder, three files.** `commsfail/annotators/<name>/` holds:
   - `__init__.py`: the code, which sets `ANNOTATOR = <the class>`.
   - `schema.json`: the output schema.
   - `README.md`: what the annotator reports, how, and what it is good and bad at.

   The folder name is the annotator's `name`.
2. **Name and version.** `name` is lowercase letters, digits and `_`, for example `judge_gpt_v1`. Change `version` whenever the output for the same trace changes.
3. **Your output, your schema.** `schema.json` is a JSON Schema (draft 2020-12) with `$schema`, `$id`, `title` and `description`.
   - The `$id` names your output format, for example `commsfail/judge_gpt_v1/v1`. Change the `$id` when the format changes.
   - Every output must validate against the schema.
4. **Same trace, same output.** `annotate()` is deterministic and does not change the trace. A model judge fixes its model, temperature and seed, or caches its answers, so that a record can be made again.
5. **No network in `annotate()`.** Loading is the source's job.
   - A model judge gets its answers in a separate step and saves them, for example as one JSON file per trace in its own folder. `annotate()` then reads the saved answers.
   - Save the answers for the samples too, so that the tests can run. The tests cut the network.
6. **Point at real posts.** Any object in your output with an integer `seq` must name a post that exists, or `0` for the whole Room.
7. **No secrets.** Pass every excerpt of post text through `redact()`. No token may appear in the output.
8. **Blind to the outcome.** An annotator never reads the task's grade or the experimental condition. It judges the conversation, not the result.
9. **Say what you are not sure of.** When the source cannot show what you report, say so in the output instead of guessing, for example `"severity": "unknown"`.
10. **Pick a taxonomy; do not write one.** If the annotator reports failures, set `taxonomy` to a choice in `commsfail/annotators/taxonomy-choices/`, and report pattern ids from `patterns.json`.
    - Implement `modes_in(output)`, which returns the pattern ids an output reports. The contract checks that they are all in your taxonomy.
    - If your method finds a failure that no pattern describes, add the pattern to `patterns.json`, and place it in every complete choice, in a class or out of scope with a reason. Do this in a pull request of its own, because it changes every complete taxonomy.
    - Never copy a pattern's definition into your annotator. Read it from the catalog.

### Steps

```bash
git clone https://github.com/xisen-w/commsfail && cd commsfail
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]" -e examples/plugin
pytest                                     # all green before you start

git checkout -b annotator/<name>
commsfail new <name>                       # copies example_kickstart to the folder, and its test to tests/annotators/test_<name>.py
pytest                                     # the copy passes as it is
```

Then:

1. Pick a taxonomy choice, and write your method in `__init__.py`: which signals it finds, and which catalog pattern each is evidence for. Get the tools from `commsfail.sources.sharednet`. If your output is analysis.v1, use the helpers in `commsfail.annotators.taxonomy`.
2. Describe your output in `schema.json`. Make it strict: use `required` and `additionalProperties: false` where you can. A loose schema checks nothing.
3. Fill in `README.md`: what it reports, how, what it is good at, what it is weak at, and which traces you read by hand to check it.
4. Write behaviour tests in `tests/annotators/test_<name>.py`: which posts it points at on the samples, and why.
5. Run `pytest`, then `commsfail analyse tests/fixtures/goal_run --annotator <name>`, and read the output yourself.
6. Add a line to `CHANGELOG.md`, then open a pull request.

### Or keep it in your own repository

If your method lives next to other code, for example a training codebase, make it a plugin. Copy [examples/plugin](examples/plugin), set the entry point, and ship `schema.json` as package data:

```toml
[project.entry-points."commsfail.annotators"]
my_v1 = "my_package.annotators:MyV1"
```

When your package and `commsfail` are installed together, `commsfail annotators` lists your annotator, and `pytest` in this repository runs the contract on it.

### What a reviewer checks

- The contract tests pass on all samples, on Python 3.10 to 3.13.
- The folder has its three files, and the README is honest about the weak cases.
- Each signal is mapped to the catalog pattern it is really evidence for. A new pattern has a definition a person could label with, and is placed in every complete choice.
- The schema is strict. Its `$id` is either new, or an existing `$id` whose meaning has not changed.
- The behaviour tests name posts and reasons, not only "it runs".
- No real Room content, no token and no share link appears in the code, the tests or the pull request text.
- The pull request changes only its own folder and its own test, or it says why it changes more.

## Adding a sample

The samples in `tests/fixtures/` are the shared ground for every annotator. To add one, put a record folder (or a share `.json`, or an `.ndjson`) there, and describe it in [tests/fixtures/README.md](tests/fixtures/README.md). Use synthetic content, or content from a Room whose people agreed. The contract tests and the audit export tests then run on it.

## Contributing a codebook

A codebook is the list of yes-or-no labels that people put on posts in `commsfail audit` (see [commsfail/audit](commsfail/audit)).

- Start a new codebook as a JSON file in your study, and pass it with `--codebook path.json`.
- Propose it as a built-in codebook only once a study has used it and reported its kappa.
- Changing a built-in label's definition makes a new codebook version, because rows labelled under the old wording no longer compare with the new.

## Data rules

- No real Room content in tests, examples or issues unless the people in the Room agreed.
- Never commit a token, a key or a share link. A share link is a capability: whoever holds it can read the Room. Cite a Room by its name.
- Experiment records, blind files, keys and gold files stay where the experiment keeps its data. This repository holds code and synthetic samples only.

## Releasing

A maintainer does the release:
1. Moves the `## Unreleased` lines under a new version heading in `CHANGELOG.md`.
2. Sets the same version in `pyproject.toml` and `commsfail/__init__.py`.
3. Merges, then tags `vX.Y.Z` on `main`.

Users pin a tag: `pip install git+https://github.com/xisen-w/commsfail@vX.Y.Z`.
