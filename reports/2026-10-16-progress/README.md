# Multi-agent experiments and trace analysis

**Professor-facing progress report — October 16, 2026**

[Read the presentation PDF](progress-report.pdf) ·
[Download the self-contained HTML](https://raw.githubusercontent.com/sulekahraman/agenttrace/main/reports/2026-10-16-progress/index.html) ·
[Computed summary and source/run IDs](summary.json)

The report has **eight briefing pages and four evidence/reproduction appendix
pages**. Download the HTML and open it in Chrome for an offline, responsive
version with clickable source citations and **Print / save PDF**. GitHub shows
HTML as source, not a hosted website. There are no external assets, provider
calls, or sign-in requirements to read the report. Evidence links point to the
frozen data commit, not mutable `main`.

## Main takeaways

- **Completed:** nine teammate-supplied traces preserved and analyzed. The
  selected results comprise 18 substantive offline analyses, nine Scout
  analyses, and nine optional demo-plugin runs. Scout produced 70 message
  annotations and 27 category judgments, not 27 verified failures.
- **Observed:** coding conversations contain competing ownership and overwrite
  claims. Arithmetic solo/team conditions report different answers under
  different interpretations; the team explicitly asks the user for guidance.
  The GPQA conversation shows disagreement, reconsideration, and contradictory
  file-state reports, not a proven causal recovery mechanism.
- **Analysis-quality concern:** Scout sometimes flags deliberate independent
  verification as duplicated work. These are unvalidated model judgments, not
  research ground truth or measured failure prevalence.
- **Not established:** independent task grades, actual artifact histories,
  cost/active-runtime measurements, generalized success rates, causal gains,
  or completed training experiments.
- **Proposed next:** a controlled, externally scored ownership-protocol pilot
  with execution/artifact logs and human adjudication before choosing a
  training target.

The scope is the nine-trace dataset, not a complete inventory of team
experiments. Eight Scout runs use analyzer 2.1.0 / prompt 3; the task-only trace
uses 2.0.0 / prompt 2. The report discloses this rather than silently rerunning
or changing saved results.

## Rebuild or verify

From the repository root, using Python 3.10+ and no extra dependencies:

```bash
python3 reports/2026-10-16-progress/build_report.py
python3 reports/2026-10-16-progress/build_report.py --check
```

`build_report.py` reads the frozen manifest, selected batch JSON, transcripts,
agent-only metrics, and SQLite in **read-only mode**. It verifies identities,
counts, message citations and short quoted evidence before generating
`index.html` and `summary.json` from `template.html`. It does not start
AgentTrace, load `.env`, import a model SDK, or regenerate judgments.

The PDF is a print export of the generated HTML. After changing the report,
regenerate HTML and print all pages to A4 landscape, with backgrounds enabled
and browser headers/footers disabled; replace `progress-report.pdf`. HTML and
JSON regeneration is deterministic; PDF metadata can vary by browser/export.

The appendix and the [dataset guide](../../data/teammate-traces/README.md)
explain restoring a separate working copy and opening the same saved judgments
in AgentTrace and native Scout without new inference.
