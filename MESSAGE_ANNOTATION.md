# Message Annotation and Collaboration Scanning

TraceScope uses message annotations as an optional semantic layer between the
raw transcript and conversation-level failure scanners:

```text
raw messages
  -> deterministic hints and bounded context
  -> one structured annotation per message
  -> annotation-guided candidate selection
  -> cited conversation-level findings
```

The deterministic TraceScope metrics remain unchanged. Annotations and findings
are model judgments produced by Inspect Scout.

## Message types

Each message receives one primary type and up to two secondary types:

`question`, `delegation_request`, `acknowledgement`, `status_update`,
`result_delivery`, `evidence_observation`, `proposal`,
`critique_disagreement`, `agreement`, `decision`, `synthesis`,
`clarification`, `artifact_sharing`, `coordination`, or `social_heartbeat`.

Messages also record inferred reply links, addressed agents, confidence,
ambiguity, a short rationale, and supporting text spans.

## Context

Each target message is annotated with:

- The agent roster
- Up to six explicitly cited earlier messages
- The twelve immediately preceding messages
- Deterministic hints for citations, addressees, artifacts, and heartbeats

Only earlier messages may appear in `replies_to`. Future messages are excluded
to prevent outcome leakage during message classification.

The context is embedded when exporting and importing the Scout bridge. Re-import
older transcripts before running these scanners.

## Rules

1. Label only the target message.
2. Describe its observable communicative function, not whether it was good.
3. Use one primary type and no more than two secondary types.
4. Keep explicit citations separate from inferred reply relationships.
5. Support inferred fields with short target-message evidence.
6. Mark genuine uncertainty with `ambiguous` and lower confidence.

## Scout workflow

Generate reusable message annotations:

```bash
scout scan scout/message_annotations.py \
  -T ./transcripts \
  --model openai/gpt-5 \
  --cache
```

Run the end-to-end annotation-guided failure scanner:

```bash
scout scan scout/scanners.py \
  -T ./transcripts \
  --model openai/gpt-5 \
  --cache
```

The end-to-end scanner annotates messages, selects bounded candidate evidence,
and returns one cited result for each of:

- Duplicated work
- Weak or failed handoffs
- Relevant information that was not integrated

Before treating annotations or findings as research measures, validate them on
a human-labeled set and report agreement, per-class errors, and prompt/model
versions.
