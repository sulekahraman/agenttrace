import asyncio
import json
from pathlib import Path
from typing import Literal

from inspect_ai.model import ChatMessageAssistant, GenerateConfig
from inspect_scout import AnswerStructured, Result, generate_answer
from pydantic import BaseModel, Field


MessageType = Literal[
    "question",
    "delegation_request",
    "acknowledgement",
    "status_update",
    "result_delivery",
    "evidence_observation",
    "proposal",
    "critique_disagreement",
    "agreement",
    "decision",
    "synthesis",
    "clarification",
    "artifact_sharing",
    "coordination",
    "social_heartbeat",
]

MESSAGE_TYPES = """
- question: asks for information, evaluation, clarification, or a decision
- delegation_request: assigns or requests concrete work from another agent
- acknowledgement: confirms receipt or understanding without substantive work
- status_update: reports progress, blockage, or current activity
- result_delivery: delivers completed analysis, output, or requested work
- evidence_observation: contributes facts, measurements, or observations
- proposal: suggests a plan, hypothesis, design, or next action
- critique_disagreement: challenges, rejects, or identifies a problem
- agreement: explicitly accepts or endorses another contribution
- decision: commits the group to a choice or conclusion
- synthesis: combines multiple contributions into a unified account
- clarification: resolves ambiguity or corrects interpretation
- artifact_sharing: publishes or points to a file, link, run, or other artifact
- coordination: manages sequencing, ownership, deadlines, or process
- social_heartbeat: greeting, availability ping, or low-content presence update
""".strip()

RULES = """
1. Label only the target message.
2. Describe observable communicative function, not quality or success.
3. Choose one primary type and at most two secondary types.
4. Keep explicit citations separate from inferred replies_to relationships.
5. Every replies_to number must be earlier than the target message number.
6. Support inferred fields with short target-message evidence; mark real uncertainty.
""".strip()


class AnnotationEvidence(BaseModel):
    field: str = Field(description="The inferred field supported by this span.")
    text: str = Field(description="A short verbatim span from the target message.")


class MessageAnnotation(BaseModel):
    primary_type: MessageType = Field(description="The target's principal communicative function.")
    secondary_types: list[MessageType] = Field(default_factory=list, max_length=2, description="Up to two additional communicative functions.")
    replies_to: list[int] = Field(default_factory=list, description="Earlier message numbers from supplied context that the target responds to.")
    addressed_to: list[str] = Field(default_factory=list, description="Agent roster IDs addressed by the target.")
    confidence: float = Field(ge=0, le=1, description="Confidence in the annotation from zero to one.")
    ambiguous: bool = Field(description="Whether the message's communicative function is genuinely ambiguous.")
    rationale: str = Field(max_length=500, description="Brief reasoning grounded in the target message.")
    evidence: list[AnnotationEvidence] = Field(default_factory=list, max_length=3, description="Verbatim target-message spans supporting inferred fields.")


def _message_text(message: ChatMessageAssistant) -> str:
    return message.text.strip()


def _metadata(message: ChatMessageAssistant) -> dict:
    return message.metadata or {}


def build_annotation_prompt(message: ChatMessageAssistant) -> str:
    metadata = _metadata(message)
    context = metadata.get("annotation_context") or {}
    target_number = int(metadata.get("sequence") or 0)
    participant = metadata.get("participant_id", "unknown-agent")
    timestamp = metadata.get("timestamp") or "unknown-time"

    roster = context.get("roster") or []
    roster_text = "\n".join(
        f"- {agent.get('id')}: {agent.get('runtime', 'unknown runtime')}"
        for agent in roster
    ) or "- unavailable"

    def render_messages(messages: list[dict], cap: int) -> str:
        if not messages:
            return "None."
        return "\n\n".join(
            f"#{item.get('index')} {item.get('participant_id')} "
            f"({item.get('timestamp') or 'unknown-time'}):\n"
            f"{str(item.get('text', ''))[:cap]}"
            for item in messages
        )

    return f"""
You are annotating one message from a multi-agent collaboration trace.
Agents work asynchronously in one shared, ordered room.

MESSAGE TYPES:
{MESSAGE_TYPES}

RULES:
{RULES}

AGENT ROSTER:
{roster_text}

MESSAGES THE TARGET EXPLICITLY CITES:
{render_messages(context.get("cited_messages") or [], 2_000)}

THE 12 MESSAGES IMMEDIATELY BEFORE THE TARGET:
{render_messages(context.get("previous_messages") or [], 500)}

RULE-BASED HINTS FOR THE TARGET:
{json.dumps(context.get("hints") or {}, sort_keys=True)}

TARGET MESSAGE TO LABEL:
#{target_number} {participant} ({timestamp}):
{_message_text(message)[:8_000]}

Label only the target message. Every number in replies_to must be lower than
{target_number}. addressed_to must use roster ids. Evidence spans must come
from the target message.
""".strip()


def normalize_annotation(
    annotation: MessageAnnotation,
    target_number: int,
    roster_ids: set[str],
) -> MessageAnnotation:
    secondary_types = [
        label
        for label in annotation.secondary_types
        if label != annotation.primary_type
    ][:2]
    replies_to = sorted({
        number
        for number in annotation.replies_to
        if 0 < number < target_number
    })
    addressed_to = list(dict.fromkeys(
        agent for agent in annotation.addressed_to if agent in roster_ids
    ))
    return annotation.model_copy(update={
        "secondary_types": secondary_types,
        "replies_to": replies_to,
        "addressed_to": addressed_to,
    })


async def annotate_message(
    message: ChatMessageAssistant,
    model: str | None = None,
    artifacts: Path | None = None,
) -> Result:
    metadata = _metadata(message)
    context = metadata.get("annotation_context") or {}
    target_number = int(metadata.get("sequence") or 0)
    roster_ids = {
        agent.get("id")
        for agent in context.get("roster") or []
        if agent.get("id")
    }
    prompt = build_annotation_prompt(message)
    if artifacts is not None:
        (artifacts / f"message-{target_number}.prompt.txt").write_text(prompt, encoding="utf-8")
    generated = await generate_answer(
        prompt,
        AnswerStructured(type=MessageAnnotation),
        model=model,
        config=GenerateConfig(cache=True),
    )
    if not isinstance(generated, Result) or generated.parsed is None:
        raise ValueError(f"Message #{target_number} returned no structured annotation.")

    annotation = normalize_annotation(generated.parsed, target_number, roster_ids)
    valid_previous = {
        item["index"] for item in (
            context.get("previous_messages", []) + context.get("cited_messages", [])
        )
    }
    if any(number not in valid_previous for number in annotation.replies_to):
        raise ValueError(f"Message #{target_number} cites a reply not in its supplied context.")
    if any(item.text not in message.text for item in annotation.evidence):
        raise ValueError(f"Message #{target_number} returned evidence not in the message.")
    if artifacts is not None:
        (artifacts / f"message-{target_number}.result.json").write_text(
            annotation.model_dump_json(indent=2), encoding="utf-8"
        )
    return Result(
        value=annotation.model_dump(mode="json"),
        label=annotation.primary_type,
        explanation=annotation.rationale,
        metadata={
            "target_sequence": target_number,
            "participant_id": metadata.get("participant_id"),
            "secondary_types": annotation.secondary_types,
            "replies_to": annotation.replies_to,
            "addressed_to": annotation.addressed_to,
            "confidence": annotation.confidence,
            "ambiguous": annotation.ambiguous,
            "evidence": [item.model_dump() for item in annotation.evidence],
        },
        parsed=annotation,
        type="message_annotation",
    )


async def annotate_messages(
    messages: list[ChatMessageAssistant],
    concurrency: int = 8,
    model: str | None = None,
    artifacts: Path | None = None,
) -> list[tuple[ChatMessageAssistant, MessageAnnotation]]:
    semaphore = asyncio.Semaphore(concurrency)

    async def annotate(message: ChatMessageAssistant):
        async with semaphore:
            result = await annotate_message(message, model=model, artifacts=artifacts)
            if not isinstance(result.parsed, MessageAnnotation):
                raise ValueError("Scout returned an invalid message annotation.")
            return message, result.parsed

    tasks = [asyncio.create_task(annotate(message)) for message in messages]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
