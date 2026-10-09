"""Plugin discovery: an entry point becomes a registered annotator or source; a broken one is skipped, not fatal."""
import warnings
from importlib.metadata import EntryPoint
from pathlib import Path
import pytest
import commsfail._plugins as plugins
from commsfail import annotators, sources
from commsfail.annotators import check_annotator, validate_output

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "plugin"

def _entry_points(*eps):
    return lambda group: [ep for ep in eps if ep.group == group]

def test_example_plugin_registers_an_annotator_and_a_source(monkeypatch, synthetic_trace):
    monkeypatch.syspath_prepend(str(EXAMPLE))
    monkeypatch.setattr(plugins, "entry_points", _entry_points(
        EntryPoint("example_v1", "commsfail_example:ExampleV1", annotators.ENTRY_POINT_GROUP),
        EntryPoint("chat_jsonl", "commsfail_example:load_chat_jsonl", sources.ENTRY_POINT_GROUP)))
    reg = annotators.discover()
    assert set(reg) >= {"regex_v1", "example_v1"}
    cls = reg["example_v1"]
    assert check_annotator(cls) == [] and annotators.origin(cls) == "commsfail_example"
    assert validate_output(cls, cls().annotate(synthetic_trace)) == []
    src = sources.discover()
    assert {"sharednet", "chat_jsonl"} <= set(src)
    trace = src["chat_jsonl"](str(EXAMPLE / "sample_chat.jsonl"))
    assert trace.source["kind"] == "chat-jsonl" and [p["seq"] for p in trace.posts] == [1, 2, 3, 4, 5]
    out = cls().annotate(trace)
    assert validate_output(cls, out) == [] and out["ends_on_question"] is True
    assert validate_output(reg["regex_v1"], reg["regex_v1"]().annotate(trace)) == []

def test_a_broken_plugin_is_skipped_with_a_warning(monkeypatch):
    monkeypatch.setattr(plugins, "entry_points", _entry_points(
        EntryPoint("broken", "no_such_module_for_commsfail:Nope", annotators.ENTRY_POINT_GROUP)))
    with pytest.warns(RuntimeWarning, match="broken"):
        reg = annotators.discover()
    assert set(reg) == set(annotators.builtin())

def test_a_plugin_class_is_keyed_by_its_own_name(monkeypatch):
    monkeypatch.setattr(plugins, "entry_points", _entry_points(
        EntryPoint("whatever", "commsfail.annotators.regex_v1:RegexV1", annotators.ENTRY_POINT_GROUP)))
    with warnings.catch_warnings():
        warnings.simplefilter("error")          # the same class under its own name is not a replacement
        reg = annotators.discover()
    assert set(reg) == set(annotators.builtin())
