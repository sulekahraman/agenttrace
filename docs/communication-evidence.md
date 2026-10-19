# Missing evidence for reliable communication-failure assessment

The experimental `communication_failures_v1` setup can assess evidenced
Disclosure, Delivery, Reading and Action incidents without complete telemetry.
**Unknown is not a negative; repaired failures still count.**

## Richer export (October 19)

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
outputs. Model input currently caps text at 8,000 characters/event and 240,000
total. This cohort yields 79 shortened and 771 omitted events, explicitly
listed per run. Missing full model inputs/workspace history and clipped context
limit attribution. Integration checks used synthetic judgments, not a live
provider evaluation; no precision/recall claim is established.

See [SharedNet capture recommendations](sharednet-capture-recommendations.md)
for preservation and CLI-instrumentation proposals.
