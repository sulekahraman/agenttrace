"""Human annotation: blind export, compare (kappa), finalize (gold). The export checks run on every sample."""
import json
from pathlib import Path
import pytest
from commsfail import audit
from commsfail.annotators import choices, load_choice, registry, taxonomy_of
from commsfail.cli import main
from commsfail.sources import sharednet
from commsfail.sources.sharednet import TOKEN_RE, agent_posts

FIXTURES = Path(__file__).resolve().parent / "fixtures"

def _fill(rows, pick):
    """A filled copy of blind rows: pick(row) -> (labels, uncertain)."""
    return [{**r, "labels": pick(r)[0], "uncertain": pick(r)[1]} for r in rows]

none = lambda r: ([], [])

@pytest.mark.parametrize("name", sorted(audit.CODEBOOKS))
def test_built_in_codebooks_are_well_formed(name):
    book = audit.load_codebook(name)
    ids = [x["id"] for x in book["labels"]]
    assert book["id"] == name and book["version"] and len(set(ids)) == len(ids)
    assert all(x["definition"] for x in book["labels"]) and book["rules"]

def test_modes_v1_is_the_ten_modes_choice():
    tax = load_choice("ten_modes")
    assert audit.CODEBOOKS["modes_v1"]["labels"] == [{k: m[k] for k in ("id", "name", "definition")} for m in tax["modes"]]

@pytest.mark.parametrize("name", [*choices(), *(f"{c}:groups" for c in choices()),
                                  *sorted(n for n, c in registry().items() if taxonomy_of(c))])
def test_every_choice_and_every_annotator_taxonomy_is_a_codebook(name, goal_run):
    book = audit.load_codebook(name)
    choice, _, level = name.partition(":")
    tax = load_choice(choice) if choice in choices() else taxonomy_of(registry()[name])
    assert book["id"] == name and [x["id"] for x in book["labels"]] == [m["id"] for m in tax["groups" if level else "modes"]]
    blind, _ = audit.export([goal_run], "s", codebook=name)
    assert {r["codebook"] for r in blind} == {f"{name}@{book['version']}"}

def test_an_annotator_without_a_taxonomy_is_not_a_codebook():
    plain = sorted(n for n, c in registry().items() if not taxonomy_of(c))
    if not plain:
        pytest.skip("every installed annotator has a taxonomy")
    with pytest.raises(ValueError, match="has no taxonomy"):
        audit.load_codebook(plain[0])

def test_export_is_blind(sample):
    blind, key = audit.export([sample], "s1")
    assert len(blind) == len(key) == len(agent_posts(sample))
    text = json.dumps(blind, ensure_ascii=False)
    assert not TOKEN_RE.search(text)
    leaks = [sample.source.get("path"), sample.source.get("room_id"), sample.room.get("name"),
             *[s.get("model") for s in sample.seats]]
    assert [v for v in leaks if v and v in text] == []
    assert all(r["labels"] is None and r["digest"] == audit.digest(r) for r in blind)
    assert {r["sample_id"] for r in blind} == {k["sample_id"] for k in key}
    assert all(k["source"]["path"] == sample.source["path"] and "loaded_at" not in k["source"] for k in key)

def test_export_is_stable_for_one_salt_and_differs_across_salts(goal_run):
    first, again, other = (audit.export([goal_run], s) for s in ("s1", "s1", "s2"))
    assert first == again
    assert {r["sample_id"] for r in first[0]}.isdisjoint(r["sample_id"] for r in other[0])
    assert [r["seq"] for r in first[0]] != sorted(r["seq"] for r in first[0])      # shuffled

def test_export_refuses_a_board_given_twice_and_an_empty_salt(goal_run):
    with pytest.raises(ValueError, match="twice"):
        audit.export([goal_run, goal_run], "s")
    with pytest.raises(ValueError, match="salt"):
        audit.export([goal_run], "")

def test_context(goal_run):
    by_seq = lambda ctx: {r["seq"]: r["context_before"] for r in audit.export([goal_run], "s", context=ctx)[0]}
    full, two, zero = by_seq(None), by_seq(2), by_seq(0)
    for seq, ctx in full.items():
        assert [c["seq"] for c in ctx] == [p["seq"] for p in goal_run.posts if p["seq"] < seq]
        assert two[seq] == ctx[-2:] and zero[seq] == []

def test_scrub_keeps_the_text_and_drops_tokens_and_emails():
    assert audit.scrub("join https://www.sharednet.ai/join/rit_abcdefghijkl123 or mail a.b@c.org\nok") == \
        "join https://www.sharednet.ai/join/<token> or mail <email>\nok"

def test_kappa():
    assert audit.kappa([]) is None
    assert audit.kappa([(False, False)] * 5) is None                     # nobody used the label
    assert audit.kappa([(True, True), (False, False)]) == 1.0
    pairs = [(True, True)] * 4 + [(False, False)] * 4 + [(True, False), (False, True)]
    assert audit.kappa(pairs) == pytest.approx(0.6)                       # observed .8, chance .5

def test_compare_counts_agreement_and_sends_every_difference_to_adjudication(goal_run):
    blind, _ = audit.export([goal_run], "s")
    a = _fill(blind, lambda r: (["D1"] if r["seq"] in (5, 10) else [], []))
    b = _fill(blind, lambda r: (["D1"] if r["seq"] == 5 else [], ["D2"] if r["seq"] == 7 else []))
    report, todo = audit.compare(a, b)
    assert report["samples"] == len(blind) == 11 and report["episodes"] == 1
    assert sorted(r["seq"] for r in todo) == [7, 10]                     # a difference, and an uncertain
    assert report["exact_agreement"] == round(9 / 11, 4)
    assert report["positives"]["D1"] == {"a": 2, "b": 1}
    assert report["decisions"]["D2"] == 10 and report["uncertain_excluded"]["D2"] == 1
    assert 0 < report["kappa"]["D1"] < 1 and report["kappa"]["HB"] is None
    row = next(r for r in todo if r["seq"] == 10)
    assert row["annotator_a"]["labels"] == ["D1"] and row["annotator_b"]["labels"] == [] and row["labels"] is None

def test_an_edited_fixed_field_is_caught(goal_run):
    blind, _ = audit.export([goal_run], "s")
    a = _fill(blind, none)
    one = [dict(r) for r in a]
    one[0]["content"] += " (edited)"
    with pytest.raises(ValueError, match="differ in fixed fields"):
        audit.compare(a, one)
    with pytest.raises(ValueError, match="a fixed field was edited"):
        audit.compare(one, [dict(r) for r in one])

@pytest.mark.parametrize("labels,unsure,msg", [
    (None, [], "list of label ids"),
    (["XX"], [], "not in modes_v1"),
    (["D1"], ["D1"], "both labelled and uncertain"),
])
def test_bad_labels_are_refused(goal_run, labels, unsure, msg):
    blind, _ = audit.export([goal_run], "s")
    a = _fill(blind, none)
    a[0] = {**a[0], "labels": labels, "uncertain": unsure}
    with pytest.raises(ValueError, match=msg):
        audit.compare(a, _fill(blind, none))

def test_finalize_restores_the_source_once_every_difference_is_adjudicated(goal_run):
    blind, key = audit.export([goal_run], "s")
    a = _fill(blind, lambda r: (["D1"] if r["seq"] in (5, 10) else [], []))
    b = _fill(blind, lambda r: (["D1"] if r["seq"] == 5 else [], []))
    _, todo = audit.compare(a, b)
    with pytest.raises(ValueError, match="needs adjudication"):
        audit.finalize(a, b, [], key)
    judged = [{**r, "labels": ["D1"], "uncertain": [], "note": "DONE, and the check failed"} for r in todo]
    gold = audit.finalize(a, b, judged, key)
    assert [r["seq"] for r in gold] == list(range(2, 13))                  # back in board order
    assert {r["seq"]: r["labels"] for r in gold if r["labels"]} == {5: ["D1"], 10: ["D1"]}
    assert [(r["seq"], r["notes"]) for r in gold if r["adjudicated"]] == [(10, ["DONE, and the check failed"])]
    assert gold[0]["source"]["path"] == goal_run.source["path"] and gold[0]["room"] == "goal_run"
    assert gold[0]["trace_digest"] == audit.trace_digest(goal_run)

def test_finalize_refuses_what_is_left_open(goal_run):
    blind, key = audit.export([goal_run], "s")
    a = _fill(blind, lambda r: (["D1"] if r["seq"] == 10 else [], []))
    b = _fill(blind, none)
    _, todo = audit.compare(a, b)
    with pytest.raises(ValueError, match="still uncertain"):
        audit.finalize(a, b, [{**r, "labels": [], "uncertain": ["D1"]} for r in todo], key)
    agreed = next(r for r in a if r["seq"] == 2)
    with pytest.raises(ValueError, match="agreed on"):
        audit.finalize(a, b, [{**r, "labels": [], "uncertain": []} for r in todo] + [agreed], key)
    with pytest.raises(ValueError, match="does not match the key"):
        audit.finalize(a, b, [{**r, "labels": [], "uncertain": []} for r in todo], [{**k, "seq": 99} for k in key])

def test_many_boards_in_one_study():
    traces = [sharednet.load(str(p)) for p in sorted(FIXTURES.iterdir()) if p.name != "README.md" and not p.name.startswith(".")]
    blind, key = audit.export(traces, "s")
    assert len({r["episode_id"] for r in blind}) == len(traces)
    gold = audit.finalize(_fill(blind, none), _fill(blind, none), [], key)
    assert len(gold) == sum(len(agent_posts(t)) for t in traces) and not any(r["labels"] for r in gold)

def test_cli_round_trip(tmp_path, capsys):
    f = lambda name: str(tmp_path / name)
    srcs = [str(FIXTURES / "goal_run"), str(FIXTURES / "share.json")]
    assert main(["audit", "export", *srcs, "--salt", "s", "--out", f("blind.jsonl"), "--key", f("key.jsonl")]) == 0
    rows = audit.read_jsonl(f("blind.jsonl"))
    first = rows[0]["sample_id"]
    audit.write_jsonl(f("a.jsonl"), _fill(rows, lambda r: (["HB"] if r["sample_id"] == first else [], [])))
    audit.write_jsonl(f("b.jsonl"), _fill(rows, none))
    assert main(["audit", "compare", f("a.jsonl"), f("b.jsonl"), "--report", f("report.json"),
                 "--adjudicate", f("todo.jsonl")]) == 0
    assert json.loads(Path(f("report.json")).read_text())["episodes"] == 2
    todo = audit.read_jsonl(f("todo.jsonl"))
    assert len(todo) == 1
    done = ["audit", "finalize", f("a.jsonl"), f("b.jsonl"), "--key", f("key.jsonl"), "--out", f("gold.jsonl")]
    assert main(done) == 1 and "needs adjudication" in capsys.readouterr().err
    audit.write_jsonl(f("judged.jsonl"), [{**r, "labels": ["HB"], "uncertain": []} for r in todo])
    assert main(done + ["--adjudicated", f("judged.jsonl")]) == 0
    assert len(audit.read_jsonl(f("gold.jsonl"))) == len(rows)

def test_cli_codebooks(tmp_path, capsys):
    assert main(["audit", "codebook"]) == 0
    out = capsys.readouterr().out
    assert all(x in out for x in ("modes_v1", "discourse_v1", "state_gap", "decision_point", "state_gap:groups"))
    assert main(["audit", "codebook", "discourse_v1"]) == 0
    assert [x["id"] for x in json.loads(capsys.readouterr().out)["labels"]] == ["accept", "result", "review_pass"]
    mine = tmp_path / "mine.json"
    mine.write_text(json.dumps({"id": "mine", "version": "1", "labels": [{"id": "ask", "definition": "asks for something"}]}))
    assert main(["audit", "export", str(FIXTURES / "share.json"), "--codebook", str(mine), "--salt", "s",
                 "--out", str(tmp_path / "b.jsonl"), "--key", str(tmp_path / "k.jsonl")]) == 0
    assert {r["codebook"] for r in audit.read_jsonl(tmp_path / "b.jsonl")} == {"mine@1"}
    mine.write_text(json.dumps({"id": "mine", "labels": []}))
    assert main(["audit", "codebook", str(mine)]) == 1 and "needs an id" in capsys.readouterr().err
