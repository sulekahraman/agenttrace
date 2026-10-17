import asyncio
import json
from pathlib import Path

import pytest
pytest.importorskip("inspect_scout")
from commsfail.sources.sharednet import from_share
from inspect_ai.model import ModelOutput

from agenttrace.scout.adapter import transcript_from_report
from agenttrace.scout.scanners import analyze_collaboration
from agenttrace.scout.annotations import annotate_messages
from agenttrace.view_model import build_view_model


def test_adapter_has_bounded_past_only_context(share):
    share["messages"][2]["content"] = "Qi, review #1 and art_example."
    transcript = transcript_from_report(build_view_model(from_share(share, {"kind": "share"})))
    context = transcript.messages[2].metadata["annotation_context"]
    assert context["hints"]["cites"] == [1]
    assert context["hints"]["artifacts"] == ["art_example"]
    assert all(item["index"] < 3 for item in context["previous_messages"])
    assert len(context["roster"]) == 2


def test_standalone_scanner_files_are_discoverable():
    from inspect_scout._scanner.scanner import scanners_from_file

    root = Path(__file__).resolve().parents[3]
    for filename in ("scanners.py", "message_annotations.py"):
        assert len(scanners_from_file(str(root / "scout" / filename), {})) == 1


def mock_structured_generation(monkeypatch, invalid_reference=False, original_reference=1):
    from inspect_scout._llm_scanner import generate

    async def generate_structured(input, schema, **kwargs):
        # Exercise Scout's real schema construction and structured-result parser.
        assert schema.properties
        assert kwargs["model"] == "mockllm/model"
        assert kwargs["config"].cache is True
        if "TARGET MESSAGE TO LABEL" in input:
            data = {
                "primary_type": "delegation_request", "secondary_types": [],
                "replies_to": [], "addressed_to": [], "confidence": 0.8,
                "ambiguous": False, "rationale": "Requests review.", "evidence": [],
                "explanation": "Target-message annotation.",
            }
        else:
            data = {"results": [
                {"category": category, "found": category == "weak_handoff",
                 "explanation": "Candidate message [M1].", "confidence": 0.8,
                 "message_numbers": [999 if invalid_reference else original_reference] if category == "weak_handoff" else []}
                for category in ("duplicated_work", "weak_handoff", "unintegrated_information")
            ]}
        output = ModelOutput.from_content("mockllm/model", json.dumps(data))
        return data, [], output

    monkeypatch.setattr(generate, "structured_generate", generate_structured)


def test_real_scout_structured_output_and_artifacts(monkeypatch, share, tmp_path):
    mock_structured_generation(monkeypatch)
    transcript = transcript_from_report(build_view_model(from_share(share, {"kind": "share"})))
    result = asyncio.run(analyze_collaboration(transcript, model="mockllm/model", artifacts=tmp_path))
    assert len(result["findings"]) == 3
    assert result["findings"][1]["message_numbers"] == [1]
    assert len(result["annotations"]) == 3
    assert result["coverage"]["annotated_messages"] == 3
    assert (tmp_path / "message-1.prompt.txt").exists()
    assert (tmp_path / "collaboration.result.json").exists()


def test_scout_invalid_evidence_fails(monkeypatch, share):
    mock_structured_generation(monkeypatch, invalid_reference=True)
    transcript = transcript_from_report(build_view_model(from_share(share, {"kind": "share"})))
    with pytest.raises(ValueError, match="outside"):
        asyncio.run(analyze_collaboration(transcript, model="mockllm/model"))


def test_noncontiguous_original_numbers_are_mapped_explicitly(monkeypatch, share, tmp_path):
    mock_structured_generation(monkeypatch, original_reference=2)
    transcript = transcript_from_report(build_view_model(from_share(share, {"kind": "share"})))
    for sequence, message in zip((2, 4, 6), transcript.messages):
        message.metadata["sequence"] = sequence
    result = asyncio.run(analyze_collaboration(transcript, model="mockllm/model", artifacts=tmp_path))
    prompt = (tmp_path / "collaboration.prompt.txt").read_text()
    assert "CANDIDATE REFERENCE MAP:" in prompt
    assert "[M1] -> AgentTrace turn #2" in prompt
    assert "[M2] -> AgentTrace turn #4" in prompt
    assert "[M3] -> AgentTrace turn #6" in prompt
    assert "Allowed message_numbers: [2, 4, 6]" in prompt
    assert result["findings"][1]["message_numbers"] == [2]


def test_failed_annotation_cancels_other_model_calls(monkeypatch, share):
    from agenttrace.scout import annotations

    cancelled = []
    async def failing_annotation(message, **kwargs):
        if message.metadata["sequence"] == 1:
            await asyncio.sleep(0.01)
            raise ValueError("Invalid annotation")
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled.append(message.metadata["sequence"])
            raise

    monkeypatch.setattr(annotations, "annotate_message", failing_annotation)
    transcript = transcript_from_report(build_view_model(from_share(share, {"kind": "share"})))
    with pytest.raises(ValueError, match="Invalid annotation"):
        asyncio.run(annotate_messages(transcript.messages))
    assert sorted(cancelled) == [2, 3]
