# Communication evidence, retrieval and uncertainty

The experimental `communication_failures_v1` setup can assess evidenced
Disclosure, Delivery, Reading and Action incidents without complete telemetry.
**Unknown is not a negative; repaired failures still count.**

## Scoped retrieval protocol (v0.3 / prompt 3)

See the [data-flow diagram, call counts and exact prompt templates](communication-analysis-flow.html).
The separate [fresh 12-run report](../reports/2026-10-21-v03-12-runs/README.md)
uses **v0.3 / prompt 3**, with fresh Scout results.
**Its communication protocol is mixed:** six runs completed independent A/B
searches, reviews and a judge. Nine review jobs failed across the other six
runs; the user approved direct recovery in one shared, non-blind parent session.
Those direct assessments inspected all agent posts and selected full native
details, not every original A/B window. Their uncompleted negative searches
remain Unknown, not No. Failed inference jobs are recorded separately and are
never interpreted as metric Unknowns. The historical
[October 19 report](../reports/2026-10-19-richer-evidence-12-runs/README.md)
remains unchanged **v0.2 / prompt 2** judgments.

The v0.2 input cap hid most full edits even though the source export contained
them; globally rejecting absence claims because *any* detail was omitted also
turned unrelated omissions into uncertainty. v0.3 keeps bounded discovery
(8,000 text characters/event, 240,000 total) but interleaves detail events by
actor. Independent A/B search calls request actor/time windows using indexed
event IDs. Deterministic retrieval then restores each requested window's full
commands, outputs, native edits and applicable workspace checkpoints. Actions
overlapping the window are included; no requested detail is clipped.

Independent A/B reviews receive their own packets, not each other's answers.
The judge receives both reviews and the union of their requested windows.
Each packet is limited to 1,200,000 event-text characters, excluding JSON
metadata; this is not a token/context guarantee. Oversized search requests get
validation feedback to narrow the windows. An oversized A/B union fails explicitly
before reviews rather than silently omitting evidence or reporting a verdict.

An absence-based incident needs a complete retrieved window covering its actors,
anchor and dependent event. A negative class decision needs complete reviewed
windows including both communicating participants. Certificates record required
events and source gaps; missing/truncated required events invalidate them.
Unrelated omissions outside those windows no longer invalidate them. Untimed
actions and missing author logs block completeness. Missing raw turns are
checked against wake intervals; incomplete calls, sessions and compactions
remain conservatively actor-wide. Certificates describe the checked export,
**not** proof that all possible telemetry was captured or that an LLM's semantic
interpretation is correct. No is a scoped search result, not universal absence.

**Flag versus impact:** a directly evidenced breakdown counts even without
proven downstream harm. Disclosure can be supported without a recipient-reliance
event, but still needs the author's relevant knowledge and sharing obligation.
Delivery still needs relevance to actual recipient work; reading and action
still require expressed understanding. Use `impact_status=not_established`
and `severity=null` when harm cannot be established.

Unknown decisions now carry one or more explicit reasons:

| Reason | Meaning |
| --- | --- |
| `missing_source_evidence` | The needed evidence was not captured in the frozen export. |
| `evidence_not_retrieved` | It exists in the export but is not in this review packet. |
| `ambiguous_cause` | Attribution of the breakdown is unresolved, not merely its impact. |
| `unclear_obligation` | A required commitment or need/opportunity to share is unestablished. |
| `unclear_understanding` | Recipient interpretation or retention is unestablished. |
| `ambiguous_timing` | Relevant publication, receipt or action ordering is unresolved. |

These reasons are model judgments, subject to structural validation. Unknown
cannot silently become No. Historical records lack these fields and remain
readable without retroactive inference.

The normal multi-agent execution is **5 application generation attempts**:
search-A, search-B, review A, review B, judge. Each stage permits 3 validation
attempts, so a successful run can use up to 15. Solo input uses 0. Saved
`execution.json` records attempts and their outcomes, including failures.
These are not provider-internal retries, billed HTTP requests, or Copilot
session turn counts. The fresh report records 66 original Copilot contexts
(57 completed, nine failed), followed by six direct judgments in the existing
parent context. Those judgments are not six independent jobs or judge calls.
HTTP requests, provider-internal retries, tokens and billing were not measured.

Per-run artifacts include discovery/source evidence, A/B review packets, union
review evidence, and `{stage}-{attempt}.prompt.json`, `.reply.json` and (when
rejected) `.errors.json`. Prompt JSON contains the exact rendered application
prompt and response schema; provider wrappers/system messages are not captured.
For the mixed report's direct recoveries, `direct-review.prompt.txt` is explicitly
a reconstructed inventory of staged source reads, not a separately submitted
prompt or the complete parent conversation. Its selected evidence and saved
reply are archived; surviving A proposals are retained as prior attempts, not
presented as an independent pair for the direct verdict.
The [diagram builder](build_communication_flow.py) reads live prompt constants
and Scout prompt source; regenerate with
`python3 docs/build_communication_flow.py` or check with `--check`.

## Richer export used by the saved report (October 19, v0.2)

`xisen-w/multi-agent-training#3`, revision
`bac848b623ea5563a7bfacb5082de91163040c4c`, supplies the same 12 rooms plus
195 recorded turn inputs, 2,322 timed actions, 36 native sessions and 174
workspace snapshots. The v0.2 importer consumes `inputs.jsonl`,
`actions.jsonl`, `workspace.json`, `agents/*/session.jsonl` and `workspace.git`
from an explicitly allowlisted local run directory.

It checks supplied file hashes when present, prompt text against native
sessions, action content/order/times against native and streamed logs,
workspace trees and final file hashes. Native item IDs differ from streamed
IDs; ordering and content are checked rather than assuming IDs match.
Tool-parent links are checked temporal-start associations, not native parent IDs.

Receipt uses completed **model-visible tool outputs**, never command stdout
alone. In two yj/n4 reads, the tool wrapper returned empty before the native
command completed. A published or internally returned message is not
automatically model-visible. Partial message objects and recorded compaction
block deterministic nonreceipt; incomplete capture fails or remains explicit.

All core posts and action/delivery/workspace summaries fit the
12 runs' existing 240,000-character text budget without core clipping or
omission. Long commands/outputs are summarized. Full details are lower-priority events, with every truncation and
omission recorded. Quotes must come from actually supplied events.

Remaining limits: recorded turn messages are not serialized model API
requests; snapshots have second precision and cover message batches rather
than individual actions. Exact patch diffs help, but simultaneous shell
writes may remain unattributable. Understanding still needs behavioral
evidence. Missing human labels prevent an accuracy claim.

## Earlier, limited export

Scope: 12 runs from `xisen-w/commsfail#10`, revision
`913ad1805642a38e5248d67e5d8c3b83c48b51b5`. All ingest successfully:
618 posts, 195 raw turns and 2,322 normalized operations, with no missing raw
turns relative to recorded wakes/operations. This does not prove export completeness.

**Missing from these exports:**

- **Exact delivered inputs:** per-agent, per-turn message IDs/content hashes,
  initial goal/instructions and tool-result associations. Wake bounds and
  bounded board reads are not complete input manifests or proof of understanding.
- **Workspace history:** baseline, action-linked changes/checkpoints and final
  artifact hashes. File-change paths alone cannot prove overwrites, final
  correctness, nonexecution or repair.
- **Action timing/causality:** stable action IDs, timestamped starts/completions
  and explicit turn/input links. Post timestamps do not date earlier work.

Optional task-evaluation summaries help estimate impact; independent human
incident labels are needed to measure accuracy. Neither is a prerequisite
for detecting an evidenced communication incident. These runs' check logs are empty.

**Importer limits, not source omissions:** normalized command output keeps
500 trailing characters; fresh local ingestion freezes full supported raw
outputs. The earlier bounded model input capped text at 8,000 characters/event and 240,000
total. That saved cohort yielded 79 shortened and 771 omitted events, explicitly
listed per run. Missing full model inputs/workspace history and clipped context
limit attribution. Integration checks used synthetic judgments, not a live
provider evaluation; no precision/recall claim is established.

See [SharedNet capture recommendations](sharednet-capture-recommendations.md)
for preservation and CLI-instrumentation proposals.
