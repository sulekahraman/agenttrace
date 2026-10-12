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

The end-to-end scanner selects messages using annotation types, explicit
citations, addressed agents and adjacent-turn context. It considers up to 80
candidate messages with 2,000 characters per candidate. Coverage reports
candidate/annotation counts and candidate-selection truncation.

It requires exactly one structured finding for each category:

| Category | Question |
| --- | --- |
| `duplicated_work` | Did agents redundantly repeat materially equivalent work without a clear verification purpose? |
| `weak_handoff` | Was requested work abandoned, ownership unclear, or delivered work not integrated? |
| `unintegrated_information` | Was relevant visible information ignored or omitted despite an opportunity to use it? |

Positive findings require original message numbers from supplied candidate
evidence. Those numbers are not the prompt's display labels. The UI jumps to
the cited original turn. Failed parsing or invalid references is reported as
an explicit failed analysis.

## Reproducibility

The same explicit model and cache configuration is used for annotations and
the collaboration call. Each run stores prompt/result artifacts, timestamps,
model, prompt version and package versions. Structural results remain in a
separate namespace. The standalone [Scout bridge](scout/README.md) is retained
for manual Scout databases and scans.

Annotations and findings are model judgments, not ground truth. Validate on a
human-labeled set and report per-class errors and prompt/model versions before
using them as research measures. Automated tests mock generation and exercise
Scout's real structured parser; they do not validate provider judgment quality.
