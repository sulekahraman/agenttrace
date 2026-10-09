"""The catalog and the taxonomy choices: each pattern defined once, and every complete choice places every pattern."""
import copy, json
import pytest
from commsfail.annotators import check_annotator, registry, taxonomy_of
from commsfail.annotators.taxonomy import (CHOICES_DIR, catalog, check_catalog, check_choice, check_taxonomy, choices,
                                           group_of, load_choice, patterns, regroup)

CHOICES = choices()

def _raw(name):
    return json.loads((CHOICES_DIR / f"{name}.json").read_text())

def test_the_catalog_defines_each_pattern_once():
    assert check_catalog(catalog()) == []

@pytest.mark.parametrize("name", CHOICES)
def test_each_choice_is_valid(name):
    assert check_choice(_raw(name)) == []

@pytest.mark.parametrize("name", [c for c in CHOICES if _raw(c).get("complete")])
def test_a_complete_choice_places_every_pattern(name):
    t = load_choice(name)
    placed = {m["id"] for m in t["modes"]} | {o["id"] for o in t["out_of_scope"]}
    assert placed == set(patterns())

def test_the_choices_on_offer():
    assert {"ten_modes", "state_gap", "decision_point"} <= set(CHOICES)
    assert load_choice("state_gap")["complete"] and load_choice("decision_point")["complete"]
    assert not load_choice("ten_modes")["complete"]          # the reference covers ten patterns, on purpose

def test_ten_modes_keeps_the_papers_order_and_fields():
    t = load_choice("ten_modes")
    assert [m["id"] for m in t["modes"]] == ["R1", "R2", "B1", "B2", "D1", "D2", "D3", "D4", "REP", "HB"]
    assert {m["id"]: m["removed_by"] for m in t["modes"]}["D1"] == "check"

def test_one_pattern_reads_in_every_choice():
    # the same label lands in a different class under each choice: this is what makes them comparable
    assert [group_of(load_choice(c))["B1"] for c in ("ten_modes", "state_gap", "decision_point")] == \
        ["not_binding", "disagreement", "claim"]
    counts = {"R1": 2, "D1": 3, "stale_act": 1}
    assert regroup(counts, "state_gap") == {"misread": 2, "ungrounded": 3, "unreceived": 1}
    assert regroup(counts, "ten_modes") == {"not_read": 2, "never_done": 3, None: 1}     # ten_modes has no stale_act

GOOD = {"id": "t", "version": "1", "description": "a test choice", "complete": False,
        "groups": [{"id": "g", "name": "G", "definition": "a class"}], "modes": {"R1": "g"}}

def _broken(change):
    t = copy.deepcopy(GOOD)
    change(t)
    return t

@pytest.mark.parametrize("change,msg", [
    (lambda t: t.pop("version"), "non-empty string 'version'"),
    (lambda t: t.update(modes={}), "must place at least one pattern"),
    (lambda t: t["modes"].update(made_up="g"), "'made_up' is not a pattern of the catalog"),
    (lambda t: t["modes"].update(R2="nowhere"), "which 'groups' does not define"),
    (lambda t: t["groups"].append(dict(t["groups"][0])), "group ids must be unique"),
    (lambda t: t.update(out_of_scope={"R1": "why"}), "'R1' is both placed and out of scope"),
    (lambda t: t.update(complete=True), "a complete choice must place every pattern"),
])
def test_check_choice_refuses(change, msg):
    assert check_choice(GOOD) == []
    errs = check_choice(_broken(change))
    assert any(msg in e for e in errs), errs

@pytest.mark.parametrize("change,msg", [
    (lambda c: c["patterns"].append(dict(c["patterns"][0])), "is defined twice"),
    (lambda c: c["patterns"][0].update(kind="odd"), "'kind' must be one of"),
    (lambda c: c["patterns"][0].pop("example"), "needs a non-empty string 'example'"),
])
def test_check_catalog_refuses(change, msg):
    cat = copy.deepcopy(catalog())
    change(cat)
    assert any(msg in e for e in check_catalog(cat))

def test_an_annotator_names_a_real_choice_and_says_which_patterns_it_reports():
    class Bad:
        name, version = "bad_v1", "0.1.0"
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "x", "title": "x",
                  "description": "x", "type": "object"}
        taxonomy = "no_such_choice"
        def annotate(self, trace): return {}
    assert any("no taxonomy choice 'no_such_choice'" in e for e in check_annotator(Bad))
    Bad.taxonomy = "state_gap"
    assert any("modes_in" in e for e in check_annotator(Bad))
    Bad.modes_in = lambda self, out: []
    assert check_annotator(Bad) == []

def test_an_inline_taxonomy_is_checked_too():
    assert check_taxonomy(load_choice("state_gap")) == []
    assert any("mode ids must be unique" in e for e in check_taxonomy({"id": "t", "version": "1",
                                                                       "modes": [load_choice("ten_modes")["modes"][0]] * 2}))

def test_facts_v1_reads_in_ten_modes_and_names_patterns_for_every_fact():
    from commsfail.annotators.facts_v1 import FACTS
    assert taxonomy_of(registry()["facts_v1"])["id"] == "ten_modes"
    assert all(pattern in patterns() for pattern, _ in FACTS.values())
