from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from statistics import median
from typing import Any

from commsfail import Trace
import regex

SIGNALS = {
    "agreement": re.compile(r"\b(agree|agreed|accept|accepted|correct|good point|makes sense|yes)\b", re.I),
    "challenge": re.compile(r"\b(disagree|however|but|concern|issue|problem|wrong|fail(?:ed|ure)?|critique|attack)\b", re.I),
    "coordination": re.compile(r"\b(please|could you|can you|need your|next step|action item|follow[- ]?up|owner|assign)\b", re.I),
}
WORD_RE = regex.compile(r"[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*")
LINK_RE = re.compile(r"https?://\S+")
CODE_RE = re.compile(r"```[\s\S]*?```|`[^`\n]+`")


def _round(value: float, digits: int = 1) -> float:
    factor = 10**digits
    return math.floor(value * factor + 0.5) / factor


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Invalid trace timestamp: {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Trace timestamps must include a timezone.")
        return parsed
    except ValueError:
        raise ValueError(f"Invalid trace timestamp: {value!r}") from None


def _gini(values: list[int]) -> float:
    if not values or all(value == 0 for value in values):
        return 0
    ordered = sorted(values)
    total = sum(ordered)
    weighted = sum((index + 1) * value for index, value in enumerate(ordered))
    return (2 * weighted) / (len(ordered) * total) - (len(ordered) + 1) / len(ordered)


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _participant_id(seat: dict[str, Any] | None, handle: str) -> str:
    if not seat:
        return handle
    label = seat.get("label")
    return f"{label} {handle}" if label and label != handle else handle


def _messages(trace: Trace) -> list[dict[str, Any]]:
    seats = {seat.get("handle"): seat for seat in trace.seats}
    messages = []
    for post in trace.posts:
        if (post.get("type") or "message") != "message":
            continue
        if post.get("role") in ("goal", "runner"):
            continue
        handle = post.get("who") or "unknown-agent"
        seat = seats.get(handle)
        text = post.get("text") or ""
        messages.append(
            {
                "index": int(post.get("seq") or len(messages) + 1),
                "participantId": _participant_id(seat, handle),
                "sender": (seat or {}).get("label") or handle,
                "instance": handle,
                "runtime": (seat or {}).get("driver") or (seat or {}).get("model") or "unknown",
                "timestamp": post.get("created_at"),
                "text": text,
                "links": len(LINK_RE.findall(text)),
                "codeBlocks": len(CODE_RE.findall(text)),
                "words": len(WORD_RE.findall(text)),
                "characters": len(text.encode("utf-16-le")) // 2,
                "questions": text.count("?"),
                "signals": {
                    name: len(pattern.findall(text))
                    for name, pattern in SIGNALS.items()
                },
            }
        )
    if not messages:
        raise ValueError("The trace does not contain any agent messages.")
    messages.sort(key=lambda message: message["index"])
    indexes = [message["index"] for message in messages]
    if any(index <= 0 for index in indexes) or len(set(indexes)) != len(indexes):
        raise ValueError("Agent message sequence numbers must be unique positive integers.")
    return messages


def _participants(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    participants: dict[str, dict[str, Any]] = {}
    for message in messages:
        participant_id = message["participantId"]
        current = participants.setdefault(
            participant_id,
            {
                "id": participant_id,
                "sender": message["sender"],
                "instance": message["instance"],
                "runtime": message["runtime"],
                "messages": 0,
                "words": 0,
                "questions": 0,
                "agreement": 0,
                "challenge": 0,
                "coordination": 0,
            },
        )
        current["messages"] += 1
        current["words"] += message["words"]
        current["questions"] += message["questions"]
        for signal, count in message["signals"].items():
            current[signal] += count
    return sorted(participants.values(), key=lambda item: (-item["messages"], -item["words"]))


def _transitions(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    switches = 0
    for previous, current in zip(messages, messages[1:]):
        source = previous["participantId"]
        target = current["participantId"]
        if source == target:
            continue
        switches += 1
        edge = edges.setdefault((source, target), {"source": source, "target": target, "count": 0})
        edge["count"] += 1
    return sorted(edges.values(), key=lambda edge: -edge["count"]), switches


def _failure_modes(
    metrics: dict[str, Any],
    participants: list[dict[str, Any]],
    transitions: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flags = []
    total_messages = metrics["totalMessages"] or 1
    top = participants[0] if participants else None
    possible_edges = len(participants) * max(len(participants) - 1, 1)
    density = len(transitions) / possible_edges if possible_edges else 0
    challenge_count = sum(message["signals"]["challenge"] for message in messages)
    agreement_count = sum(message["signals"]["agreement"] for message in messages)

    if top and top["messages"] / total_messages >= 0.4:
        flags.append(
            {
                "id": "dominance",
                "severity": "high",
                "title": "Contribution dominance",
                "detail": f"{top['id']} produced {_round(top['messages'] / total_messages * 100)}% of all messages.",
                "threshold": "Triggered when one agent produces at least 40% of messages.",
                "evidence": "A high share can indicate coordinator bottlenecks or weak participation.",
            }
        )
    if len(participants) > 2 and density < 0.35:
        flags.append(
            {
                "id": "siloing",
                "severity": "high" if density < 0.2 else "medium",
                "title": "Sparse transition matrix",
                "detail": f"Only {_round(density * 100)}% of possible directed agent transitions occurred.",
                "threshold": "Triggered when fewer than 35% of possible directed transitions occur.",
                "evidence": "Some agents may be communicating through a hub rather than with each other.",
            }
        )
    if metrics["questionFollowUpRate"] < 0.6 and metrics["questionMessages"] >= 5:
        flags.append(
            {
                "id": "unresolved-questions",
                "severity": "medium",
                "title": "Questions may be going unresolved",
                "detail": f"{_round((1 - metrics['questionFollowUpRate']) * 100)}% of question messages had no other-agent reply within three turns.",
                "threshold": "Triggered when at least five question messages exist and fewer than 60% receive a near-term follow-up.",
                "evidence": "This is a turn-taking proxy; it does not judge whether a reply actually answered the question.",
            }
        )
    if challenge_count > agreement_count * 1.5 and challenge_count >= 10:
        flags.append(
            {
                "id": "conflict",
                "severity": "medium",
                "title": "Challenge-heavy discourse",
                "detail": f"{challenge_count} challenge markers versus {agreement_count} agreement markers.",
                "threshold": "Triggered at 10 or more challenge markers and 1.5 times the agreement-marker count.",
                "evidence": "Productive critique and unproductive conflict cannot be separated without semantic evaluation.",
            }
        )
    if metrics["p95WordsPerMessage"] >= 900:
        flags.append(
            {
                "id": "context-load",
                "severity": "medium",
                "title": "High context load",
                "detail": f"The 95th percentile message is {metrics['p95WordsPerMessage']} words.",
                "threshold": "Triggered when the 95th percentile message length is at least 900 words.",
                "evidence": "Long messages can hide decisions and increase context-window and attribution errors.",
            }
        )
    if not flags:
        flags.append(
            {
                "id": "none",
                "severity": "low",
                "title": "No strong structural flag",
                "detail": "The deterministic thresholds did not identify a strong failure-mode signal.",
                "threshold": "No configured threshold was crossed.",
                "evidence": "This does not imply the collaboration was successful; inspect the transcript and task outcome.",
            }
        )
    return flags


def trace_id(trace: Trace) -> str:
    content = trace.to_dict()
    content["source"] = {
        key: value for key, value in trace.source.items()
        if key not in ("loaded_at", "fetched_at")
    }
    identity = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return f"trace_{hashlib.sha256(identity.encode()).hexdigest()[:16]}"


def build_view_model(trace: Trace, analyses: dict[str, Any] | None = None) -> dict[str, Any]:
    messages = _messages(trace)
    goal = trace.episode.get("goal")
    description = goal if isinstance(goal, str) else next(
        (post.get("text") for post in trace.posts if post.get("role") == "goal"),
        None,
    )
    participants = _participants(messages)
    transitions, switches = _transitions(messages)
    first_time = next((message["timestamp"] for message in messages if message["timestamp"]), None)
    last_time = next((message["timestamp"] for message in reversed(messages) if message["timestamp"]), None)
    parsed_times = [_parse_time(message["timestamp"]) for message in messages]
    first_dt = next((value for value in parsed_times if value is not None), None)
    last_dt = next((value for value in reversed(parsed_times) if value is not None), None)
    duration_ms = max(0, int((last_dt - first_dt).total_seconds() * 1000)) if first_dt and last_dt else None
    latencies = []
    question_messages = 0
    followed_questions = 0

    for index, message in enumerate(messages):
        if message["questions"] > 0:
            question_messages += 1
            if any(
                candidate["participantId"] != message["participantId"]
                for candidate in messages[index + 1 : index + 4]
            ):
                followed_questions += 1
        if index and message["participantId"] != messages[index - 1]["participantId"]:
            previous_dt = parsed_times[index - 1]
            current_dt = parsed_times[index]
            if previous_dt and current_dt:
                latency = int((current_dt - previous_dt).total_seconds() * 1000)
                if latency >= 0:
                    latencies.append(latency)

    total_words = sum(message["words"] for message in messages)
    metrics = {
        "totalMessages": len(messages),
        "participantCount": len(participants),
        "totalWords": total_words,
        "averageWordsPerMessage": _round(total_words / len(messages)),
        "p95WordsPerMessage": _percentile([message["words"] for message in messages], 0.95),
        "durationMs": duration_ms,
        "contributionBalance": _round((1 - _gini([participant["messages"] for participant in participants])) * 100),
        "turnSwitchRate": _round(switches / (len(messages) - 1) * 100) if len(messages) > 1 else 0,
        "medianResponseLatencyMs": median(latencies) if latencies else None,
        "questionMessages": question_messages,
        "questionFollowUpRate": followed_questions / question_messages if question_messages else 1,
        "links": sum(message["links"] for message in messages),
        "codeBlocks": sum(message["codeBlocks"] for message in messages),
    }
    return {
        "schemaVersion": "2.0",
        "traceId": trace_id(trace),
        "source": {
            "provider": "sharednet",
            **trace.source,
        },
        "conversation": {
            "title": trace.room.get("name") or "Untitled conversation",
            "description": description,
            "firstTimestamp": first_time,
            "lastTimestamp": last_time,
        },
        "metrics": metrics,
        "participants": participants,
        "transitions": transitions,
        "failureModes": _failure_modes(metrics, participants, transitions, messages),
        "messages": messages,
        "analyses": analyses or {},
    }
