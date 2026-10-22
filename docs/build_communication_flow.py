"""Generate the self-contained flow/prompt reference without dependencies or inference."""

import argparse
import ast
import html
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMM = ROOT / "packages/agenttrace-api/agenttrace/communication"
SCOUT = ROOT / "packages/agenttrace-api/agenttrace/scout"
OUTPUT = Path(__file__).with_name("communication-analysis-flow.html")


def source(path):
    text = path.read_text(encoding="utf-8")
    return text, ast.parse(text)


def literal(path, name):
    _, tree = source(path)
    node = next(node for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
    value = node.value
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "strip":
        return ast.literal_eval(value.func.value).strip()
    return ast.literal_eval(value)


def prompt_source(path, function, assignment=None):
    text, tree = source(path)
    definition = next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and node.name == function)
    if assignment:
        expression = next(node.value for node in ast.walk(definition) if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == assignment for target in node.targets))
    else:
        expression = next(node.value for node in definition.body if isinstance(node, ast.Return))
    if isinstance(expression, ast.Call):
        expression = expression.func.value
    segment = ast.get_source_segment(text, expression)
    if not isinstance(expression, ast.JoinedStr) or not segment.startswith('f"""'):
        raise ValueError(f"Update prompt extraction for {function}.")
    return segment[4:-3].strip()


def definitions(path, names):
    text, tree = source(path)
    return "\n\n".join(ast.get_source_segment(text, node) for node in tree.body
                       if isinstance(node, ast.ClassDef) and node.name in names)


def panel(identifier, title, content):
    return (f'<details id="{identifier}"><summary>{html.escape(title)}</summary>'
            f'<pre>{html.escape(content)}</pre></details>')


def box(x, y, width, height, title, lines, tone="blue"):
    heading = f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" class="{tone}"/>'
    for offset, line in enumerate([title, *lines]):
        weight = ' font-weight="700"' if offset == 0 else ""
        heading += (f'<text x="{x + 16}" y="{y + 27 + offset * 22}"{weight}>'
                    f'{html.escape(line)}</text>')
    return heading


def arrow(points):
    return f'<polyline points="{points}" class="arrow" marker-end="url(#head)"/>'


def diagram():
    nodes = [
        box(20, 20, 1220, 105, "Frozen export -> deterministic import (0 LLM calls)", [
            "Room posts + wakes | turn logs | inputs.jsonl | actions.jsonl | native sessions | workspace snapshots/git",
            "Validate hashes, native/stream action links and model-visible receipts. Freeze evidence; do not trust message instructions.",
            "Scout gets the message transcript/context. Communication analysis also gets execution, receipt and workspace evidence.",
        ], "green"),
        box(20, 175, 350, 120, "Scout: annotate each message", [
            "N message stages; 1-3 attempts each",
            "Target <=8k chars; roster, hints,",
            "cited posts <=2k; preceding 12 <=500",
        ]),
        box(20, 345, 350, 120, "Scout: candidate selection (0 calls)", [
            "Annotations -> type filter + neighbors",
            "Keep annotation index + citation map",
            "<=80 candidate posts; <=2k chars each",
        ], "green"),
        box(20, 515, 350, 120, "Scout: collaboration scan (1 call)", [
            "All three flags in ONE response:",
            "duplicated work, weak handoff,",
            "unintegrated information",
        ]),
        box(20, 690, 350, 120, "Scout: validate + save (0 calls)", [
            "Binary yes/no; no unknown value",
            "No can include insufficient evidence",
            "No native full-window review here",
        ], "green"),
        box(420, 175, 820, 120, "Communication: bounded discovery index (0 calls)", [
            "Posts/wakes first, then core action/receipt/workspace summaries; detail events interleaved by actor",
            "<=8k text characters/event; <=240k total event text. Full-detail IDs and omissions stay explicit.",
            "This index is NOT the complete source. Retrieval restores requested details from the frozen bundle.",
        ], "green"),
        box(420, 345, 390, 100, "1. search-A (1 call)", [
            "Independent work-item discovery",
            "Returns actor + event-bounded windows",
        ]),
        box(850, 345, 390, 100, "2. search-B (1 call)", [
            "Same index; no search-A answer",
            "Returns its own windows",
        ]),
        box(420, 495, 390, 120, "Retrieve A windows (0 calls)", [
            "Full commands/outputs/diffs/checkpoints",
            "Include overlapping actions + details",
            "Certificate: required events + gaps",
        ], "green"),
        box(850, 495, 390, 120, "Retrieve B windows (0 calls)", [
            "Same deterministic retrieval policy",
            "No requested detail is clipped",
            "Budget errors are explicit",
        ], "green"),
        box(420, 665, 390, 100, "3. A: independent review (1 call)", [
            "A's full packet -> Assessment",
            "No B review or search answer",
        ]),
        box(850, 665, 390, 100, "4. B: independent review (1 call)", [
            "B's full packet -> Assessment",
            "No A review or search answer",
        ]),
        box(420, 815, 820, 100, "Judge input (0 calls): full union packet + both validated assessments", [
            "Union budget is checked BEFORE reviews. Oversized union fails; no silent clipping or partial verdict.",
            "Judge can reconsider Unknown using either side's restored evidence, not just the old excerpts.",
        ], "green"),
        box(420, 965, 820, 100, "5. judge: adjudication (1 call)", [
            "Keep/reject every A/B candidate; merge duplicates; agreement is not proof.",
            "First supported failed transition. Flag observed breakdown separately from downstream impact.",
        ]),
        box(420, 1115, 820, 100, "Deterministic validation -> saved results -> UI/report (0 calls)", [
            "Exact citations, receipt checks, first-failure order, scoped absence/negative checks, candidate accounting",
            "Save prompts + schemas + replies + errors + actual generation attempts; keep historical results unchanged.",
        ], "green"),
    ]
    edges = [
        "195,125 195,175", "830,125 830,175",
        "195,295 195,345", "195,465 195,515", "195,635 195,690",
        "830,295 830,320 615,320 615,345", "830,320 1045,320 1045,345",
        "615,445 615,495", "1045,445 1045,495",
        "615,615 615,665", "1045,615 1045,665",
        "615,765 615,815", "1045,765 1045,815",
        "830,915 830,965", "830,1065 830,1115",
    ]
    return ('<div class="scroll"><svg viewBox="0 0 1260 1240" role="img" aria-labelledby="flow-title">'
            '<title id="flow-title">Scout and five-stage communication analysis: data, independence and model-call counts</title>'
            '<defs><marker id="head" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto">'
            '<path d="M0,0 L8,4 L0,8" fill="#64748b"/></marker></defs>'
            + "".join(arrow(edge) for edge in edges) + "".join(nodes) + '</svg></div>')


def render():
    analysis = COMM / "analysis.py"
    constants = {name: literal(analysis, name) for name in (
        "RUBRIC", "PROMPT_TEMPLATE", "SEARCH_INSTRUCTIONS", "REVIEW_INSTRUCTIONS", "JUDGE_INSTRUCTIONS",
    )}
    version, prompt_version = (literal(COMM / "__init__.py", key) for key in ("VERSION", "PROMPT_VERSION"))
    annotation = prompt_source(SCOUT / "annotations.py", "build_annotation_prompt")
    for name in ("MESSAGE_TYPES", "RULES"):
        annotation = annotation.replace("{" + name + "}", literal(SCOUT / "annotations.py", name))
    collaboration = prompt_source(SCOUT / "scanners.py", "analyze_collaboration", "question")
    stages = [
        ("search-A", "SEARCH_INSTRUCTIONS", "{DISCOVERY_INDEX_JSON}", "", "EvidenceSearch"),
        ("search-B", "SEARCH_INSTRUCTIONS", "{DISCOVERY_INDEX_JSON}", "", "EvidenceSearch"),
        ("A", "REVIEW_INSTRUCTIONS", "{A_FULL_WINDOW_PACKET_JSON}", "", "Assessment"),
        ("B", "REVIEW_INSTRUCTIONS", "{B_FULL_WINDOW_PACKET_JSON}", "", "Assessment"),
        ("judge", "JUDGE_INSTRUCTIONS", "{UNION_FULL_WINDOW_PACKET_JSON}", "{A_B_REVIEW_RECORDS_JSON}", "Adjudication"),
    ]
    prompts = "".join(
        panel(f"prompt-{tag}", f"{tag}: exact application template -> {schema}",
              constants["PROMPT_TEMPLATE"].format(
                  rubric=constants["RUBRIC"], stage=tag, evidence=packet,
                  instructions=constants[instructions], records=records,
              ))
        for tag, instructions, packet, records, schema in stages
    )
    schemas = definitions(analysis, {
        "Record", "EvidenceWindow", "EvidenceSearch", "Citation", "Transition", "Transitions",
        "Recovery", "Incident", "ClassAssessment", "Assessment", "Decision", "Adjudication",
    })
    scout_schemas = definitions(SCOUT / "annotations.py", {"AnnotationEvidence", "MessageAnnotation"})
    scout_schemas += "\n\n" + definitions(SCOUT / "scanners.py", {"CollaborationFinding"})
    styles = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentTrace: annotator data flow, model calls and exact prompts</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f1f5f9;color:#17243a;font:16px/1.55 system-ui,sans-serif}
main{max-width:1340px;margin:auto;padding:32px}h1{line-height:1.2}h2{margin-top:40px}
a{color:#174cb4}p{max-width:1120px}.notice{padding:16px 20px;border-left:5px solid #b7791f;background:#fff8e5}
.card,details{background:white;border:1px solid #d7dfeb;border-radius:12px;padding:18px;margin:14px 0}
summary{cursor:pointer;font-weight:650}pre{font:13px/1.55 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
.scroll{overflow-x:auto}svg{display:block;width:100%;min-width:1100px;background:white;border-radius:12px}
svg text{font-family:system-ui,sans-serif;font-size:14px;fill:#17243a}.blue{fill:#eef4ff;stroke:#6a8cce}
.green{fill:#edf9f3;stroke:#6c9e88}.arrow{fill:none;stroke:#64748b;stroke-width:2}
table{border-collapse:collapse;width:100%;background:white}th,td{border:1px solid #d7dfeb;padding:11px;text-align:left;vertical-align:top}
th{background:#e7edf7}code{font-size:.9em}nav a{display:inline-block;margin-right:18px}
@media(max-width:650px){main{padding:16px}h1{font-size:26px}td,th{min-width:115px}}
</style></head><body><main>
"""
    body = f"""
<h1>Which data reaches each annotator?</h1>
<p>Communication implementation <strong>v{html.escape(version)} / prompt {html.escape(prompt_version)}</strong>.
Blue boxes make model calls; green boxes are deterministic. Search A/B are independent,
review A/B are independent, and only the judge sees both reviews.</p>
<p class="notice"><strong>The latest saved cohort uses a mixed review protocol.</strong>
The <a href="../reports/2026-10-21-v03-12-runs/README.md">fresh October 21 cohort</a>
has new Scout results for all 12 runs. Six communication assessments completed
the five-stage protocol below. After nine review jobs failed, the user approved
direct recovery of the other six in one shared, non-blind parent context, using
all agent posts and selected full native details rather than complete A/B windows.
Those six are not independent A/B judgments; incomplete negative searches remain
Unknown. The original 66 contexts comprise 57 completed and nine failed attempts;
direct recovery adds no independent session jobs or judge calls. The historical
<a href="../reports/2026-10-19-richer-evidence-12-runs/README.md">October 19 report</a>
remains v0.2 / prompt 2. Generating this page uses no LLM calls.</p>
<nav><a href="#flow">Data flow</a><a href="#calls">Call counts</a><a href="#metrics">Metrics / labels</a>
<a href="#prompts">Exact prompts</a><a href="#artifacts">Saved artifacts / limits</a></nav>
<h2 id="flow">Data flow</h2>{diagram()}
<p>Full-window retrieval keeps the bounded core index, replaces requested details with full source text,
and includes applicable workspace checkpoints. The certificate covers the checked export and requested
actors/time interval, not every possible missing real-world observation. See
<a href="communication-evidence.md">retrieval and completeness rules</a>.</p>
<h2 id="calls">How many LLM calls?</h2>
<div class="scroll"><table><thead><tr><th>Path</th><th>Normal successful execution</th><th>Validation-attempt ceiling</th><th>What is counted?</th></tr></thead><tbody>
<tr><td>Communication: one multi-agent run</td><td>5: search-A, search-B, A, B, judge</td><td>15: up to 3 attempts per stage</td><td>Application generation attempts</td></tr>
<tr><td>Communication: all 12 multi-agent runs</td><td>60</td><td>180</td><td>Planned counts, not a new execution</td></tr>
<tr><td>Communication: solo</td><td>0</td><td>0</td><td>Four not-applicable classes</td></tr>
<tr><td>Native Scout pipeline: N annotatable messages</td><td>N + 1</td><td>3N + 1</td><td>N per-message annotation stages, then ONE three-category scan</td></tr>
<tr><td>Import, receipt reconstruction, retrieval, validation, offline heuristics, rendering, restore</td><td>0</td><td>0</td><td>No inference</td></tr>
</tbody></table></div>
<p>The first two searches run in parallel; the two reviews run in parallel after retrieval.
Provider exceptions stop explicitly. Validation failures may regenerate the affected stage; exhausted
validation fails the run, never returns a success-shaped Unknown or No. A failed run can stop before all stages.</p>
<p>These are application calls, <strong>not guaranteed HTTP/billing counts</strong>: provider-internal retries,
structured-output internals and Scout caching may differ. Communication uses cache=False; Scout uses cache=True.
An empty Scout transcript fails before the collaboration scan. Copilot replay session jobs can contain
multiple internal model turns; the historical 36-session count is not a measured provider-call count.</p>
<h2 id="metrics">Seven metrics and their decision labels</h2>
<div class="scroll"><table><thead><tr><th>Metric</th><th>Meaning</th><th>Live definition</th></tr></thead><tbody>
<tr><td>Scout: duplicated work</td><td>Different agents repeat equivalent work without a valid checking, repair or synthesis purpose.</td><td><a href="#prompt-scout-scan">Collaboration prompt, category 1</a></td></tr>
<tr><td>Scout: weak handoff</td><td>An evidenced request/commitment is not delivered/integrated, or ownership leaves work uncoordinated.</td><td><a href="#prompt-scout-scan">Collaboration prompt, category 2</a></td></tr>
<tr><td>Scout: unintegrated information</td><td>Relevant visible information goes unused despite positive evidence of opportunity to use it.</td><td><a href="#prompt-scout-scan">Collaboration prompt, category 3</a></td></tr>
<tr><td>Disclosure</td><td>Relevant knowledge is not shared clearly, accurately and in time, despite a sharing obligation/opportunity.</td><td><a href="#rubric">Common communication rubric</a></td></tr>
<tr><td>Delivery</td><td>A clear timely post is not received before relevant recipient work.</td><td><a href="#rubric">Common communication rubric</a></td></tr>
<tr><td>Reading</td><td>Delivered information is misinterpreted or forgotten; requires the recipient's expressed account.</td><td><a href="#rubric">Common communication rubric</a></td></tr>
<tr><td>Action</td><td>Execution violates a correctly understood commitment.</td><td><a href="#rubric">Common communication rubric</a></td></tr>
</tbody></table></div>
<p><strong>Communication yes:</strong> final judge retained a supported incident.
<strong>No:</strong> no qualifying failure found in explicitly complete, reviewed scopes, not universal absence.
<strong>Unknown:</strong> abstention with a reason; neither yes nor no.
<strong>Scout yes/no:</strong> its binary found flag; no can mean insufficient candidate evidence.
Scout has no Unknown field. None of these are human-verified ground truth. Later repair does not erase an evidenced yes.</p>
<p><strong>Failure flag is not impact.</strong> An observed breakdown can count without proven downstream harm.
Use impact_status=not_established and severity=null when cost is unproven. Disclosure can omit a
recipient-reliance event; delivery still needs relevance to actual work, and reading/action still need understanding evidence.</p>
<div class="scroll"><table><thead><tr><th>Unknown reason</th><th>What is unresolved?</th></tr></thead><tbody>
<tr><td>missing_source_evidence</td><td>Needed evidence was not captured.</td></tr>
<tr><td>evidence_not_retrieved</td><td>Captured evidence was not supplied to this review.</td></tr>
<tr><td>ambiguous_cause</td><td>Attribution of the breakdown, not merely downstream harm.</td></tr>
<tr><td>unclear_obligation</td><td>A sharing need/opportunity or commitment.</td></tr>
<tr><td>unclear_understanding</td><td>Recipient interpretation or retention.</td></tr>
<tr><td>ambiguous_timing</td><td>Publication, receipt or action order.</td></tr>
</tbody></table></div>
<h2 id="prompts">Exact application prompts and structured outputs</h2>
<p>Communication templates below are built directly from live constants, with the entire common rubric
included in each call. Braced uppercase values stand for that run's JSON data; they are not extra model calls.
Scout templates are extracted from their actual Python f-strings: braced expressions show runtime substitutions.
The concrete per-attempt prompts and JSON response schemas are saved with each communication run.</p>
{panel("rubric", "Shared communication rubric (included in all five calls)", constants["RUBRIC"])}
{prompts}
{panel("communication-schema", "Live communication response definitions: search, review and judge", schemas)}
{panel("prompt-scout-message", "Scout message annotation: exact template, types and rules", annotation)}
{panel("prompt-scout-scan", "Scout collaboration scan: exact three-category template", collaboration)}
{panel("scout-schema", "Live Scout structured response definitions", scout_schemas)}
<p>Communication retry suffix: <code>VALIDATION FEEDBACK: {{error}}\\nReturn a corrected complete record.</code>
Previous validation feedback stays in the prompt. Scout's per-message retry feedback is constructed in
<a href="../packages/agenttrace-api/agenttrace/scout/annotations.py">annotate_message</a>;
the collaboration scan has no application validation-retry loop.</p>
<h2 id="artifacts">Exact artifacts and remaining limits</h2>
<p><code>evidence.json</code>: full frozen source; <code>supplied-evidence.json</code>: discovery index;
<code>A-review-evidence.json</code> / <code>B-review-evidence.json</code>: each review packet;
<code>review-evidence.json</code>: judge's full union.
For each actual attempt, <code>{{stage}}-{{attempt}}.prompt.json</code> contains its rendered prompt and
JSON response schema; <code>.reply.json</code> holds a parsed response and <code>.errors.json</code> a rejection.
Provider failures may have no parsed reply. <code>execution.json</code> records stage, attempt and outcome,
including failure/cancellation; successful output also embeds this audit.</p>
<p>Source completeness is scoped, not automatic. Untimed actions/missing author logs block absence claims.
Missing turns use wake intervals; incomplete calls/sessions/compactions remain conservatively actor-wide.
Each restored packet has a 1,200,000 event-text-character cap, excluding metadata; requested details are not
silently clipped. A/B union can exceed that cap even if each side fits: fail explicitly before reviews.
Recorded inputs are not complete serialized API requests; workspace checkpoints are batch-level, not action-level.
Understanding, obligations and causality can remain genuinely ambiguous after all available evidence is read.</p>
<p>Saved prompts are the application layer, not complete provider/system-message serialization.
Scout persists its message prompt (latest attempt) and collaboration prompt; it does not currently provide
the new communication per-attempt execution audit. Historical records remain readable without these new fields.</p>
<p>Source: <a href="../packages/agenttrace-api/agenttrace/communication/analysis.py">communication prompts / validation</a>,
<a href="../packages/agenttrace-api/agenttrace/communication/evidence.py">retrieval / scope certificates</a>,
<a href="../packages/agenttrace-api/agenttrace/scout/annotations.py">Scout annotation prompt</a>,
<a href="../packages/agenttrace-api/agenttrace/scout/scanners.py">Scout collaboration prompt</a>.
Regenerate without inference: <code>python3 docs/build_communication_flow.py</code>;
verify live-template parity: append <code>--check</code>. This HTML has no network dependencies.</p>
"""
    return styles + textwrap.dedent(body) + "</main></body></html>\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != expected:
            parser.exit(1, "Flow reference is stale; run python3 docs/build_communication_flow.py\n")
    else:
        OUTPUT.write_text(expected, encoding="utf-8")


if __name__ == "__main__":
    main()
