from typing import Literal

from inspect_ai.model import ChatMessageAssistant
from inspect_scout import (
    AnswerStructured,
    Result,
    Scanner,
    Transcript,
    generate_answer,
    message_numbering,
    scanner,
)
from pydantic import BaseModel, Field

from scout.annotations import MessageAnnotation, annotate_messages


FailureCategory = Literal[
    "duplicated_work",
    "weak_handoff",
    "unintegrated_information",
]

RELEVANT_TYPES = {
    "duplicated_work": {
        "status_update",
        "result_delivery",
        "evidence_observation",
        "proposal",
        "artifact_sharing",
    },
    "weak_handoff": {
        "delegation_request",
        "acknowledgement",
        "status_update",
        "result_delivery",
        "coordination",
        "decision",
        "synthesis",
    },
    "unintegrated_information": {
        "result_delivery",
        "evidence_observation",
        "proposal",
        "critique_disagreement",
        "decision",
        "synthesis",
        "artifact_sharing",
    },
}


class CollaborationFinding(BaseModel):
    category: FailureCategory = Field(alias="label")
    found: bool = Field(alias="value")
    explanation: str = Field(
        alias="explanation",
        description="Explain the finding and cite candidate messages as [M#].",
    )
    confidence: float = Field(ge=0, le=1)
    message_numbers: list[int] = Field(
        default_factory=list,
        description="Original TraceScope turn numbers supporting the finding.",
    )


def _candidate_positions(
    annotations: list[tuple[ChatMessageAssistant, MessageAnnotation]],
) -> set[int]:
    positions = set()
    for message, annotation in annotations:
        sequence = int((message.metadata or {}).get("sequence") or 0)
        relevant = any(
            annotation.primary_type in types
            or any(label in types for label in annotation.secondary_types)
            for types in RELEVANT_TYPES.values()
        )
        if relevant:
            positions.update({sequence - 1, sequence, sequence + 1})
    return {position for position in positions if position > 0}


def _annotation_index(
    annotations: list[tuple[ChatMessageAssistant, MessageAnnotation]],
) -> str:
    lines = []
    for message, annotation in annotations:
        metadata = message.metadata or {}
        lines.append(
            " | ".join([
                f"#{metadata.get('sequence', '?')}",
                str(metadata.get("participant_id", "unknown-agent")),
                f"primary={annotation.primary_type}",
                f"secondary={','.join(annotation.secondary_types) or '-'}",
                f"replies_to={annotation.replies_to}",
                f"addressed_to={annotation.addressed_to}",
                f"confidence={annotation.confidence:.2f}",
                f"rationale={annotation.rationale[:240]}",
            ])
        )
    return "\n".join(lines)


def _candidate_messages(
    transcript: Transcript,
    positions: set[int],
) -> list[ChatMessageAssistant]:
    candidates = []
    for message in transcript.messages:
        if not isinstance(message, ChatMessageAssistant):
            continue
        metadata = message.metadata or {}
        sequence = int(metadata.get("sequence") or 0)
        if sequence not in positions:
            continue
        participant = metadata.get("participant_id", "unknown-agent")
        candidates.append(ChatMessageAssistant(
            id=message.id,
            content=(
                f"TraceScope turn #{sequence}; agent {participant}\n"
                f"{message.text[:2_000]}"
            ),
            metadata=metadata,
        ))
    return candidates[:80]


@scanner(messages="all", version=1)
def annotation_guided_collaboration() -> Scanner[Transcript]:
    async def scan(transcript: Transcript):
        messages = [
            message
            for message in transcript.messages
            if isinstance(message, ChatMessageAssistant)
        ]
        annotations = await annotate_messages(messages)
        if not annotations:
            return Result(
                value=False,
                label="annotation_failed",
                explanation="No messages could be annotated.",
            )

        positions = _candidate_positions(annotations)
        if not positions:
            positions = {
                int((message.metadata or {}).get("sequence") or 0)
                for message in messages
            }
        candidates = _candidate_messages(transcript, positions)
        messages_as_str, extract_refs = message_numbering()
        candidate_text = await messages_as_str(candidates)
        question = f"""
Use the message annotations as candidate-generation evidence, then verify every
finding against the candidate message text.

ANNOTATION INDEX:
{_annotation_index(annotations)}

CANDIDATE MESSAGES:
{candidate_text}

Return exactly one record for each category:

1. duplicated_work: Different agents independently repeat materially equivalent
   analysis or execution without a clear verification, synthesis, or handoff
   purpose. Do not count acknowledgements, context summaries, or deliberate
   independent checks.
2. weak_handoff: Requested work is not acknowledged or delivered, delivered
   work is not integrated, ownership is unclear, or a request is abandoned.
3. unintegrated_information: Relevant visible information is later ignored,
   contradicted without resolution, or omitted from a decision despite a clear
   opportunity to use it.

Use found=false when evidence is insufficient. Explanations must cite the
candidate messages using [M#]. message_numbers must contain the original turn
numbers shown in the candidate message metadata, not the [M#] display labels.
""".strip()

        return await generate_answer(
            question,
            AnswerStructured(type=list[CollaborationFinding]),
            extract_refs=extract_refs,
        )

    return scan
