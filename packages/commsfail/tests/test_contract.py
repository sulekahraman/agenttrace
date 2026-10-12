"""The contract. These tests run on every registered annotator, built in or plugin, and on every sample.

An annotator passes when it is well formed (name, version, a valid schema with $id, title and description),
its output conforms to its own schema on every sample, it gives the same output twice and leaves the trace
unchanged, it runs with the network cut, every "seq" it reports is a real post, and no token reaches its output.
An annotator with a taxonomy also passes when a built-in one names a choice in taxonomy-choices/, and every
pattern its output reports is in that taxonomy.
"""
import copy, json
from pathlib import Path
import pytest
from commsfail.annotators import (check_annotator, choices, origin, registry, run, taxonomy_of, validate_output,
                                  validate_record)
from commsfail.sources.sharednet import TOKEN_RE

NAMES = sorted(registry())

@pytest.mark.parametrize("name", NAMES)
def test_annotator_is_well_formed(name):
    cls = registry()[name]
    assert check_annotator(cls) == []
    if origin(cls) == "builtin":
        folder = Path(__import__(cls.__module__, fromlist=["_"]).__file__).parent
        assert folder.name == name
        for f in ("schema.json", "README.md"):
            assert (folder / f).is_file(), f"commsfail/annotators/{name}/{f} is missing"

@pytest.mark.parametrize("name", NAMES)
def test_output_conforms_to_its_own_schema(name, any_trace, no_network):
    out = registry()[name]().annotate(any_trace)
    assert validate_output(registry()[name], out) == []
    json.dumps(out, allow_nan=False)

@pytest.mark.parametrize("name", NAMES)
def test_same_output_twice_and_trace_unchanged(name, any_trace, no_network):
    before = copy.deepcopy(any_trace.to_dict())
    ann = registry()[name]()
    assert ann.annotate(any_trace) == ann.annotate(any_trace)
    assert any_trace.to_dict() == before, "annotate() must not change the trace"

def _seqs(x):
    if isinstance(x, dict):
        if isinstance(x.get("seq"), int) and not isinstance(x.get("seq"), bool):
            yield x["seq"]
        for v in x.values():
            yield from _seqs(v)
    elif isinstance(x, list):
        for v in x:
            yield from _seqs(v)

@pytest.mark.parametrize("name", NAMES)
def test_every_seq_is_a_real_post(name, any_trace, no_network):
    out = registry()[name]().annotate(any_trace)
    real = {p["seq"] for p in any_trace.posts} | {0}
    bad = sorted(set(_seqs(out)) - real)
    assert not bad, f"{name} points at posts that do not exist: {bad}"

@pytest.mark.parametrize("name", NAMES)
def test_no_token_in_the_output(name, any_trace, no_network):
    text = json.dumps(registry()[name]().annotate(any_trace), ensure_ascii=False)
    assert not TOKEN_RE.search(text), f"{name} copied a token into its output: pass excerpts through redact()"

@pytest.mark.parametrize("name", NAMES)
def test_record_round_trip(name, any_trace, no_network):
    rec = json.loads(json.dumps(run(registry()[name](), any_trace)))
    assert rec["annotator"]["name"] == name
    assert validate_record(rec) == []

WITH_TAXONOMY = sorted(n for n in NAMES if taxonomy_of(registry()[n]))

@pytest.mark.parametrize("name", [n for n in WITH_TAXONOMY if origin(registry()[n]) == "builtin"])
def test_a_builtin_annotator_names_a_choice_and_keeps_no_taxonomy_of_its_own(name):
    cls = registry()[name]
    assert cls.taxonomy in choices(), f"{name}: set taxonomy to one of {choices()}"
    folder = Path(__import__(cls.__module__, fromlist=["_"]).__file__).parent
    assert not (folder / "taxonomy.json").exists(), f"{name}: taxonomies live in taxonomy-choices/, not in the annotator"

@pytest.mark.parametrize("name", WITH_TAXONOMY)
def test_output_reports_only_modes_of_its_taxonomy(name, any_trace, no_network):
    ann = registry()[name]()
    ids = {m["id"] for m in taxonomy_of(ann)["modes"]}
    assert set(ann.modes_in(ann.annotate(any_trace))) <= ids
