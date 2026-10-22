import { useEffect, useState } from "react";
import { requestJson, startAnalysis } from "./api.js";
import { AnalysisResults } from "./analysis-results.jsx";

const analyzer = "communication_failures_v1";

export function CommunicationSetup({ report, defaultModel, setReport, onEvidence }) {
  const saved = report.analyses[analyzer];
  const [model, setModel] = useState(saved?.provenance.model || defaultModel || "");
  const [run, setRun] = useState(saved || null);
  const [setup, setSetup] = useState(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const active = ["queued", "running"].includes(run?.status);

  useEffect(() => {
    setRun(saved || null);
    setModel(saved?.provenance.model || defaultModel || "");
    setSetup(null);
    setError("");
  }, [report.traceId, saved?.id, defaultModel]);

  useEffect(() => {
    if (!active) return undefined;
    const controller = new AbortController();
    let timer;
    async function poll() {
      try {
        const updated = await requestJson(`/api/analysis-runs/${run.id}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRun(updated);
        if (["queued", "running"].includes(updated.status)) {
          timer = setTimeout(poll, 1000);
        } else {
          setReport((current) => current?.traceId === updated.trace_id ? {
            ...current, analyses: { ...current.analyses, [analyzer]: updated }
          } : current);
        }
      } catch (failure) {
        if (failure.name !== "AbortError") setError(failure.message);
      }
    }
    timer = setTimeout(poll, 300);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [run?.id, active]);

  async function showSetup() {
    setError("");
    try {
      setSetup(await requestJson(`/api/communication/setup?model=${encodeURIComponent(model.trim())}&trace_id=${encodeURIComponent(report.traceId)}`));
    } catch (failure) {
      setError(failure.message);
    }
  }

  async function start() {
    setStarting(true);
    setError("");
    setSetup(null);
    try {
      const created = await startAnalysis(report.traceId, analyzer, model.trim());
      setRun(created);
      setReport((current) => current?.traceId === created.trace_id ? {
        ...current, analyses: { ...current.analyses, [analyzer]: created }
      } : current);
    } catch (failure) {
      setError(failure.message);
      if (failure.code === "communication_setup_required") setSetup(failure.setup);
    } finally {
      setStarting(false);
    }
  }

  return (
    <section className="panel span-2" aria-label="Communication failure analysis setup">
      <h2>Communication failure incidents</h2>
      <p><strong>Experimental, separate from Scout.</strong> Checks Disclosure, Delivery, Reading and Action using independent A/B evidence discovery, full-window review and adjudication: five model steps, up to fifteen generation attempts with validation retries. Observed breakdowns count even without proven downstream harm; unknown decisions explain why.</p>
      <p className="muted">Running sends supplied messages and execution evidence to the selected provider; charges apply. Keep confidential traces on a locally configured provider.</p>
      <div className="analysis-controls">
        <label>Communication model
          <input value={model} onChange={(event) => setModel(event.target.value)} placeholder="provider/model" />
        </label>
        <button type="button" disabled={starting || active || !model.trim()} onClick={start}>
          {active ? "Communication analysis running..." : "Run communication analysis"}
        </button>
        <button type="button" className="secondary" disabled={starting || !model.trim()} onClick={showSetup}>Communication provider setup</button>
      </div>
      {setup && <div role="status">
        <p>{setup.ready ? "Provider dependencies and credential presence are ready; access is checked during execution." : "Provider setup required."}</p>
        {setup.issues.map((issue) => <p role="alert" key={issue.code}>{issue.message}</p>)}
        {!setup.ready && <p>Activate the server environment and install <code>{setup.install_command}</code> if needed. Configure provider credentials server-side, then restart <code>{setup.start_command}</code>. Never enter keys in this page.</p>}
        {setup.coverage && <p>Raw turns: {setup.coverage.raw_turns}; wake records: {setup.coverage.wake_records}.
          {setup.coverage.recorded_inputs ? " Recorded turn inputs imported." : " Recorded turn inputs unavailable."}
          {setup.coverage.workspace_history ? " Batch workspace history imported." : " Workspace history unavailable."}
          {" Serialized model API requests are not imported."}
        </p>}
      </div>}
      {error && <p role="alert" className="analysis-error">{error}</p>}
      <AnalysisResults analysis={run} onEvidence={onEvidence} />
    </section>
  );
}
