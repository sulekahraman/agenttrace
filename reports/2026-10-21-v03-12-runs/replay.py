"""Prepare and validate saved session responses; never call a provider.

``direct --work WORK --slug SLUG`` reads direct-review-evidence.json,
direct-review.schema.json (Assessment), direct-review.reply.json, and
direct-review.prompt.txt. The last file is a reconstructed staged-read inventory
in shared parent context, not a submitted prompt; it must include the source
digest, either the packet file SHA-256 or exact packet JSON, and the words
reconstructed, staged and shared.
Selected packets preserve exact source events or indexed discovery summaries.
Coverage inherits the source coverage and records total_events, supplied_events,
omitted_events, truncated_events, retrieval_windows and retrieval_policy
``reviewer-selected-source-events``. Retained certificates must still contain
every required full event. Original search-A/B inputs and replies are reused.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from unittest.mock import patch

from inspect_scout import Result
from pydantic import TypeAdapter

from agenttrace.communication import analysis
from agenttrace.communication import PROMPT_VERSION, VERSION
from agenttrace.communication.evidence import digest, model_evidence, retrieve_evidence, window_bounds
from agenttrace.scout import annotations, scanners
from agenttrace.scout.adapter import transcript_from_report
from agenttrace.store import Store
from agenttrace.view_model import build_view_model

ROOT = Path(__file__).resolve().parents[2]
MODEL = "copilot-session/gpt-6.1-sol"
STAGES = ("search-A", "search-B", "A", "B", "judge")
PARENT_SESSION = "141c12e0-1ebe-4856-92f6-738fb99cce57"
DIRECT_METHOD = "direct single-session"
INDEPENDENT_METHOD = "independent A/B + judge"


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prompt(directory, tag, packet, records=""):
    instructions = (analysis.SEARCH_INSTRUCTIONS if tag.startswith("search-")
                    else analysis.JUDGE_INSTRUCTIONS if tag == "judge" else analysis.REVIEW_INSTRUCTIONS)
    text = analysis.PROMPT_TEMPLATE.format(
        rubric=analysis.RUBRIC, stage=tag, evidence=json.dumps(packet, ensure_ascii=False),
        instructions=instructions, records=records,
    )
    path = directory / f"{tag}.prompt.txt"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    schema = (analysis.EvidenceSearch if tag.startswith("search-")
              else analysis.Adjudication if tag == "judge" else analysis.Assessment)
    write(directory / f"{tag}.schema.json", schema.model_json_schema())
    return text


def prepare(work, source, viewer):
    if work.exists() or viewer.exists():
        raise ValueError("Replay or viewer destination exists; refusing to overwrite.")
    work.mkdir(parents=True, mode=0o700)
    viewer.mkdir(parents=True)
    with sqlite3.connect(f"file:{ROOT}/data/programbench-pr10/agenttrace.sqlite3?mode=ro", uri=True) as original:
        with sqlite3.connect(viewer / "agenttrace.sqlite3") as destination:
            original.backup(destination)
    store = Store(viewer)
    prior = read(source / "manifest.json")
    rows = []
    for item in prior["rows"]:
        slug = item["slug"]
        directory = work / slug
        directory.mkdir(mode=0o700)
        bundle = read(source / slug / "evidence.json")
        if digest({k: v for k, v in bundle.items() if k != "sha256"}) != item["evidence_sha256"]:
            raise ValueError(f"Frozen source hash mismatch: {slug}")
        write(directory / "evidence.json", bundle)
        store.save_evidence(item["trace_id"], bundle)
        report = build_view_model(store.get_trace(item["trace_id"]))
        write(directory / "report.input.json", report)
        messages = transcript_from_report(report).messages
        prompts = [
            {"message_number": message.metadata["sequence"], "prompt": annotations.build_annotation_prompt(message)}
            for message in messages
        ]
        write(directory / "message-prompts.json", prompts)
        write(directory / "annotation.schema.json", annotations.MessageAnnotation.model_json_schema())
        discovery = model_evidence(bundle)
        write(directory / "discovery-evidence.json", discovery)
        for tag in ("search-A", "search-B"):
            prompt(directory, tag, discovery)
        rows.append({
            "slug": slug, "trace_id": item["trace_id"], "messages": len(messages),
            "evidence_sha256": bundle["sha256"], "coverage": bundle["coverage"],
            "message_prompt_sha256": digest({"prompts": prompts}),
        })
    sources = [
        ROOT / "packages/agenttrace-api/agenttrace" / area / filename
        for area, filenames in (
            ("communication", ("__init__.py", "analysis.py", "evidence.py", "capture.py")),
            ("scout", ("__init__.py", "annotations.py", "scanners.py", "adapter.py")),
        ) for filename in filenames
    ]
    write(work / "manifest.json", {
        "model": MODEL, "execution": "copilot-session-prompt-replay", "direct_provider_api_calls": 0,
        "source_commit": prior["source_commit"], "communication_version": VERSION,
        "communication_prompt_version": PROMPT_VERSION,
        "source_code_sha256": {str(path.relative_to(ROOT)): sha(path) for path in sources},
        "rubric_sha256": hashlib.sha256(analysis.RUBRIC.encode()).hexdigest(),
        "scout_rerun": True, "rows": rows,
    })
    print(json.dumps([{"slug": r["slug"], "messages": r["messages"]} for r in rows]))


def check(work, slug, tag):
    directory = work / slug
    schema = (analysis.EvidenceSearch if tag.startswith("search-")
              else analysis.Adjudication if tag == "judge" else analysis.Assessment)
    result = schema.model_validate(read(directory / f"{tag}.reply.json"))
    if tag.startswith("search-"):
        discovery = read(directory / "discovery-evidence.json")
        index = {event["id"]: event for event in discovery["events"]}
        for window in result.windows:
            window_bounds(window.model_dump(), index)
        retrieve_evidence(read(directory / "evidence.json"), [w.model_dump() for w in result.windows])
    else:
        packet = read(directory / ("union-evidence.json" if tag == "judge" else f"{tag}-review-evidence.json"))
        analysis.validate_assessment(result, packet, require_reasons=True)
    print(f"{slug} {tag}: schema and evidence validation passed.")
    return result


def retrieve(work, slug):
    directory = work / slug
    bundle = read(directory / "evidence.json")
    plans = [check(work, slug, tag) for tag in ("search-A", "search-B")]
    windows = [w.model_dump() for plan in plans for w in plan.windows]
    union = retrieve_evidence(bundle, windows)
    write(directory / "union-evidence.json", union)
    for role, plan in zip(("A", "B"), plans):
        packet = retrieve_evidence(bundle, [w.model_dump() for w in plan.windows])
        write(directory / f"{role}-review-evidence.json", packet)
        prompt(directory, role, packet)
    print(f"{slug}: full independent packets and union ready; no clipping.")


def judge_prompt(work, slug):
    directory = work / slug
    records = {tag: check(work, slug, tag).model_dump(mode="json") for tag in ("A", "B")}
    prompt(directory, "judge", read(directory / "union-evidence.json"), json.dumps(records))
    print(f"{slug}: judge prompt ready.")


async def communication(work, slug):
    directory = work / slug
    bundle = frozen_source(work, slug)
    if read(directory / "discovery-evidence.json") != model_evidence(bundle):
        raise ValueError("Saved discovery packet diverges from the frozen source.")
    async def saved_generate(text, schema, model):
        tag = re.search(r"Independent step: ([^\n]+)", text).group(1)
        if text != (directory / f"{tag}.prompt.txt").read_text(encoding="utf-8"):
            raise ValueError(f"Session prompt diverged from native prompt: {slug} {tag}")
        if read(directory / f"{tag}.schema.json") != schema.model_json_schema():
            raise ValueError(f"Saved response schema diverged from native schema: {slug} {tag}")
        return schema.model_validate(read(directory / f"{tag}.reply.json"))
    with patch.object(analysis, "generate", saved_generate):
        output = await analysis.analyze(bundle, MODEL, directory / "native-validation")
    windows = []
    for role, plan in output["searches"].items():
        if read(directory / f"{role}-review-evidence.json") != retrieve_evidence(bundle, plan["windows"]):
            raise ValueError(f"Saved review packet differs from native retrieval: {slug} {role}")
        windows.extend(plan["windows"])
    if read(directory / "union-evidence.json") != retrieve_evidence(bundle, windows):
        raise ValueError(f"Saved union packet differs from native retrieval: {slug}")
    output["execution"]["count_basis"] = "Five saved session-stage responses validated; not provider calls or Copilot internal turns."
    write(directory / "communication.result.json", output)
    print(f"{slug}: all five saved responses passed the unmodified native v0.3 pipeline.")


def frozen_source(work, slug):
    bundle = read(work / slug / "evidence.json")
    manifest = read(work / "manifest.json")
    source = next(row for row in manifest["rows"] if row["slug"] == slug)
    if (bundle["sha256"] != source["evidence_sha256"]
            or digest({k: v for k, v in bundle.items() if k != "sha256"}) != bundle["sha256"]):
        raise ValueError("Review source digest diverges from the frozen manifest.")
    if hashlib.sha256(analysis.RUBRIC.encode()).hexdigest() != manifest["rubric_sha256"]:
        raise ValueError("Frozen rubric changed.")
    for name, expected in manifest["source_code_sha256"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"Frozen implementation changed: {name}")
    return bundle


def validated_packet(bundle, packet):
    """Reject altered source events or fabricated completeness certificates."""
    if digest({k: v for k, v in bundle.items() if k != "sha256"}) != bundle["sha256"]:
        raise ValueError("Frozen source evidence digest mismatch.")
    if packet["sha256"] != bundle["sha256"] or packet["schema"] != bundle["schema"]:
        raise ValueError("Review packet does not identify the frozen source.")
    if packet == model_evidence(bundle):
        return
    windows = [certificate["window"] for certificate in packet["coverage"].get("retrieval_windows", [])]
    if packet["coverage"].get("retrieval_policy") == "full-window-v1":
        if packet != retrieve_evidence(bundle, windows):
            raise ValueError("Review packet or completeness certificates differ from source retrieval.")
        return
    index = {event["id"]: event for event in bundle["events"]}
    discovery = {event["id"]: event for event in model_evidence(bundle)["events"]}
    ids = [event["id"] for event in packet["events"]]
    if len(set(ids)) != len(ids) or any(
        event["id"] not in index or (index[event["id"]] != event and discovery.get(event["id"]) != event)
        for event in packet["events"]
    ):
        raise ValueError("Selected events must be unique exact source events or exact indexed discovery summaries.")
    truncated = [event["id"] for event in packet["events"] if event["text"] != index[event["id"]]["text"]]
    certificates = packet["coverage"].get("retrieval_windows", [])
    for certificate in certificates:
        restored = retrieve_evidence(bundle, [certificate["window"]])["coverage"]["retrieval_windows"][0]
        if (certificate != restored or not set(certificate["required_events"]) <= set(ids)
                or set(certificate["required_events"]) & set(truncated)):
            raise ValueError("Retained completeness certificates must match source retrieval and contain all required full events.")
    coverage = packet["coverage"]
    omitted = [event["id"] for event in bundle["events"] if event["id"] not in set(ids)]
    if any(
        not isinstance(coverage.get(key), list)
        or len(coverage[key]) != len(set(coverage[key]))
        or set(coverage[key]) != set(expected_ids)
        for key, expected_ids in (("omitted_events", omitted), ("truncated_events", truncated))
    ):
        raise ValueError("Selected-event omission/shortening IDs must exactly match the source.")
    policy = coverage.get("retrieval_policy")
    if policy not in ("reviewer-selected-source-events", "direct-parent-selected-exact-source-events"):
        raise ValueError("Unrecognized reviewer-selected source-event policy.")
    if policy == "direct-parent-selected-exact-source-events" and any(index[event["id"]] != event for event in packet["events"]):
        raise ValueError("Exact-source selection policy cannot include shortened discovery summaries.")
    expected = {
        **bundle["coverage"], "total_events": len(index), "supplied_events": len(ids),
        "omitted_events": coverage["omitted_events"],
        "truncated_events": coverage["truncated_events"], "retrieval_windows": certificates,
        "retrieval_policy": policy,
    }
    if "input_text_limit" in coverage:
        from agenttrace.communication.evidence import REVIEW_TEXT_LIMIT
        expected["input_text_limit"] = REVIEW_TEXT_LIMIT
    if packet["coverage"] != expected:
        raise ValueError("Selected-event coverage must record exact omissions/shortening and only validated complete windows.")


def validate_direct_inventory(text, bundle, packet_sha256, packet=None):
    """Bind the reconstructed inventory to saved inputs, not a fictitious prompt."""
    bound = packet_sha256 in text
    if not bound and packet is not None:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                value, _ = decoder.raw_decode(text, match.start())
            except ValueError:
                continue
            if value == packet:
                bound = True
                break
    if (bundle["sha256"] not in text or not bound
            or any(word not in text.casefold() for word in ("reconstructed", "staged", "shared"))):
        raise ValueError(
            "Direct inventory must contain the source sha256 and packet file sha256 or exact packet JSON and disclose "
            "'reconstructed', 'staged' reads, and 'shared' parent context; it is not a submitted prompt."
        )


async def direct(work, slug):
    directory = work / slug
    bundle = frozen_source(work, slug)
    packet = read(directory / "direct-review-evidence.json")
    validated_packet(bundle, packet)
    if read(directory / "direct-review.schema.json") != analysis.Assessment.model_json_schema():
        raise ValueError("Direct review schema must be the exact Assessment schema.")
    text = (directory / "direct-review.prompt.txt").read_text(encoding="utf-8")
    packet_sha256 = sha(directory / "direct-review-evidence.json")
    validate_direct_inventory(text, bundle, packet_sha256, packet)
    searches = {}
    discovery = model_evidence(bundle)
    if read(directory / "discovery-evidence.json") != discovery:
        raise ValueError("Saved search discovery packet diverges from the frozen source.")
    for tag in ("search-A", "search-B"):
        expected_search = analysis.PROMPT_TEMPLATE.format(
            rubric=analysis.RUBRIC, stage=tag, evidence=json.dumps(discovery, ensure_ascii=False),
            instructions=analysis.SEARCH_INSTRUCTIONS, records="",
        )
        if ((directory / f"{tag}.prompt.txt").read_text(encoding="utf-8") != expected_search
                or read(directory / f"{tag}.schema.json") != analysis.EvidenceSearch.model_json_schema()):
            raise ValueError(f"Saved search prompt/schema diverges: {tag}")
        searches[tag.removeprefix("search-")] = check(work, slug, tag).model_dump(mode="json")
    assessment = analysis.Assessment.model_validate(read(directory / "direct-review.reply.json"))
    analysis.validate_assessment(assessment, packet, require_reasons=True)
    output = {
        "schema": "agenttrace/communication-analysis.v1", "taxonomy_version": analysis.TAXONOMY_VERSION,
        "experimental": True, **assessment.model_dump(mode="json"),
        "coverage": packet["coverage"], "evidence_sha256": bundle["sha256"],
        "evidence": packet["events"], "annotations": {}, "searches": searches,
        "direct_assessment": assessment.model_dump(mode="json"), "method": DIRECT_METHOD,
        "protocol": {
            "kind": "direct-session-assessment", "reviewer_session": PARENT_SESSION,
            "shared_context": True, "independent_ab": False, "judge": False,
            "saved_searches_reused": ["search-A", "search-B"],
            "prior_review_proposals_used": False,
            "packet_sha256": packet_sha256,
            "input_record_kind": "reconstructed application input inventory",
            "input_presentation": "staged reads in existing shared parent context, not a separately submitted model prompt",
            "inspection_scope": "All non-goal communication posts, indexed command/receipt discovery, and selected fully inspected source events only; omitted details were not retrieved.",
            "omitted_detail_reason": "evidence_not_retrieved",
            "independent_robustness_comparable": False,
            "input_selection": packet.get("direct_review", {}),
        },
        "execution": {
            "generation_attempts": 3,
            "calls": [
                {"stage": tag, "attempt": 1, "status": "validated", "operation": "saved-response-validation"}
                for tag in ("search-A", "search-B", "direct-review")
            ],
            "inference_calls": 0, "saved_responses_validated": 3,
            "direct_assessments": 1, "reused_search_responses": 2,
            "independent_review_responses": 0, "judge_responses": 0,
            "count_basis": "Direct session assessment, no independent A/B or judge; saved-response validation not inference calls. Two prior search responses reused; one parent-session Assessment validated.",
        },
        "caveats": [
            "Direct parent-session judgment in shared context, not an independent A/B review or adjudication.",
            "Prior surviving review proposals are archived as attempts, not used for direct decisions.",
            "Validation verifies structure, source consistency, citations and scopes, not semantic correctness.",
            "No is scoped; unknown is not No. Breakdown and downstream impact are separate.",
            "Source-complete retrieval windows differ from reviewer-selected events without completeness certificates.",
            "direct-review.prompt.txt is a reconstructed inventory of staged reads in the existing shared parent context, not a separately submitted independent model prompt. It cannot reconstruct the complete parent conversation.",
            "Only supplied posts, discovery summaries and selected full source events were inspected; no claim is made that the whole union or full trace was reviewed. Omitted source details are evidence_not_retrieved, not missing_source_evidence.",
        ],
    }
    write(directory / "communication.result.json", output)
    print(f"{slug}: direct parent-session Assessment and two reused searches validated; no independent A/B or judge.")


async def scout(work, slug):
    directory = work / slug
    messages = transcript_from_report(read(directory / "report.input.json")).messages
    prompts = [
        {"message_number": message.metadata["sequence"], "prompt": annotations.build_annotation_prompt(message)}
        for message in messages
    ]
    source = next(row for row in read(work / "manifest.json")["rows"] if row["slug"] == slug)
    if (read(directory / "message-prompts.json") != prompts
            or digest({"prompts": prompts}) != source["message_prompt_sha256"]
            or read(directory / "annotation.schema.json") != annotations.MessageAnnotation.model_json_schema()):
        raise ValueError("Saved Scout prompts/schema diverge from the frozen inputs.")
    expected = {m.metadata["sequence"]: m for m in messages}
    values = read(directory / "annotations.reply.json")
    if len(values) != len(expected) or {v["message_number"] for v in values} != set(expected):
        raise ValueError("Need exactly one annotation for every target message.")
    parsed = {}
    for value in values:
        number = value["message_number"]
        message = expected[number]
        payload = {k: v for k, v in value.items() if k != "message_number"}
        if set(payload) - set(annotations.MessageAnnotation.model_fields):
            raise ValueError(f"Unknown annotation fields: {number}")
        annotation = annotations.MessageAnnotation.model_validate(payload)
        context = message.metadata["annotation_context"]
        roster = {a["id"] for a in context["roster"]}
        previous = {m["index"] for m in context["previous_messages"] + context["cited_messages"]}
        if (not set(annotation.addressed_to) <= roster or not set(annotation.replies_to) <= previous
                or any(n >= number for n in annotation.replies_to)
                or any(e.text not in message.text for e in annotation.evidence)
                or annotation.primary_type in annotation.secondary_types):
            raise ValueError(f"Invalid annotation roster, reply or verbatim target evidence: {number}")
        parsed[number] = annotation
    async def annotation_generate(text, *args, **kwargs):
        number = int(re.search(r"TARGET MESSAGE TO LABEL:\n#(\d+)", text).group(1))
        return Result(value=True, parsed=parsed[number])
    async def collaboration_generate(text, *args, **kwargs):
        prompt_path = directory / "collaboration.prompt.txt"
        if prompt_path.exists() and prompt_path.read_text(encoding="utf-8") != text:
            raise ValueError("Saved Scout collaboration prompt diverges from native prompt.")
        prompt_path.write_text(text, encoding="utf-8")
        schema = TypeAdapter(list[scanners.CollaborationFinding])
        schema_path = directory / "collaboration.schema.json"
        if schema_path.exists() and read(schema_path) != schema.json_schema():
            raise ValueError("Saved Scout collaboration schema diverges from native schema.")
        write(directory / "collaboration.schema.json", schema.json_schema())
        path = directory / "collaboration.reply.json"
        if not path.exists():
            raise RuntimeError("ANNOTATIONS VALID: read collaboration.prompt.txt and produce collaboration.reply.json next.")
        return Result(value=True, parsed=schema.validate_python(read(path)))
    artifacts = directory / "scout-validation"
    artifacts.mkdir(exist_ok=True)
    with patch.object(annotations, "generate_answer", annotation_generate), patch.object(scanners, "generate_answer", collaboration_generate):
        output = await scanners.analyze_collaboration(
            transcript_from_report(read(directory / "report.input.json")), model=MODEL, artifacts=artifacts,
        )
    write(directory / "scout.result.json", output)
    print(f"{slug}: {len(parsed)} fresh annotations and all three Scout flags validated.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "check", "retrieve", "judge", "communication", "direct", "scout"])
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--viewer", type=Path)
    parser.add_argument("--slug")
    parser.add_argument("--tag")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.work, args.source, args.viewer)
    elif args.command == "check":
        check(args.work, args.slug, args.tag)
    elif args.command == "retrieve":
        retrieve(args.work, args.slug)
    elif args.command == "judge":
        judge_prompt(args.work, args.slug)
    else:
        asyncio.run(globals()[args.command](args.work, args.slug))


if __name__ == "__main__":
    main()
