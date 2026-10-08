import argparse
import asyncio
import json
from pathlib import Path
from typing import AsyncIterator

from inspect_ai.model import ChatMessageAssistant
from inspect_scout import Transcript, transcripts_db


def load_bridge(path: Path) -> dict:
    with path.open(encoding="utf-8") as file:
        bridge = json.load(file)

    if bridge.get("bridgeVersion") != "1.0":
        raise ValueError("Unsupported TraceScope Scout bridge version.")
    if not bridge.get("transcript_id") or not bridge.get("messages"):
        raise ValueError("The bridge file must contain transcript_id and messages.")
    return bridge


def format_message(message: dict) -> ChatMessageAssistant:
    metadata = message.get("metadata") or {}
    participant = metadata.get("participant_id", "unknown-agent")
    return ChatMessageAssistant(
        content=message.get("content", ""),
        metadata={
            **metadata,
            "role_label": f"AGENT {participant}",
        },
    )


async def transcript_source(bridge: dict) -> AsyncIterator[Transcript]:
    yield Transcript(
        transcript_id=bridge["transcript_id"],
        source_type=bridge.get("source_type"),
        source_id=bridge.get("source_id"),
        source_uri=bridge.get("source_uri"),
        date=bridge.get("date"),
        task_set=bridge.get("task_set"),
        task_id=bridge.get("task_id"),
        agent=bridge.get("agent"),
        message_count=bridge.get("message_count"),
        total_time=bridge.get("total_time"),
        messages=[format_message(message) for message in bridge["messages"]],
        metadata=bridge.get("metadata") or {},
    )


async def import_transcript(input_path: Path, output_path: Path) -> None:
    bridge = load_bridge(input_path)
    async with transcripts_db(str(output_path)) as database:
        await database.insert(transcript_source(bridge))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a TraceScope Scout bridge file into an Inspect Scout transcript database."
    )
    parser.add_argument("input", type=Path, help="TraceScope Scout bridge JSON file")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./transcripts"),
        help="Local Scout transcript database directory (default: ./transcripts)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(import_transcript(arguments.input, arguments.output))
