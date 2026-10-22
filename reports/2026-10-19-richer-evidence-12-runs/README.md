# Richer-evidence reassessment: 12 runs

Open [the HTML report](index.html) for the metric definitions, clarified tables,
expandable findings and per-run AgentTrace UI links.
[Complete results](results.json) preserve all judgments, exact supplied citations, separate A/B
records, adjudication decisions, model/session identities and input/code hashes.
[The machine-readable summary](summary.json) holds counts and visualization URLs.

The report defines all seven metrics and separates Scout's saved binary flags
from the communication adjudicator's Yes / No qualifying failure found / Unknown
decisions. Unknown is an abstention, not a negative. Comparison totals count
runs; incident totals count individual failures. Expand a run to compare
annotator A, annotator B and the final adjudicator, including candidate rejections.
Rejecting one candidate does not necessarily make the run's metric negative.

**Protocol update, not a results update:** these remain v0.2/prompt 2 judgments.
The new [annotator-flow diagram and exact prompts](../../docs/communication-analysis-flow.html)
describe v0.3's targeted full-evidence retrieval, explicit uncertainty reasons and
separate impact assessment. These 12 runs have not been rerun under v0.3.

## Latest results

### All seven failure flags together

One row per run; each cell is a failure flag, not an incident count. Scout flags
are unchanged from the earlier analysis. Incident flags are the final
communication adjudicator's decisions, not individual A/B proposals.

| Run | Scout: duplicated work | Scout: weak handoff | Scout: unintegrated information | Incident: disclosure failure | Incident: delivery failure | Incident: reading failure | Incident: action failure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| xsv-n2-round1 | no | no | no | unknown | yes | no | no |
| xsv-n2-round2 | no | no | no | no | yes | no | unknown |
| xsv-n2-round3 | no | no | no | unknown | yes | unknown | unknown |
| xsv-n3-round1 | yes | yes | no | unknown | yes | no | no |
| xsv-n3-round2 | yes | no | no | no | unknown | no | no |
| xsv-n3-round3 | yes | no | no | unknown | yes | no | unknown |
| xsv-n4-round1 | yes | no | no | yes | no | no | no |
| xsv-n4-round2 | no | no | no | no | yes | no | no |
| xsv-n4-round3 | yes | no | no | unknown | no | no | no |
| yj-n2-round1 | no | no | no | unknown | no | unknown | unknown |
| yj-n3-round1 | yes | no | no | no | no | no | no |
| yj-n4-round1 | yes | yes | no | unknown | unknown | yes | unknown |

**Legend:** **yes** means the analysis flagged this failure type in the run
(for communication, the final adjudicator retained at least one supported
incident). **no** means no qualifying failure was flagged; for communication,
the type was assessable and no qualifying incident was found within the supplied
evidence. It is not proof of absence. **unknown** means the communication evidence
was insufficient for a decision: neither yes nor no. Scout is binary and has no
unknown output. Later repair does not change an evidenced yes to no.

### Communication totals

| Communication failure type | Runs with a final failure flag | Runs with no qualifying failure found | Runs with inconclusive evidence | Supported failure incidents |
| --- | --- | --- | --- | --- |
| Disclosure | 1/12 | 4/12 | 7/12 | 1 |
| Delivery | 6/12 | 4/12 | 2/12 | 7 |
| Reading | 1/12 | 9/12 | 2/12 | 1 |
| Action | 0/12 | 7/12 | 5/12 | 0 |

The first three numeric columns count **runs**, not incidents. A final failure
flag means the model adjudicator retained at least one supported incident of
that type. No qualifying failure found is a scoped negative; inconclusive
evidence is **Unknown, not No**. Nine supported incidents and six unresolved
candidates are retained in total. These are model judgments, not ground truth.

Scout's unchanged binary flags are positive in 7/12 runs for duplicated work,
2/12 for weak handoff and 0/12 for unintegrated information. Scout does not
have a separate Unknown output.

## Sharing with teammates

Send or download `index.html` and open it in a browser. Its tables, metric
definitions and expandable A/B/adjudicator findings work without a server.
Zip this entire report folder to also include the saved JSON judgments.

**The visualization links are local-only:** they point to
`http://127.0.0.1:3013`, so they do not connect to the author's computer when
opened by a teammate. Interactive visualizations require a shared viewer or a
teammate's own local viewer with the restored results. Source-code, evidence
documentation and previous-report links require the surrounding repository;
they are not bundled into a standalone HTML file or report-folder zip.

## Evidence and reproduction

Only communication failures are rerun: v0.2.0, prompt 2, using 36 independent
GPT-6.1 Sol Copilot session stages, with no direct provider/API-key calls.
The three Scout flags and 602 annotations are carried over unchanged from
`../2026-10-19-sol-12-runs/`; their shared-context caveat still applies.

Source: `xisen-w/multi-agent-training#3`, pinned to
`bac848b623ea5563a7bfacb5082de91163040c4c`. Room messages and wakes are unchanged.
The new inputs, native sessions, timed actions and workspace snapshots are
validated before annotation. All core summaries fit without additional clipping;
long commands/outputs are summarized and full-detail supplements remain explicitly
bounded. These are model assessments, not calibrated
accuracy, and the previous/new comparison is not a controlled experiment.

The local read-only viewer uses `.agenttrace/rich-12-runs-2026-10-19` on port
3013. The previous database and port 3012 are untouched. To restore saved
analyses into a new directory without inference:

```bash
.venv/bin/python reports/2026-10-19-richer-evidence-12-runs/build_report.py \
  restore --viewer .agenttrace/restored-rich-results
```

Restoration is for viewing saved results, not reconstructing the private raw
capture. A new assessment needs the pinned source export and fresh ingestion.
See `../../docs/communication-evidence.md` for remaining telemetry limits.
