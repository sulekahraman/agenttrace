# ProgramBench progress addendum — October 17, 2026

- [Presentation PDF](progress-addendum.pdf): six landscape pages.
- [Self-contained HTML](index.html): download and open locally; not hosted.
- [Machine-readable summary](summary.json): every selected run ID, provenance,
  metrics, raw judgments, and the separate qualitative audit.
- [Frozen input and result dataset](../../data/programbench-pr10/).
- [Three-repository roles and future storage workflow](../../docs/experiment-storage.md).

Adds 12 Goal Run records from commsfail PR #10: nine xsv runs and three yj runs,
with 618 raw posts, 602 agent posts and 195 turn-log files. All 12 receive
structural, regex, log-grounded facts_v1, and model-backed Scout analysis;
12 demo-plugin outputs are preserved but not counted as substantive detectors.

No hidden-test scores are present. DONE consensus is not a task-success grade.
The report audits all four facts_v1 flags and cautions against interpreting
Scout's raw collaboration judgments as validated failure rates. The original
nine-trace dataset and October 16 professor report are preserved separately.
An explicit citation audit records 20 of 36 Scout finding records with narrative
display citations absent from their structured original-turn lists. Raw outputs
are retained, not repaired or treated as verified evidence.

Regenerate deterministic HTML/JSON from the frozen evidence, without network
or model calls:

```bash
python3 reports/2026-10-17-programbench/build_report.py
python3 reports/2026-10-17-programbench/build_report.py --check
```

Re-export the PDF from the generated HTML after any content changes, using A4
landscape, print backgrounds, CSS page sizing, and no browser headers/footers.
The HTML/JSON checker does not regenerate the PDF.
