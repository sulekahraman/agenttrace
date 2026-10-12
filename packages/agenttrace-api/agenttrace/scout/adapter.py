from __future__ import annotations

import re
from inspect_ai.model import ChatMessageAssistant
from inspect_scout import Transcript


def _extract_citations(text: str, target: int, valid: set[int]) -> list[int]:
    citations = []
    for match in re.finditer(r"(?:#|\[M)(\d+)\]?", text, re.I):
        number = int(match.group(1))
        if number < target and number in valid and number not in citations:
            citations.append(number)
    return citations[:6]


def transcript_from_report(report: dict) -> Transcript:
    roster = [
        {
            "id": participant["id"],
            "sender": participant["sender"],
            "instance": participant["instance"],
            "runtime": participant["runtime"],
        }
        for participant in report["participants"]
    ]
    valid = {message["index"] for message in report["messages"]}
    by_index = {message["index"]: message for message in report["messages"]}
    messages = []

    for position, message in enumerate(report["messages"]):
        citations = _extract_citations(message["text"], message["index"], valid)
        previous = report["messages"][max(0, position - 12) : position]
        context = {
            "guide_version": "1.0",
            "roster": roster,
            "cited_messages": [
                {
                    "index": number,
                    "participant_id": by_index[number]["participantId"],
                    "timestamp": by_index[number]["timestamp"],
                    "text": by_index[number]["text"][:2000],
                }
                for number in citations
            ],
            "previous_messages": [
                {
                    "index": item["index"],
                    "participant_id": item["participantId"],
                    "timestamp": item["timestamp"],
                    "text": item["text"][:500],
                }
                for item in previous
            ],
            "hints": {
                "cites": citations,
                "addressed_to": [
                    participant["id"]
                    for participant in roster
                    if participant["id"] != message["participantId"]
                    and any(
                        name and len(name) >= 3 and name.lower() in message["text"].lower()
                        for name in (participant["sender"], participant["instance"])
                    )
                ],
                "artifacts": list(dict.fromkeys(re.findall(
                    r"\b(?:art|shr|run|tool|file)_[A-Za-z0-9_-]+\b", message["text"]
                ))),
                "heartbeat": bool(re.match(
                    r"^\s*(?:heartbeat|ping|still working|working on it|status update|no update)\b",
                    message["text"], re.I,
                )),
            },
        }
        messages.append(
            ChatMessageAssistant(
                content=message["text"],
                metadata={
                    "participant_id": message["participantId"],
                    "sender": message["sender"],
                    "instance": message["instance"],
                    "runtime": message["runtime"],
                    "sequence": message["index"],
                    "timestamp": message["timestamp"],
                    "words": message["words"],
                    "questions": message["questions"],
                    "signals": message["signals"],
                    "annotation_context": context,
                    "role_label": f"AGENT {message['participantId']}",
                },
            )
        )

    return Transcript(
        transcript_id=report["traceId"],
        source_type=report["source"].get("kind") or "sharednet",
        source_id=report["traceId"],
        source_uri=report["source"].get("url"),
        date=report["conversation"]["firstTimestamp"],
        task_set="sharednet-conversation",
        task_id=report["traceId"],
        agent="multi-agent-room",
        message_count=len(messages),
        total_time=report["metrics"]["durationMs"] / 1000 if report["metrics"]["durationMs"] is not None else None,
        messages=messages,
        metadata={
            "agenttrace_schema_version": report["schemaVersion"],
            "title": report["conversation"]["title"],
            "participants": report["participants"],
            "metrics": report["metrics"],
            "transitions": report["transitions"],
            "structural_flags": report["failureModes"],
        },
    )
