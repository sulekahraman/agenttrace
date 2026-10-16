import importlib.util
from html.parser import HTMLParser
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "reports" / "2026-10-16-progress"


def load_builder():
    spec = importlib.util.spec_from_file_location("progress_report", REPORT / "build_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.sheets = 0
        self.external_resources = []

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if "id" in attributes:
            self.ids.append(attributes["id"])
        if tag == "a":
            self.links.append(attributes["href"])
        if tag == "article" and attributes.get("class") == "sheet":
            self.sheets += 1
        if ("src" in attributes and not attributes["src"].startswith("data:")) or (
            tag == "link" and not attributes.get("href", "").startswith("data:")
        ):
            self.external_resources.append(attributes)


def test_progress_report_is_current_and_deterministic():
    builder = load_builder()
    generated = builder.outputs()
    assert generated == builder.outputs()
    for filename, text in generated.items():
        assert (REPORT / filename).read_text(encoding="utf-8") == text


def test_progress_report_counts_and_applicability():
    summary = json.loads((REPORT / "summary.json").read_text(encoding="utf-8"))
    counts = summary["counts"]
    assert (counts["traces"], counts["agent_posts"], counts["task_operator_posts"]) == (9, 59, 11)
    assert counts["visible_posts"] == counts["message_annotations"] == counts["candidate_messages"] == 70
    assert counts["substantive_offline"] + counts["demo_plugin"] + counts["completed_scout"] == 36
    assert counts["substantive_offline"] == 18
    assert counts["collaboration_judgments"] == 27
    assert (counts["visible_multi_agent_traces"], counts["solo_traces"], counts["task_only_traces"]) == (6, 2, 1)
    assert counts["historical_runs"] == 49
    assert counts["candidate_count_truncated_traces"] == 0
    assert counts["messages_over_8000_characters"] == counts["messages_over_2000_characters"] == 3
    assert summary["raw_scout_positive_judgments"] == {
        "duplicated_work": 6, "weak_handoff": 5, "unintegrated_information": 5,
    }
    assert sorted((row["analyzer_version"], row["prompt_version"], row["traces"])
                  for row in summary["scout_versions"]) == [("2.0.0", "2", 1), ("2.1.0", "3", 8)]
    assert [trace["ref"] for trace in summary["traces"] if trace["scout_version"] == "2.0.0"] == ["E7"]
    assert {day for trace in summary["traces"] for day in trace["source_dates"]} == {"2026-10-10"}
    types = summary["primary_message_types_including_task_operator_posts"]
    assert sum(types.values()) == 70
    assert len({run["run_id"] for trace in summary["traces"] for run in trace["selected_runs"]}) == 36
    html = (REPORT / "index.html").read_text(encoding="utf-8")
    assert html.count('class="unobserved">N/A (raw: no)') == 6
    assert html.count('class="unobserved">Unknown (raw: no)') == 3
    assert "6.141 seconds" in html
    assert "E9 #7 already reports D before #8 reports B" in html


def test_progress_report_links_and_offline_assets():
    builder = load_builder()
    html = (REPORT / "index.html").read_text(encoding="utf-8")
    parser = ReportParser()
    parser.feed(html)
    assert parser.sheets == 12
    assert len(parser.ids) == len(set(parser.ids))
    assert parser.external_resources == []
    assert re.search(r"\{\{[A-Z_0-9]+\}\}", html) is None
    for url in parser.links:
        if url.startswith("#"):
            assert url[1:] in parser.ids
        elif url.startswith(builder.GITHUB):
            relative = url[len(builder.GITHUB):].split("#", 1)[0]
            path = ROOT / relative
            assert path.is_file(), relative
            if "#L" in url:
                match = re.search(r"#L(\d+)-L(\d+)$", url)
                assert match, url
                start, end = map(int, match.groups())
                assert 1 <= start <= end <= len(path.read_text(encoding="utf-8").splitlines())
        elif not url.startswith("https://"):
            assert (REPORT / url).is_file(), url
    assert "/Users/" not in html
    assert "sk-proj-" not in html
    assert "BEGIN PRIVATE KEY" not in html
    pdf = (REPORT / "progress-report.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 12
    assert not re.search(rb"/URI\s*\([^)]*(?:127\.0\.0\.1|file:)[^)]*\)", pdf)
    assert b"/Users/" not in pdf
