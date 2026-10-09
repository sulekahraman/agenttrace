"""The command line: listing, analysing to a record, validating, and starting a new annotator."""
import importlib.util, json, sys
from pathlib import Path
from commsfail.annotators import check_annotator, registry, taxonomy_of, validate_output
from commsfail.cli import KICKSTART
from commsfail.cli import main
from commsfail.sources import sharednet

GOAL_RUN = str(Path(__file__).resolve().parent / "fixtures" / "goal_run")

def test_lists(capsys):
    assert main(["annotators"]) == 0
    out = capsys.readouterr().out
    assert "regex_v1" in out and "builtin" in out and "comms-failure/analysis.v1" in out
    assert "ten_modes@1" in out and "state_gap@1" in out
    assert any(line.startswith("standard ") and "annotate-batch" in line for line in out.splitlines())
    assert main(["sources"]) == 0 and "sharednet" in capsys.readouterr().out

def test_analyse_validate_and_markdown(tmp_path, capsys):
    out = tmp_path / "rec.json"
    assert main(["analyse", GOAL_RUN, "-o", str(out)]) == 0
    rec = json.loads(out.read_text())
    assert rec["record"] == "commsfail/record.v1" and rec["annotator"]["name"] == "regex_v1"
    assert rec["source"]["kind"] == "goal-run" and rec["output"]["schema"] == "comms-failure/analysis.v1"
    assert main(["validate", str(out)]) == 0
    rec["output"]["modes"] = rec["output"]["modes"][:3]
    bad = tmp_path / "bad.json"; bad.write_text(json.dumps(rec))
    assert main(["validate", str(bad)]) == 1
    capsys.readouterr()
    assert main(["analyse", GOAL_RUN, "--markdown"]) == 0
    assert "| mode | severity |" in capsys.readouterr().out

def test_trace_and_schema(capsys):
    assert main(["trace", GOAL_RUN]) == 0
    assert json.loads(capsys.readouterr().out)["posts"] == 12
    assert main(["schema", "regex_v1"]) == 0
    assert json.loads(capsys.readouterr().out)["$id"] == "comms-failure/analysis.v1"
    assert main(["taxonomy"]) == 0
    listing = capsys.readouterr().out
    assert all(c in listing for c in ("ten_modes", "state_gap", "decision_point")) and "complete" in listing
    assert main(["taxonomy", "regex_v1"]) == 0
    assert len(json.loads(capsys.readouterr().out)["modes"]) == 10
    assert main(["taxonomy", "state_gap"]) == 0
    assert [g["id"] for g in json.loads(capsys.readouterr().out)["groups"]][:6] == \
        ["unsaid", "unreceived", "misread", "disagreement", "ungrounded", "stalled"]
    plain = [n for n, c in registry().items() if taxonomy_of(c) is None]
    if plain:
        assert main(["taxonomy", plain[0]]) == 1 and "has no taxonomy" in capsys.readouterr().err

def test_new_makes_a_working_copy_of_example_kickstart(tmp_path, capsys, monkeypatch):
    (tmp_path / "commsfail" / "annotators").mkdir(parents=True)
    assert main(["new", "my_method_v1", "--root", str(tmp_path)]) == 0
    folder = tmp_path / "commsfail" / "annotators" / "my_method_v1"
    assert sorted(p.name for p in folder.iterdir()) == ["README.md", "__init__.py", "schema.json"]
    assert "kickstart" not in (folder / "README.md").read_text().lower()      # the how-to note stays behind
    test = tmp_path / "tests" / "annotators" / "test_my_method_v1.py"
    compile(test.read_text(), str(test), "exec")
    assert "my_method_v1" in test.read_text() and "example_kickstart" not in test.read_text()
    spec = importlib.util.spec_from_file_location("my_method_v1", folder / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "my_method_v1", mod)
    spec.loader.exec_module(mod)
    cls = mod.ANNOTATOR
    assert cls.__name__ == "MyMethodV1" and cls.name == "my_method_v1"
    assert check_annotator(cls) == []
    out = cls().annotate(sharednet.load(GOAL_RUN))
    assert validate_output(cls, out) == [] and [(f["seq"], f["signal"]) for f in out["findings"]] == [(6, "open_question"), (10, "bare_claim")]
    assert out["taxonomy"] == "state_gap@1" and set(cls().modes_in(out)) <= {m["id"] for m in taxonomy_of(cls)["modes"]}
    assert json.loads((folder / "schema.json").read_text())["$id"] == "commsfail/my_method_v1/v1"

def test_the_kickstart_test_is_the_template_new_copies():
    here = Path(__file__).resolve().parent / "annotators" / "test_example_kickstart.py"
    assert here.read_text() == (KICKSTART / "test_example_kickstart.py.txt").read_text(), \
        "tests/annotators/test_example_kickstart.py and example_kickstart/test_example_kickstart.py.txt must stay identical"

def test_new_refuses_bad_names_and_existing_folders(tmp_path):
    import pytest
    (tmp_path / "commsfail" / "annotators").mkdir(parents=True)
    with pytest.raises(SystemExit):
        main(["new", "Bad-Name", "--root", str(tmp_path)])
    main(["new", "ok_v1", "--root", str(tmp_path)])
    with pytest.raises(SystemExit):
        main(["new", "ok_v1", "--root", str(tmp_path)])
    with pytest.raises(SystemExit):
        main(["new", "ok_v2", "--root", str(tmp_path / "nowhere")])
