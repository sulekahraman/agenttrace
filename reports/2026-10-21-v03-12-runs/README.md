# Fresh Scout + communication v0.3: 12 runs

**Fresh Scout and communication v0.3 / prompt 3 for all 12 traces.** 602 new Scout annotations, 36 new Scout findings, and 48 final communication decisions. Communication retains **46 supported incidents**, **6 unresolved candidates**, and **19/48 unknown class decisions**. These are model judgments, not ground truth.

October 21, 2026. GPT-6.1 Sol Copilot-session replay; no environment OpenAI/Azure keys or direct provider API calls.
This is a separate report; the [October 19 v0.2 results](../2026-10-19-richer-evidence-12-runs/README.md) are preserved.

[HTML report](index.html) · [Complete judgments](results.json) · [Compact summary](summary.json) ·
[Stage prompts, reconstructed direct input inventories, replies, schemas and supplied evidence (gzip JSON)](prompt-replay.json.gz) ·
[Data-flow diagram and prompt definitions](../../docs/communication-analysis-flow.html)

## All seven failure flags

| Run / AgentTrace visualization | Communication review method | Scout: duplicated work | Scout: weak handoff | Scout: unintegrated information | Incident: disclosure failure | Incident: delivery failure | Incident: reading failure | Incident: action failure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [xsv-n2-round1](http://127.0.0.1:3014/?trace=trace_810039cd98b3c8b0&analysis=run_v03fresh12_xsv-n2-round1_communication) | direct single-session | no | no | no | yes | yes | unknown | unknown |
| [xsv-n2-round2](http://127.0.0.1:3014/?trace=trace_f18bef1f6956af75&analysis=run_v03fresh12_xsv-n2-round2_communication) | direct single-session | no | no | no | yes | yes | unknown | unknown |
| [xsv-n2-round3](http://127.0.0.1:3014/?trace=trace_3ce5b38eb14b6137&analysis=run_v03fresh12_xsv-n2-round3_communication) | direct single-session | no | no | no | unknown | yes | unknown | unknown |
| [xsv-n3-round1](http://127.0.0.1:3014/?trace=trace_f1509e7ad764d54a&analysis=run_v03fresh12_xsv-n3-round1_communication) | direct single-session | yes | yes | no | yes | yes | unknown | unknown |
| [xsv-n3-round2](http://127.0.0.1:3014/?trace=trace_abb6da728982d695&analysis=run_v03fresh12_xsv-n3-round2_communication) | direct single-session | yes | no | no | yes | unknown | unknown | unknown |
| [xsv-n3-round3](http://127.0.0.1:3014/?trace=trace_b7ff2953e20e3e5e&analysis=run_v03fresh12_xsv-n3-round3_communication) | direct single-session | yes | no | no | yes | yes | unknown | unknown |
| [xsv-n4-round1](http://127.0.0.1:3014/?trace=trace_a49b03f1df3bca94&analysis=run_v03fresh12_xsv-n4-round1_communication) | independent A/B + judge | yes | no | no | yes | no | no | no |
| [xsv-n4-round2](http://127.0.0.1:3014/?trace=trace_abaad9e890b53c8a&analysis=run_v03fresh12_xsv-n4-round2_communication) | independent A/B + judge | no | no | no | yes | yes | no | no |
| [xsv-n4-round3](http://127.0.0.1:3014/?trace=trace_f4edfa23b99faa29&analysis=run_v03fresh12_xsv-n4-round3_communication) | independent A/B + judge | yes | no | no | yes | unknown | no | no |
| [yj-n2-round1](http://127.0.0.1:3014/?trace=trace_b128ff4c92d47fa5&analysis=run_v03fresh12_yj-n2-round1_communication) | independent A/B + judge | no | no | no | yes | yes | unknown | unknown |
| [yj-n3-round1](http://127.0.0.1:3014/?trace=trace_c25e8be963216dac&analysis=run_v03fresh12_yj-n3-round1_communication) | independent A/B + judge | yes | no | no | yes | yes | unknown | unknown |
| [yj-n4-round1](http://127.0.0.1:3014/?trace=trace_ae5cc6010f6d3028&analysis=run_v03fresh12_yj-n4-round1_communication) | independent A/B + judge | yes | yes | no | yes | yes | no | no |

**Legend:** **yes** = this failure type was flagged; communication requires a final supported incident. **no** = no qualifying failure was flagged; communication negatives apply only to complete reviewed scopes, not the whole run or every possible failure. **unknown** = insufficient evidence to decide, neither yes nor no. Scout is binary and cannot report unknown. A/B proposals alone are not final flags. A rejected candidate is not a run-level No; another candidate can still be supported or unknown. Repair does not erase a failure; breakdown and downstream harm are separate.

## Counts, not scores

| Failure metric | Runs: yes | Runs: no | Runs: unknown | Supported incidents |
| --- | --- | --- | --- | --- |
| Scout: duplicated work | 7 | 5 | 0 | not an incident metric |
| Scout: weak handoff | 2 | 10 | 0 | not an incident metric |
| Scout: unintegrated information | 0 | 12 | 0 | not an incident metric |
| Incident: disclosure failure | 11 | 0 | 1 | 33 |
| Incident: delivery failure | 9 | 1 | 2 | 13 |
| Incident: reading failure | 0 | 4 | 8 | 0 |
| Incident: action failure | 0 | 4 | 8 | 0 |

Run columns each sum to 12. Incidents count individual first-transition breakdowns; a run can have multiple.
Unknown class reasons (one decision may have several): `{"ambiguous_cause": 6, "evidence_not_retrieved": 14, "unclear_obligation": 1, "unclear_understanding": 16}`.
Of 46 supported incidents, 1 have separately evidenced downstream impact.
Missing proof of harm does not invalidate an observed breakdown; unestablished impact has null severity.

## Metric definitions

| Metric | What yes means |
| --- | --- |
| Scout: duplicated work | Different agents repeat materially equivalent work without a useful verification, synthesis, handoff or corrective purpose. |
| Scout: weak handoff | A concrete request or commitment is abandoned, its result is not delivered/integrated, or conflicting ownership causes observable coordination failure. Silence alone is insufficient. |
| Scout: unintegrated information | A later dependent decision ignores or contradicts relevant shared information despite positive evidence of an opportunity to use it. Publication order alone is insufficient. |
| Incident: disclosure failure | An agent knows relevant information but fails to share it clearly, accurately and in time when sharing is required. |
| Incident: delivery failure | Clearly shared information does not reach the intended recipient before relevant actual work. Publication/native stdout alone does not establish model-visible receipt. |
| Incident: reading failure | The recipient receives a clear message but expresses an incorrect interpretation or forgets it. Receipt alone does not establish understanding. |
| Incident: action failure | The recipient receives and correctly understands a commitment, but subsequent execution violates it. An ordinary coding error alone does not qualify. |

Definitions: [Scout rubric (analyze_collaboration)](../../packages/agenttrace-api/agenttrace/scout/scanners.py);
[communication RUBRIC / Incident / ClassAssessment](../../packages/agenttrace-api/agenttrace/communication/analysis.py);
[retrieval/completeness rules](../../packages/agenttrace-api/agenttrace/communication/evidence.py).
Communication assigns only the first evidenced failed transition: disclosure → delivery → reading → action.
See the HTML report for final class decisions, explicit unknown reasons, evidence scopes and incidents.
Only the six independent-review traces have A/B proposals and candidate adjudication.

## Execution and limitations

**Mixed review protocol.** Six traces retain their completed independent A/B + judge outputs unchanged.
The six xsv n2/n3 traces instead use **direct single-session** Assessments authored by the parent in shared
session `141c12e0-1ebe-4856-92f6-738fb99cce57`; these are not independent A/B reviews, judge results, or six independent jobs.
Original successful search-A/B replies are reused. Surviving A proposals are archived as prior attempts and
ignored for direct decisions. There are no synthetic A/B annotations or candidate adjudication decisions.
No full-cohort A/B agreement statistic is reported.
**The direct-review prompt files are reconstructed application input inventories of staged reads in the
existing shared parent context, not separately submitted independent model prompts.** They do not reconstruct
the entire parent conversation. Direct judgments are not comparable in robustness to independent A/B + judge.

**66 previously launched agent contexts: 12 Scout + 24 search + 24 review + 6 judge;
57 succeeded, 9 failed.** The failed review stages remain failed. Six additional direct assessments share
the existing parent session. Exact assignments and failure statuses are archived.
The independent traces use the native five-stage pipeline with saved replies; direct traces bypass it
and validate only their actual Assessment and the two reused searches.
Saved-response validation counters are **not inference calls or billed API-call counts**.
Scout's native formula would be 602 annotation generations + 12 collaboration generations without retries;
our per-trace grouped sessions are **not 614 independent native calls**.
Copilot-internal turns, requests, tokens and billing are unmeasured.

Source: xisen-w/multi-agent-training#3, pinned to `bac848b623ea5563a7bfacb5082de91163040c4c`.
The gzip archive includes exact submitted independent-stage prompts, reconstructed direct-review input
inventories, schemas/replies, fresh Scout input, full frozen source evidence,
and the exact packet supplied to each actual reviewer. Direct review need not use the A/B union:
its exact supplied packet determines the published evidence and coverage.
Direct input selection consists of all non-goal communication posts, indexed command/receipt discovery,
and selected fully inspected source events. This does not mean the whole union or full trace was reviewed.
Omitted source details are **evidence_not_retrieved**, not missing_source_evidence.
Source-complete certificates cover particular actor/time windows; reviewer-selected source events without
certificates cannot support scoped absence or negative claims. Copilot system wrappers/internal conversations are not captured.
`results.json` records session IDs, source/code hashes and prompt/reply hashes.

- Fresh GPT-6.1 Sol Copilot-session judgments, not native Inspect/provider generation or human ground truth.
- Scout targets and the collaboration scan share one context per trace, including possible later-target lookahead; not 614 independent native calls.
- Mixed review protocol: six traces use independent A/B + judge; six xsv n2/n3 traces use a direct single-session Assessment. No full-cohort A/B agreement statistic is valid.
- 66 previously launched agent contexts: 12 Scout + 24 search + 24 review + 6 judge; 57 succeeded and 9 failed. Failed stages remain failed, not replaced with fabricated A/B or judge replies.
- Six direct assessments were authored in parent session 141c12e0-1ebe-4856-92f6-738fb99cce57, sharing context; they are not six independent contexts. Original successful searches are reused. Surviving A proposals are prior attempts, ignored for direct decisions.
- Direct-review prompt files are reconstructed application input inventories for staged reads in the existing shared parent context, not separately submitted independent prompts. The complete parent conversation is not reconstructed.
- Direct review covers all non-goal communication posts, indexed command/receipt discovery, and selected inspected full source events, not the entire union or full trace. Omitted source details are evidence_not_retrieved, not missing_source_evidence. Direct judgments do not provide robustness comparable to independent A/B + judge.
- Execution counters describe saved-response validation, not additional inference or provider billing. Copilot internal turns, HTTP requests, billed calls and tokens are not measured.
- Independent same-model judgments can share errors. Validation verifies structure, citations and evidence scopes, not semantic accuracy.
- No is a scoped negative, not universal absence. Unknown is not No. Receiving text is not proof of understanding.
- Source-complete retrieval certificates cover specific actor/time windows, not whole-run completeness. Reviewer-selected source events alone do not certify complete windows or justify absence claims.
- Recorded inputs/tool outputs are not complete serialized model API requests; workspace checkpoints have batch-level timing and causal-attribution limits.
- v0.2-to-v0.3 changes mix evidence access, decision rules and sampling; this is not a controlled ablation or an accuracy-improvement measurement.
- Localhost viewer links require the matching restored database on the reader's machine, or rewriting links to a shared viewer.

## Share or restore without inference

Send `index.html` for a standalone readable report; send this folder for judgments and replay artifacts.
**Visualization links use 127.0.0.1:3014:** teammates need their own restored local viewer, or a shared viewer.
Repository/documentation links require the surrounding checkout.

```bash
env -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY \
  PYTHONPATH=packages/commsfail:packages/agenttrace-api \
  .venv/bin/python reports/2026-10-21-v03-12-runs/build_report.py \
  restore --viewer .agenttrace/restored-v03
env -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY \
  PYTHONPATH=packages/commsfail:packages/agenttrace-api \
  .venv/bin/python reports/2026-10-21-v03-12-runs/viewer.py \
  --viewer .agenttrace/restored-v03 --port 3014
```

Restore copies the checked-in baseline SQLite into a new directory, verifies the archived evidence, and saves only
these new analysis records. It never initializes the original database or invokes a model.
Regenerate the readable reports with `python3 reports/2026-10-21-v03-12-runs/build_report.py render`.
