# Latest-rubric results: all 12 ProgramBench traces

Open `index.html` for the concise report. Every row links to its saved results
and visualizations in the local AgentTrace UI at port 3012; these are not hosted
links. `results.json` preserves every metric, annotation, finding, incident,
independent A/B assessment, adjudication decision and replay provenance.
`summary.json` contains the compact counts.

## Method

User-authorized **GPT-6.1 Sol session prompt replay**, not native Scout/OpenAI
provider inference. Your OpenAI API key was not used; there were no direct
provider API calls. Copilot session usage is separate, not a claim of free inference.
Scout 2.2.0 / prompt 8 regenerated all 602 message labels and the collaboration
candidates from those labels. Each trace's Scout session retains earlier
context and may see nearby later targets within a chronological batch; native
Scout's independent per-message context is not reproduced.

Communication 0.1.0 / prompt 1 uses separate A, B and judge session agents,
the same supplied evidence caps, and the current native validators. The judge
accounts for all A/B candidates. Publication is not receipt; unknown evidence
is not a negative; evidenced incidents count even after repair.

Outputs are validated, **not independent ground truth**. Model, rubric and
candidate selection differ from the October 17 baseline, so differences cannot
be attributed to any single change. Offline structural/regex/facts analyses
are preserved from the frozen cohort, not new model judgments.

Full model inputs and workspace history are missing. Per-event/context clipping
is recorded in each result. No hidden-test scores or independent human labels
are available. Evidence remains untrusted data throughout.

## Reopen or restore the viewer

The current working database is `.agenttrace/sol-12-runs-2026-10-19`.
For a fresh copy, with the API dependencies installed:

```bash
.venv/bin/python reports/2026-10-19-sol-12-runs/build_report.py \
  --restore .agenttrace/sol-12-restored
```

Restoration refuses an existing destination, preserves baseline history, checks
the reconstructed evidence hashes, and imports the saved session results.
It makes no model calls. Serve that directory on port 3012 using AgentTrace;
do not select Run analysis merely to view saved results.

```bash
env -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY \
  AGENTTRACE_DATA_DIR="$PWD/.agenttrace/sol-12-restored" \
  PORT=3012 .venv/bin/agenttrace
```

The viewer opened for this review additionally rejects all write requests.

Rebuild HTML/summary from the saved results without any inference:

```bash
python3 reports/2026-10-19-sol-12-runs/build_report.py
```
