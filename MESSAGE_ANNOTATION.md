# Message Annotation and Collaboration Scanning

AgentTrace uses Inspect Scout directly from its Python backend:

```text
canonical trace -> UI report -> Scout transcript with bounded earlier context
 -> structured message annotations -> candidate selection -> cited findings
```

Scout runs only after an explicit **Run Scout** request. It does not replace
the offline metrics or `commsfail` annotators. The selected model provider
receives trace content and may charge for generation.

## Message types

Each message receives one primary type and up to two secondary types:

`question`, `delegation_request`, `acknowledgement`, `status_update`,
`result_delivery`, `evidence_observation`, `proposal`,
`critique_disagreement`, `agreement`, `decision`, `synthesis`,
`clarification`, `artifact_sharing`, `coordination`, or `social_heartbeat`.

Annotations include inferred replies, addressed agents, confidence, ambiguity,
a brief rationale and target-message evidence spans.

## Bounded context

Each target receives the roster, up to six explicitly cited earlier messages
(2,000 characters each), twelve preceding messages (500 characters each),
and deterministic citation/addressee/artifact/heartbeat hints. Target text is
limited to 8,000 characters. Future messages are excluded from classification.

Reply links are normalized to supplied earlier context, and addressed agents
to the roster. Evidence spans must appear verbatim in the target text. Invalid
evidence fails the run rather than becoming a successful empty result.

## Collaboration findings

The end-to-end scanner selects messages using primary/secondary annotation
types and adjacent-turn context. Citations and addressees appear in annotation
context but do not independently select candidates. It considers up to 80
candidate messages with 2,000 characters per candidate. Coverage reports
candidate/annotation counts and candidate-selection truncation.

It requires exactly one structured finding for each category:

| Category | Question |
| --- | --- |
| `duplicated_work` | Did distinct agents substantively execute or deliver the same work without a clear verification, repair, synthesis, or handoff purpose? |
| `weak_handoff` | Did a concrete request or commitment fail, a delivered result go unintegrated, or incompatible ownership leave work uncoordinated? |
| `unintegrated_information` | Did a dependent decision/action ignore relevant information despite evidenced opportunity to use it? |

### Evidence and exclusions

Independent verification, assigned review, useful alternative derivations and
corrective rework are not duplicated work merely because they repeat analysis.
Repeated same-agent status reports, shared vocabulary and overlapping proposals
do not prove repeated execution. A positive duplication finding must cite at
least two distinct non-human participant IDs; the model must additionally
identify substantive work and explain why the legitimate purposes do not apply.

Offers do not establish accepted commitments. Snapshot silence, omitted
follow-ups and a missing acknowledgement alone do not prove abandonment.
Publication order does not establish receipt or reading: asynchronous agents
may post while another is working. Information-use findings must identify the
relevant post, the dependent decision/action, and positive evidence of an
opportunity to use it, such as explicit acknowledgement or discussion of its
content. A reasoned rejection or an agent's own calculation error is not by
itself a communication failure.

Candidate headers include publication timestamps and runtime labels. These
are context, not execution or delivery receipts. Message labels and inferred
relationships are retrieval hints, not ground-truth failure evidence.

### Recovered episodes

An evidenced failure counts even if it is later repaired. Positive explanations
must identify the local failed step and describe whether candidate evidence
shows repair, shows the problem remains unresolved, or leaves recovery unknown.
Any described repair must be cited. A normal proposal/challenge/review/correction
sequence is not itself a failure without a distinct failed coordination or
decision step. Do not infer an unrepaired failure just because later evidence
was omitted or truncated.

### Citation validation

Every finding, including a negative or insufficient-evidence judgment, must
cite candidate messages as `[M#]`. `message_numbers` must be exactly the set
of original turn numbers mapped from those citations. Display labels and
original turn numbers may differ. Out-of-range labels, mismatched citation sets
and positive findings without evidence fail explicitly; they are not rewritten
into negative findings. The UI continues to jump to the cited original turns.
`found=false` means insufficient qualifying evidence, not proof of absence.

## Reproducibility

The same explicit model and cache configuration is used for annotations and
the collaboration call. Each run stores prompt/result artifacts, timestamps,
model, prompt version and package versions. Structural results remain in a
separate namespace. The standalone [Scout bridge](scout/README.md) is retained
for manual Scout databases and scans.

New runs use analyzer **2.2.0**, prompt **8**, and collaboration-scanner version
**4**. This versions the stricter evidence rules and explicit recovered-episode
policy; message-annotation prompts are unchanged. Historical runs and published
reports retain their original versions and are not relabeled or overwritten.
Batch exports may reuse completed runs for the selected model; use
`agenttrace-batch --scout --rerun ...` to request fresh judgments under the
current rubric rather than re-exporting saved results.

Annotations and findings are model judgments, not ground truth. Validate on a
human-labeled set and report per-class errors and prompt/model versions before
using them as research measures. Automated tests mock generation and exercise
Scout's real structured parser; they do not validate provider judgment quality.
