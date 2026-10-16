"""Export saved AgentTrace judgments for Scout View without model generation."""

import asyncio
import base64
import json
import re
from pathlib import Path

from inspect_ai.model import ChatMessageAssistant
from inspect_scout import Reference, Result, Scanner, ScanJob, Transcript, columns
from inspect_scout import scan, scanner, transcripts_db, transcripts_from

from agenttrace.batch import save_json
from agenttrace.scout.adapter import transcript_from_report
from agenttrace.scout.annotations import MessageAnnotation
from agenttrace.scout.scanners import _candidate_messages, _candidate_positions

EXPORT_VERSION = 2


def native_viewer_url(export: dict, base_url: str) -> str:
    location = Path(export["location"]).resolve()
    directory = base64.urlsafe_b64encode(location.parent.as_uri().encode()).decode().rstrip("=")
    return f"{base_url}/#/scan/{directory}/{location.name}"


def saved_results(transcript: Transcript, output: dict) -> tuple[list[Result], list[Result]]:
    messages = {
        int(message.metadata["sequence"]): message
        for message in transcript.messages
        if isinstance(message, ChatMessageAssistant)
    }
    annotations = [
        (messages[row["message_number"]], MessageAnnotation.model_validate(row))
        for row in output["annotations"]
    ]
    if len(annotations) != len(messages) or {
        int(message.metadata["sequence"]) for message, _ in annotations
    } != set(messages):
        raise ValueError("Saved annotations must cover every transcript message exactly once.")
    positions = _candidate_positions(annotations) or set(messages)
    candidates = _candidate_messages(transcript, positions)
    candidate_labels = {
        int(message.metadata["sequence"]): f"M{position}"
        for position, message in enumerate(candidates, 1)
    }
    annotation_results = [
        Result(
            value=annotation.primary_type,
            label=f"Turn {message.metadata['sequence']}",
            explanation=annotation.rationale,
            metadata=annotation.model_dump(),
            references=[Reference(type="message", id=message.id)],
        )
        for message, annotation in annotations
    ]
    findings = [
        Result(
            value=finding["found"],
            label=finding["category"],
            explanation=finding["explanation"],
            metadata={
                "confidence": finding["confidence"],
                "message_numbers": finding["message_numbers"],
            },
            references=[
                Reference(type="message", id=messages[number].id, cite=candidate_labels[number])
                for number in finding["message_numbers"]
            ],
        )
        for finding in output["findings"]
    ]
    return annotation_results, findings


def _replay(results_file: str, field: str) -> Scanner[Transcript]:
    async def replay(transcript: Transcript) -> list[Result]:
        saved = json.loads(Path(results_file).read_text(encoding="utf-8"))
        if saved["trace_id"] != transcript.transcript_id:
            raise ValueError("Saved replay results belong to a different transcript.")
        return [Result.model_validate(result) for result in saved[field]]

    return replay


@scanner(messages="all", version=2)
def saved_message_annotations(results_file: str) -> Scanner[Transcript]:
    return _replay(results_file, "annotations")


@scanner(messages="all", version=2)
def saved_collaboration_findings(results_file: str) -> Scanner[Transcript]:
    return _replay(results_file, "findings")


def export_saved_run(report: dict, analysis: dict, root: Path) -> dict:
    if analysis["analyzer"]["name"] != "scout_collaboration_v1" or analysis["status"] != "completed":
        raise ValueError("Only completed Scout analyses can be exported.")
    if report["traceId"] != analysis["trace_id"]:
        raise ValueError("The saved analysis does not belong to this trace.")
    identifier = analysis["id"]
    if not re.fullmatch(r"run_[0-9a-f]{32}", identifier):
        raise ValueError("Invalid analysis run identifier.")
    root = root.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    manifest = root / "exports" / f"{identifier}.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        location = Path(saved["location"]).resolve()
        if (
            saved.get("export_version") == EXPORT_VERSION
            and location.is_relative_to(root / "scans")
            and location.is_dir()
        ):
            return saved

    transcript = transcript_from_report(report)
    for message in transcript.messages:
        message.id = f"{transcript.transcript_id}_m{message.metadata['sequence']}"
    annotation_results, findings = saved_results(transcript, analysis["output"])
    results_file = root / "replays" / f"{identifier}.json"
    save_json(results_file, {
        "trace_id": transcript.transcript_id,
        "annotations": [result.model_dump(mode="json") for result in annotation_results],
        "findings": [result.model_dump(mode="json") for result in findings],
    })

    async def insert():
        async with transcripts_db(str(root / "transcripts")) as database:
            await database.insert([transcript])

    asyncio.run(insert())
    scanners = {
        "saved_message_annotations": saved_message_annotations(str(results_file)),
        "saved_collaboration_findings": saved_collaboration_findings(str(results_file)),
    }
    status = scan(
        scanners=ScanJob(
            scanners=scanners,
            name=f"{report['conversation']['title']} (saved {identifier[-8:]})",
        ),
        transcripts=transcripts_from(str(root / "transcripts")).where(
            columns.transcript_id == transcript.transcript_id
        ),
        scans=str(root / "scans"),
        # These scanners only return saved judgments; the mock model never generates.
        model="mockllm/model",
        max_processes=1,
        display="none",
        fail_on_error=True,
        tags=["agenttrace", "saved-results"],
        metadata={
            "agenttrace_run_id": identifier,
            "original_analyzer": analysis["analyzer"],
            "original_provenance": analysis["provenance"],
            "export_kind": "saved-results-replay",
            "generation_logs_available": False,
        },
    )
    if not status.complete or status.errors:
        raise RuntimeError("Native Scout export did not complete successfully.")
    saved = {
        "export_version": EXPORT_VERSION,
        "run_id": identifier,
        "trace_id": transcript.transcript_id,
        "location": status.location,
    }
    save_json(manifest, saved)
    return saved
