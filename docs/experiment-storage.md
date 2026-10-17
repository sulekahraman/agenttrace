# Where experiments and analyses belong

## The three repositories

| Repository | Primary role |
| --- | --- |
| [multi-agent-training](https://github.com/xisen-w/multi-agent-training) | Research coordination: proposal, experiment protocols, conditions, evaluation plans, and the experiment/analysis catalog. Access requires the team's repository permissions. |
| [commsfail](https://github.com/xisen-w/commsfail) | Reusable Python analysis engine: canonical traces, source readers, offline annotators, schemas/taxonomies, human-label audits, and automated annotation tooling. |
| [agenttrace](https://github.com/sulekahraman/agenttrace) | Application and results: web UI/API, SQLite history, batch exports, Inspect Scout analysis and saved native-viewer replay, public approved cohort snapshots, and presentation reports. |

AgentTrace currently includes an imported copy of commsfail under
`packages/commsfail`; it does **not** automatically receive changes from
`xisen-w/commsfail`. Record the actual analysis revision, not just the upstream
repository name.

## Is a pull request the right way to share runs?

**A PR is a good review workflow, not a separate archival storage system.**
For this small public cohort, PR #10 is useful: the inputs are reviewable,
byte-preserving, and accompanied by SHA-256 manifests. AgentTrace pins its
unmerged head `913ad1805642a38e5248d67e5d8c3b83c48b51b5`; it does not assume
these files are already in upstream `main`.

There is a policy mismatch to resolve upstream: PR #10's `sample/README.md`
describes real research samples, while `CONTRIBUTING.md` still says experiment
records stay with the experiment and this repository contains code and
synthetic samples. Agree on an explicit exception for small, consented examples
before using the analysis library as the default home for every run.

Recommendation:

1. **Catalog in the research repository.** Review protocols, small run manifests,
   evaluator versions, result summaries, and analysis links through PRs.
2. **One immutable raw artifact per run.** Initially, a modest collection of
   consented text records can be versioned in Git. As it grows, put compressed
   run bundles in a designated dataset release or team-controlled object store,
   and commit only their immutable identifiers and SHA-256 hashes. Do not keep
   copying the complete archive into all three repositories.
3. **Derived results separately.** Save analyzer outputs, model annotations,
   prompts, failed-attempt history, provenance, and reports under a versioned
   analysis ID. A published frozen SQLite export is convenient for viewing;
   a mutable local database is not the sole canonical record.

The checked-in ProgramBench cohort is an explicitly identified, checksummed
publication mirror of PR #10, not a second set of experiments. Repetitions are
separate runs; loading or reanalyzing one does not create another experiment.

GitHub documents [large-file considerations](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
and [releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases).
Use releases or an artifact store for growing bulk datasets rather than
ever-larger Git diffs. Do not use temporary CI artifacts as the only archive.
No new storage service or hosting is created by this recommendation.

## What each run should preserve

Keep immutable `run_id`, task/revision, repetition and seed (or explicit
`null` if not recorded), agent count/roles, resolved models, harness/runner
revision, routing/stop rules, budgets, container image digest, and timestamps.
Preserve the goal instructions, room posts, agent turn logs, checks/wakes, and
an approved workspace snapshot or patch history. Do **not** include agent home
directories, credentials, authentication databases, or capability links.

Include evaluator revision, final submitted artifact hash, grade/rubric
results, and evaluation provenance when shareable. Keep protected hidden tests
protected. Distinguish `passed`, `failed`, and `unavailable`; DONE consensus is
not an evaluation grade.

A small catalog entry could look like this (placeholders, not this cohort's
actual metadata):

```json
{
  "schema": "experiment-run/v1",
  "run_id": "study-task-n3-rep02",
  "task": {"id": "task-id", "revision": "<task-commit>"},
  "condition": {"agents": 3, "model": "<resolved-model>", "seed": null},
  "code": {"runner": "<commit>", "container_digest": "<sha256:digest>"},
  "termination": {"trigger": "consensus", "budget_tokens": 3000000},
  "artifact": {"uri": "<immutable-run-bundle>", "sha256": "<digest>"},
  "evaluation": {"status": "unavailable", "revision": null, "uri": null},
  "analyses": [{"id": "<analysis-id>", "code_revision": "<commit>", "uri": "<results>"}]
}
```

Also document token-counter semantics and completeness: cached versus
uncached counts, missing sessions/snapshots, skipped records, and unlinked
posts. Store source hashes, analyzer/model/prompt versions, timestamps, and
explicit errors with every derived analysis. Preserve previous attempts rather
than replacing a failure with an apparently successful fallback.
