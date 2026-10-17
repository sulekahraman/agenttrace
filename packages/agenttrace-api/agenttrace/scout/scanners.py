import json
from pathlib import Path
from typing import Literal

from inspect_ai.model import ChatMessageAssistant, GenerateConfig
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

from agenttrace.scout.annotations import MessageAnnotation, annotate_messages


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
    category: FailureCategory = Field(alias="label", description="The collaboration failure category.")
    found: bool = Field(alias="value", description="Whether candidate evidence supports this failure.")
    explanation: str = Field(
        alias="explanation",
        description="Explain the finding and cite candidate messages as [M#].",
    )
    confidence: float = Field(ge=0, le=1, description="Confidence in the finding from zero to one.")
    message_numbers: list[int] = Field(
        default_factory=list,
        description="Original AgentTrace turn numbers supporting the finding.",
    )


def _candidate_positions(
    annotations: list[tuple[ChatMessageAssistant, MessageAnnotation]],
) -> set[int]:
    positions = set()
    for position, (message, annotation) in enumerate(annotations):
        sequence = int((message.metadata or {}).get("sequence") or 0)
        relevant = any(
            annotation.primary_type in types
            or any(label in types for label in annotation.secondary_types)
            for types in RELEVANT_TYPES.values()
        )
        if relevant:
            positions.update(
                int((neighbor.metadata or {}).get("sequence") or 0)
                for neighbor, _ in annotations[max(0, position - 1):position + 2]
            )
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
                f"AgentTrace turn #{sequence}; agent {participant}\n"
                f"{message.text[:2_000]}"
            ),
            metadata=metadata,
        ))
    return candidates[:80]


async def analyze_collaboration(
    transcript: Transcript,
    model: str | None = None,
    artifacts: Path | None = None,
) -> dict:
    messages = [
        message
        for message in transcript.messages
        if isinstance(message, ChatMessageAssistant)
    ]
    annotations = await annotate_messages(messages, model=model, artifacts=artifacts)
    if not annotations:
        raise ValueError("No messages could be annotated.")

    positions = _candidate_positions(annotations)
    if not positions:
        positions = {
            int((message.metadata or {}).get("sequence") or 0)
            for message in messages
        }
    candidates = _candidate_messages(transcript, positions)
    messages_as_str, extract_refs = message_numbering()
    candidate_text = await messages_as_str(candidates)
    original_numbers = [int(message.metadata["sequence"]) for message in candidates]
    reference_map = "\n".join(
        f"[M{position}] -> AgentTrace turn #{number}"
        for position, number in enumerate(original_numbers, 1)
    )
    question = f"""
Use the message annotations as candidate-generation evidence, then verify every
finding against the candidate message text.

ANNOTATION INDEX:
{_annotation_index(annotations)}

CANDIDATE MESSAGES:
{candidate_text}

CANDIDATE REFERENCE MAP:
{reference_map}
Allowed message_numbers: {original_numbers}
Display labels and original turn numbers are different identifiers. Original
turn numbers can have gaps because non-agent messages are excluded. For each
[M#] explanation citation, use its mapped original turn in message_numbers.
Never infer missing turns or cite annotation-only messages.

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

    if artifacts is not None:
        (artifacts / "collaboration.prompt.txt").write_text(question, encoding="utf-8")
    result = await generate_answer(
        question,
        AnswerStructured(type=list[CollaborationFinding]),
        extract_refs=extract_refs,
        model=model,
        config=GenerateConfig(cache=True),
    )
    if not isinstance(result, Result) or result.parsed is None:
        raise ValueError("Scout returned no structured collaboration findings.")
    expected = {"duplicated_work", "weak_handoff", "unintegrated_information"}
    if len(result.parsed) != 3 or {item.category for item in result.parsed} != expected:
        raise ValueError("Scout must return exactly one finding for each collaboration category.")
    valid_numbers = {int(message.metadata["sequence"]) for message in candidates}
    for finding in result.parsed:
        if any(number not in valid_numbers for number in finding.message_numbers):
            raise ValueError("Scout finding cites a message outside the candidate evidence.")
        if finding.found and not finding.message_numbers:
            raise ValueError("Positive Scout findings must cite supporting message numbers.")
    findings = [
        finding.model_dump(mode="json", by_alias=False)
        for finding in result.parsed
    ]
    output = {
        "findings": findings,
        "annotations": [
            {
                "message_number": int((message.metadata or {}).get("sequence") or 0),
                **annotation.model_dump(mode="json"),
            }
            for message, annotation in annotations
        ],
        "coverage": {
            "annotated_messages": len(annotations),
            "candidate_messages": len(candidates),
            "candidate_limit": 80,
            "candidate_text_limit": 2000,
            "truncated": len(positions) > len(candidates),
        },
    }
    if artifacts is not None:
        (artifacts / "collaboration.result.json").write_text(
            json.dumps(output, indent=2), encoding="utf-8"
        )
    return output


@scanner(messages="all", version=3)
def annotation_guided_collaboration() -> Scanner[Transcript]:
    async def scan(transcript: Transcript):
        output = await analyze_collaboration(transcript)
        return [
            Result(value=finding["found"], label=finding["category"],
                   explanation=finding["explanation"],
                   metadata={"message_numbers": finding["message_numbers"],
                             "confidence": finding["confidence"], "coverage": output["coverage"]})
            for finding in output["findings"]
        ]

    return scan
