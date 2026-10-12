from commsfail.sources.sharednet import from_share
import json
from pathlib import Path
import pytest
from commsfail import Trace, run, validate_record

from agenttrace.view_model import build_view_model


def sample_trace():
    return from_share(
        {
            "room": {"name": "Test room", "created_at": "2026-01-01T00:00:00Z"},
            "members": [
                {"handle": "AAAA", "label": "Researcher", "driver": "claude-code"},
                {"handle": "BBBB", "label": "Reviewer", "driver": "codex"},
            ],
            "messages": [
                {
                    "sequence": 1,
                    "content": "Could you verify this result?",
                    "created_at": "2026-01-01T00:00:00Z",
                    "sender": {"handle": "AAAA"},
                },
                {
                    "sequence": 2,
                    "content": "Yes, but there is one issue.",
                    "created_at": "2026-01-01T00:02:00Z",
                    "sender": {"handle": "BBBB"},
                },
                {
                    "sequence": 3,
                    "content": "Agreed. I will follow up.",
                    "created_at": "2026-01-01T00:05:00Z",
                    "sender": {"handle": "AAAA"},
                },
            ],
        },
        {"kind": "share-file", "path": "fixture.json", "room_id": None},
    )


def test_builds_existing_ui_contract():
    report = build_view_model(sample_trace())

    assert report["schemaVersion"] == "2.0"
    assert report["conversation"]["title"] == "Test room"
    assert report["metrics"]["totalMessages"] == 3
    assert report["metrics"]["participantCount"] == 2
    assert report["metrics"]["turnSwitchRate"] == 100
    assert report["metrics"]["medianResponseLatencyMs"] == 150_000
    assert report["metrics"]["questionFollowUpRate"] == 1
    assert report["participants"][0]["messages"] == 2
    assert report["messages"][1]["signals"]["challenge"] == 2


def test_matches_frozen_javascript_baseline():
    expected = json.loads(
        (Path(__file__).resolve().parents[3] / "fixtures/legacy-report.json").read_text()
    )
    actual = build_view_model(sample_trace())
    for key in expected:
        assert actual[key] == expected[key], key


def simple_trace(texts, authors=None):
    authors = authors or ["a"] * len(texts)
    return Trace(
        room={"name": "Threshold fixture"}, seats=[],
        posts=[{"seq": index + 1, "who": who, "text": text, "created_at": None}
               for index, (who, text) in enumerate(zip(authors, texts))],
        source={"kind": "share-file"},
    )


def test_unicode_words_and_original_utf16_character_count():
    report = build_view_model(simple_trace(["agent's multi-agent café 中文 123 _ 😀"]))
    assert report["messages"][0]["words"] == 5
    assert report["messages"][0]["characters"] == 36


def test_dominance_threshold():
    for dominant_count in (3, 4):
        authors = ["a"] * dominant_count + ["b", "c", "d", "e", "f", "g", "h"][:10 - dominant_count]
        modes = build_view_model(simple_trace(["hello"] * 10, authors))["failureModes"]
        assert any(mode["id"] == "dominance" for mode in modes) == (dominant_count == 4)


def test_question_and_context_thresholds():
    report = build_view_model(simple_trace(["question?"] * 5 + ["word " * 900]))
    assert report["metrics"]["questionFollowUpRate"] == 0
    assert {mode["id"] for mode in report["failureModes"]} >= {"unresolved-questions", "context-load"}
    below = build_view_model(simple_trace(["question?"] * 4 + ["word " * 899]))
    assert not {"unresolved-questions", "context-load"} & {mode["id"] for mode in below["failureModes"]}


def test_plugin_is_registered_and_valid():
    record = run("agenttrace_heuristics_v1", sample_trace())
    assert validate_record(record) == []
    assert record["output"]["metrics"]["totalMessages"] == 3


def test_duplicate_sequence_and_invalid_timestamp_rejected():
    trace = sample_trace()
    trace.posts[1]["seq"] = trace.posts[0]["seq"]
    with pytest.raises(ValueError, match="sequence"):
        build_view_model(trace)
    trace = sample_trace()
    trace.posts[0]["created_at"] = "wrong"
    with pytest.raises(ValueError, match="timestamp"):
        build_view_model(trace)
    trace = simple_trace(["one", "two", "three"])
    trace.posts[1]["created_at"] = "wrong"
    with pytest.raises(ValueError, match="timestamp"):
        build_view_model(trace)


def test_original_sequence_numbers_survive_excluded_runner_posts():
    trace = simple_trace(["one", "runner", "three"], ["a", "runner", "b"])
    trace.posts[1]["role"] = "runner"
    report = build_view_model(trace)
    assert [message["index"] for message in report["messages"]] == [1, 3]
    assert report["metrics"]["totalMessages"] == 2
    assert report["metrics"]["turnSwitchRate"] == 100
