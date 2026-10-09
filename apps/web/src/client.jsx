import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import * as Plot from "@observablehq/plot";
import { buildScoutTranscript } from "./scout.js";
import { ingestTrace, requestJson, startAnalysis } from "./api.js";
import { AnalysisResults } from "./analysis-results.jsx";
import "./styles.css";

const exampleUrl = "https://www.sharednet.ai/s/shr_iNiJPLkMnu4c5b7wYTfqVW4xf_CJBYWtNUBNyrof4Zg";
const offlineLabels = {
  regex_v1: {
    order: 0,
    title: "Conversation patterns",
    description: "Find repetition, coordination gaps and other communication signals in the messages."
  },
  facts_v1: {
    order: 1,
    title: "Claims vs. actions",
    description: "Compare agents' claims with execution logs to find unsupported reviews, success claims and contradictions."
  }
};
const colors = [
  "#73f2b7",
  "#e8ff7a",
  "#7bb8ff",
  "#ff9f7b",
  "#c69cff",
  "#59d6d6",
  "#ff78aa",
  "#d2a86e",
  "#9ad36a",
  "#a4b4ff"
];

function formatNumber(value) {
  return new Intl.NumberFormat().format(value);
}

function formatDuration(milliseconds) {
  if (milliseconds == null) return "Unknown";
  const minutes = Math.round(milliseconds / 60_000);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} hr`;
  return `${Math.round(hours / 24)} days`;
}

function formatTimestamp(value) {
  if (!value) return "Unknown dates";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function PlotChart({ build, data, onDatumClick, label }) {
  const containerRef = useRef(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const container = containerRef.current;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.max(320, Math.floor(entry.contentRect.width)));
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!width) return undefined;
    const container = containerRef.current;
    const plot = build(width);
    container.replaceChildren(plot);

    const handleClick = (event) => {
      if (!onDatumClick) return;
      let target = event.target;
      while (target && target !== plot) {
        if (target.closest?.('g[aria-label="bar"], g[aria-label="cell"], g[aria-label="text"]') && target.__data__ != null) {
          const datum = typeof target.__data__ === "number" ? data[target.__data__] : target.__data__;
          if (datum) onDatumClick(datum);
          return;
        }
        target = target.parentNode;
      }
    };

    plot.addEventListener("click", handleClick);
    return () => {
      plot.removeEventListener("click", handleClick);
      plot.remove();
    };
  }, [build, data, onDatumClick, width]);

  return <div ref={containerRef} className="plot-container" aria-label={label} />;
}

function MetricCard({ label, value, title }) {
  return (
    <article className="metric" title={title}>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
    </article>
  );
}

function PanelHeading({ eyebrow, title, note }) {
  return (
    <div className="panel-heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h3>{title}</h3>
      </div>
      {note && <p className="muted">{note}</p>}
    </div>
  );
}

function ScoutSetupDialog({ setup, onClose }) {
  const dialogRef = useRef(null);
  useEffect(() => {
    dialogRef.current.showModal();
  }, []);
  const openai = setup.model.startsWith("openai/");
  const missingPackage = setup.issues.some((issue) => issue.code === "scout_not_installed");
  return (
    <dialog ref={dialogRef} className="setup-dialog" aria-labelledby="scout-setup-title" onCancel={onClose}>
      <h2 id="scout-setup-title">{setup.ready ? "Scout provider setup" : "Set up Scout"}</h2>
      <p>Selected model: <code>{setup.model}</code></p>
      {setup.issues.map((issue) => <p role="alert" className="analysis-error" key={issue.code}>{issue.message}</p>)}
      {setup.ready && <p>{openai
        ? "Key detected. Access is checked when Scout runs."
        : "Scout is installed. Configure your provider's credentials on the server."}</p>}
      <p>From the repo root, activate the Python environment where AgentTrace is installed.</p>
      <ol>
        {missingPackage && <li>Install Scout from the repository root:
          <pre><code>{setup.install_command}</code></pre>
        </li>}
        {openai ? <li>Create a key in the <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">OpenAI API dashboard</a> (API billing required).</li> :
          <li>Set your provider's credentials using the <a href="https://inspect.aisi.org.uk/providers.html" target="_blank" rel="noreferrer">Inspect provider guide</a>.</li>}
        <li>Stop AgentTrace, then run:
          {openai && <pre><code>{`read -s "OPENAI_API_KEY?Paste your OpenAI API key: "; echo\nexport OPENAI_API_KEY\n${setup.start_command}`}</code></pre>}
          {!openai && <pre><code>{setup.start_command}</code></pre>}
        </li>
        <li>Keep that terminal open. Refresh and click <strong>Run Scout</strong>.</li>
      </ol>
      <p className="muted">Keys stay on the server. Scout sends trace content to your provider; API charges apply.</p>
      <details>
        <summary>{openai ? "Other shells & details" : "More details"}</summary>
        <p>For the default environment, activate with <code>source .venv/bin/activate</code>. Use your environment's name if different.</p>
        {openai && <>
          <p>Bash/Linux:</p>
          <pre><code>{`read -r -s -p "Paste your OpenAI API key: " OPENAI_API_KEY; echo\nexport OPENAI_API_KEY\n${setup.start_command}`}</code></pre>
          <p>A ChatGPT subscription does not include API usage.</p>
        </>}
        <p>Use Ctrl+C to stop a foreground server. For a background server, identify its current AgentTrace process first.</p>
        <p>Keys entered with these commands are hidden and not saved to a file. Never share them or commit them to Git.</p>
      </details>
      <button type="button" autoFocus onClick={onClose}>Close</button>
    </dialog>
  );
}

function downloadJson(value, filename) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json" });
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(blob);
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}

function App() {
  const [url, setUrl] = useState(exampleUrl);
  const [report, setReport] = useState(null);
  const [status, setStatus] = useState("Ready to analyze the example trace.");
  const [statusType, setStatusType] = useState("");
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedAgents, setSelectedAgents] = useState([]);
  const [turnStart, setTurnStart] = useState("");
  const [turnEnd, setTurnEnd] = useState("");
  const [transition, setTransition] = useState(null);
  const [expandedMessages, setExpandedMessages] = useState([]);
  const [model, setModel] = useState("");
  const [scoutRun, setScoutRun] = useState(null);
  const [analysisError, setAnalysisError] = useState("");
  const [scoutSetup, setScoutSetup] = useState(null);
  const [startingAnalysis, setStartingAnalysis] = useState(false);
  const [analyzers, setAnalyzers] = useState([]);
  const [offlineAnalyzer, setOfflineAnalyzer] = useState("regex_v1");
  const [sourceType, setSourceType] = useState("sharednet_share");
  const [upload, setUpload] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    requestJson("/api/analyzers", { signal: controller.signal }).then((available) => {
      setAnalyzers(available);
      const scout = available.find((analyzer) => analyzer.name === "scout_collaboration_v1");
      if (scout?.default_model) setModel((current) => current || scout.default_model);
    }).catch((error) => {
      if (error.name !== "AbortError") setAnalysisError(error.message);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!scoutRun || !["queued", "running"].includes(scoutRun.status)) return undefined;
    const controller = new AbortController();
    let timer;
    async function poll() {
      try {
        const updated = await requestJson(`/api/analysis-runs/${scoutRun.id}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (["queued", "running"].includes(updated.status)) {
          timer = setTimeout(poll, 1500);
        } else {
          setScoutRun(updated);
          setReport((current) => current?.traceId === updated.trace_id ? {
            ...current,
            analyses: { ...current.analyses, scout_collaboration_v1: updated }
          } : current);
        }
      } catch (error) {
        if (error.name !== "AbortError") setAnalysisError(`Scout status could not be loaded: ${error.message}`);
      }
    }
    timer = setTimeout(poll, 500);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [scoutRun?.id, scoutRun?.status]);

  useEffect(() => {
    const identifier = new URLSearchParams(window.location.search).get("trace");
    if (!identifier) return undefined;
    const controller = new AbortController();
    requestJson(`/api/traces/${encodeURIComponent(identifier)}`, { signal: controller.signal }).then((body) => {
      setReport(body);
      setScoutRun(body.analyses.scout_collaboration_v1 || null);
      if (body.analyses.scout_collaboration_v1?.provenance.model) {
        setModel(body.analyses.scout_collaboration_v1.provenance.model);
      }
      setStatus(`Loaded ${body.metrics.totalMessages} messages from saved trace.`);
    }).catch((error) => {
      if (error.name !== "AbortError") {
        setStatusType("error");
        setStatus(error.message);
      }
    });
    return () => controller.abort();
  }, []);

  const agentIds = report?.participants.map((participant) => participant.id) || [];
  const traceAnalyzers = report?.analyzers || analyzers;
  const selectedOfflineAnalyzer = traceAnalyzers.find((analyzer) => analyzer.name === offlineAnalyzer);
  useEffect(() => {
    if (report && selectedOfflineAnalyzer && !selectedOfflineAnalyzer.available) setOfflineAnalyzer("regex_v1");
  }, [report?.traceId, selectedOfflineAnalyzer?.available]);
  const colorScale = useMemo(() => ({
    domain: agentIds,
    range: agentIds.map((_, index) => colors[index % colors.length]),
    legend: true
  }), [agentIds]);

  const messageMatchesFilters = (message) => {
    if (selectedAgents.length && !selectedAgents.includes(message.participantId)) return false;
    if (turnStart !== "" && message.index < Number(turnStart)) return false;
    if (turnEnd !== "" && message.index > Number(turnEnd)) return false;
    if (query && !`${message.participantId} ${message.runtime} ${message.text}`.toLowerCase().includes(query.toLowerCase())) {
      return false;
    }
    if (transition) {
      const messagePosition = report.messages.findIndex((candidate) => candidate.index === message.index);
      const previous = report.messages[messagePosition - 1];
      if (!previous || previous.participantId !== transition.source || message.participantId !== transition.target) {
        return false;
      }
    }
    return true;
  };

  const visibleMessages = useMemo(
    () => report ? report.messages.filter(messageMatchesFilters) : [],
    [query, report, selectedAgents, transition, turnEnd, turnStart]
  );

  const hasFilters = Boolean(
    query || selectedAgents.length || turnStart !== "" || turnEnd !== "" || transition
  );

  function resetFilters() {
    setQuery("");
    setSelectedAgents([]);
    setTurnStart("");
    setTurnEnd("");
    setTransition(null);
  }

  function toggleAgent(agentId) {
    setSelectedAgents((current) =>
      current.includes(agentId)
        ? current.filter((candidate) => candidate !== agentId)
        : [...current, agentId]
    );
  }

  function toggleExpanded(messageIndex) {
    setExpandedMessages((current) =>
      current.includes(messageIndex)
        ? current.filter((candidate) => candidate !== messageIndex)
        : [...current, messageIndex]
    );
  }

  async function analyze(event) {
    event.preventDefault();
    setLoading(true);
    setReport(null);
    setScoutRun(null);
    setAnalysisError("");
    resetFilters();
    setStatusType("loading");
    setStatus("Fetching and analyzing the conversation...");

    try {
      let value = url;
      if (sourceType === "share_json") {
        if (!upload) throw new Error("Choose a SharedNet share JSON file.");
        if (upload.size > 5_000_000) throw new Error("Share JSON must be smaller than 5 MB.");
        value = JSON.parse(await upload.text());
      }
      const body = await ingestTrace({ type: sourceType, value });
      setReport(body);
      setScoutRun(body.analyses.scout_collaboration_v1 || null);
      window.history.replaceState(null, "", `?trace=${encodeURIComponent(body.traceId)}`);
      setStatusType("");
      setStatus(`Analyzed ${body.metrics.totalMessages} messages from ${body.metrics.participantCount} agents.`);
    } catch (error) {
      setStatusType("error");
      setStatus(error.message);
    } finally {
      setLoading(false);
    }
  }

  async function runAnalysis(name) {
    setStartingAnalysis(true);
    setAnalysisError("");
    try {
      const analysis = await startAnalysis(report.traceId, name, name === "scout_collaboration_v1" ? model.trim() : undefined);
      if (name === "scout_collaboration_v1") setScoutRun(analysis);
      setReport((current) => ({
        ...current, analyses: { ...current.analyses, [name]: analysis }
      }));
    } catch (error) {
      setAnalysisError(error.message);
      if (error.code === "scout_setup_required" && error.setup) setScoutSetup(error.setup);
    } finally {
      setStartingAnalysis(false);
    }
  }

  async function showScoutSetup() {
    setAnalysisError("");
    try {
      setScoutSetup(await requestJson(`/api/scout/setup?model=${encodeURIComponent(model.trim())}`));
    } catch (error) {
      setAnalysisError(error.message);
    }
  }

  function showEvidence(number) {
    resetFilters();
    setTurnStart(String(number));
    setTurnEnd(String(number));
    setExpandedMessages([number]);
    document.querySelector("#message-explorer")?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <main>
      {scoutSetup && <ScoutSetupDialog setup={scoutSetup} onClose={() => setScoutSetup(null)} />}
      <header className="app-header">
        <div className="brand">
          <p className="eyebrow">Multi-agent post-training research</p>
          <h1>AgentTrace</h1>
          <p className="lede">Explore participation, communication structure, response dynamics, and structural failure-mode signals.</p>
        </div>
        <form onSubmit={analyze}>
          <label htmlFor="source-type">Trace source
            <select id="source-type" value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
              <option value="sharednet_share">SharedNet public share link</option>
              <option value="share_json">SharedNet share JSON file</option>
              <option value="local">Local goal-run directory or export</option>
            </select>
          </label>
          <label htmlFor="conversation-url">{sourceType === "local" ? "Path relative to configured data directory" : sourceType === "share_json" ? "Share JSON file" : "SharedNet conversation link"}</label>
          <div className="input-row">
            {sourceType === "share_json" ? <input key="share-upload" id="conversation-url" type="file" accept=".json,application/json" required onChange={(event) => setUpload(event.target.files[0] || null)} /> : <input
              key="source-path"
              id="conversation-url"
              type={sourceType === "sharednet_share" ? "url" : "text"}
              required
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              autoComplete="url"
            />}
            <button type="submit" disabled={loading || startingAnalysis}>Analyze</button>
          </div>
          <p className="form-note">{sourceType === "local" ? "Local sources require AGENTTRACE_SOURCE_ROOT on the API server." : "SharedNet traces are loaded through commsfail. Scout runs only when explicitly requested."}</p>
        </form>
      </header>

      <section className={`status ${statusType}`} aria-live="polite">{status}</section>

      {report && (
        <>
          <section className="report-header">
            <div>
              <p className="eyebrow">Conversation report</p>
              <h2>{report.conversation.title}</h2>
              <p className="muted">
                {formatTimestamp(report.conversation.firstTimestamp)} to {formatTimestamp(report.conversation.lastTimestamp)}
                {" | "}
                {report.conversation.description || "Public trace"}
              </p>
            </div>
            <div className="report-actions">
              <button
                className="secondary"
                type="button"
                onClick={() => downloadJson(report, "agenttrace-report.json")}
              >
                Export JSON
              </button>
              <button
                className="secondary"
                type="button"
                onClick={() => downloadJson(
                  buildScoutTranscript(report),
                  "agenttrace-scout-transcript.json"
                )}
              >
                Export for Scout
              </button>
            </div>
          </section>

          <section className="metric-grid" aria-label="Summary metrics">
            <MetricCard label="Messages" value={formatNumber(report.metrics.totalMessages)} />
            <MetricCard label="Agents" value={formatNumber(report.metrics.participantCount)} />
            <MetricCard label="Conversation span" value={formatDuration(report.metrics.durationMs)} />
            <MetricCard label="Total words" value={formatNumber(report.metrics.totalWords)} />
            <MetricCard label="Contribution balance" value={`${report.metrics.contributionBalance}%`} title="100% means equal message counts across agents." />
            <MetricCard label="Turn switch rate" value={`${report.metrics.turnSwitchRate}%`} title="Share of adjacent messages authored by different agents." />
            <MetricCard label="Median response" value={formatDuration(report.metrics.medianResponseLatencyMs)} />
            <MetricCard label="Question follow-up" value={`${Math.round(report.metrics.questionFollowUpRate * 100)}%`} title="Question messages followed by another agent within three turns." />
          </section>

          <section className="filter-panel">
            <div className="filter-topline">
              <div>
                <p className="eyebrow">Linked exploration</p>
                <h3>Filter the trace</h3>
              </div>
              <button className="secondary compact" type="button" disabled={!hasFilters} onClick={resetFilters}>Reset filters</button>
            </div>
            <div className="filter-controls">
              <label className="search-control">
                Search
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Agent or message content" />
              </label>
              <label>
                First turn
                <input type="number" min="1" max={report.messages.at(-1).index} value={turnStart} onChange={(event) => setTurnStart(event.target.value)} placeholder="1" />
              </label>
              <label>
                Last turn
                <input type="number" min="1" max={report.messages.at(-1).index} value={turnEnd} onChange={(event) => setTurnEnd(event.target.value)} placeholder={String(report.messages.at(-1).index)} />
              </label>
            </div>
            <div className="agent-chips">
              {report.participants.map((participant, index) => {
                const active = selectedAgents.includes(participant.id);
                return (
                  <button
                    key={participant.id}
                    type="button"
                    className={`agent-chip ${active ? "active" : ""}`}
                    style={{ "--agent-color": colors[index % colors.length] }}
                    onClick={() => toggleAgent(participant.id)}
                  >
                    {participant.id}
                  </button>
                );
              })}
            </div>
            <div className="active-filter-row">
              <span>{formatNumber(visibleMessages.length)} of {formatNumber(report.messages.length)} messages shown</span>
              {transition && (
                <button className="filter-chip" type="button" onClick={() => setTransition(null)}>
                  {transition.source} → {transition.target} ×
                </button>
              )}
            </div>
          </section>

          <section className="panel span-2">
            <PanelHeading eyebrow="commsfail annotators" title="Communication failures" note="Deterministic evidence pointers, not human labels." />
            <div className="annotator-grid" role="group" aria-label="Offline annotators">
              {traceAnalyzers.filter((analyzer) => analyzer.kind === "offline" && analyzer.name !== "agenttrace_heuristics_v1")
                .sort((left, right) => (offlineLabels[left.name]?.order ?? 2) - (offlineLabels[right.name]?.order ?? 2)).map((analyzer) => {
                const label = offlineLabels[analyzer.name] || { title: analyzer.name, description: "An installed commsfail offline plugin." };
                const run = report.analyses[analyzer.name];
                return (
                  <button key={analyzer.name} type="button" className="annotator-card"
                    aria-label={`Select ${label.title}`} aria-pressed={offlineAnalyzer === analyzer.name}
                    disabled={!analyzer.available || startingAnalysis || loading} onClick={() => setOfflineAnalyzer(analyzer.name)}>
                    <span className="annotator-kind">Offline / No API key</span>
                    <strong>{label.title}</strong>
                    <span className="annotator-description">{label.description}</span>
                    <code>{analyzer.name} v{analyzer.version}</code>
                    <span className={`annotator-status ${!analyzer.available || run?.status === "failed" ? "needs-setup" : ""}`}>
                      {!analyzer.available ? "Needs execution logs" : run ? `Run ${run.status}` : "Ready to run"}
                    </span>
                    {!analyzer.available && <span className="annotator-description">{analyzer.unavailable_reason}</span>}
                  </button>
                );
              })}
            </div>
            <div className="analysis-controls">
              <button type="button" disabled={startingAnalysis || loading || !selectedOfflineAnalyzer?.available} onClick={() => runAnalysis(offlineAnalyzer)}>Run annotator</button>
              <p className="muted">Selected: {offlineLabels[offlineAnalyzer]?.title || offlineAnalyzer}. Runs locally without model charges.</p>
            </div>
            <AnalysisResults analysis={report.analyses[offlineAnalyzer]} onEvidence={showEvidence} />
          </section>

          <section className="panel span-2">
            <PanelHeading eyebrow="Inspect Scout" title="Semantic collaboration findings" note="Model judgments; verify cited evidence. Running Scout sends this trace to the selected model provider and may incur charges." />
            <div className="scout-overview">
              <span className="annotator-kind">LLM / Provider API key / Usage-based cost</span>
              <p>Annotates messages and checks <strong>duplicated work</strong>, <strong>weak handoffs</strong> and <strong>unintegrated information</strong>.</p>
              <span className="annotator-status">{scoutRun ? `Run ${scoutRun.status}` : "Not run"}</span>
            </div>
            <div className="analysis-controls">
              <label>Model
                <input value={model} onChange={(event) => setModel(event.target.value)} placeholder="provider/model" />
              </label>
              <button type="button" disabled={startingAnalysis || loading || ["queued", "running"].includes(scoutRun?.status) || !model.trim()} onClick={() => runAnalysis("scout_collaboration_v1")}>
                {["queued", "running"].includes(scoutRun?.status) ? "Scout running..." : "Run Scout"}
              </button>
              <button type="button" className="secondary" disabled={!model.trim() || startingAnalysis || loading} onClick={showScoutSetup}>Provider setup</button>
            </div>
            <p className="muted">Default: <code>{analyzers.find((analyzer) => analyzer.name === "scout_collaboration_v1")?.default_model || "Loading..."}</code>. Change the provider/model above to use another model. If setup is missing, Run Scout opens instructions before creating a run.</p>
            <AnalysisResults analysis={scoutRun} onEvidence={showEvidence} />
          </section>
          {analysisError && <p className="analysis-error" role="alert">{analysisError}</p>}

          <section className="panel span-2">
            <PanelHeading
              eyebrow="Conversation shape"
              title="Turn timeline"
              note="Click a bar to isolate that message. Filters dim non-matching turns."
            />
            <PlotChart
              data={report.messages}
              label="Message word counts by turn and agent"
              onDatumClick={(message) => {
                if (!message.index) return;
                setTurnStart(String(message.index));
                setTurnEnd(String(message.index));
              }}
              build={(width) => Plot.plot({
                width,
                height: 290,
                marginLeft: 58,
                color: colorScale,
                x: { label: "Turn" },
                y: { label: "Words", grid: true },
                marks: [
                  Plot.barY(report.messages, {
                    x: "index",
                    y: "words",
                    fill: "participantId",
                    opacity: (message) => messageMatchesFilters(message) ? 1 : 0.12,
                    title: (message) => `#${message.index} ${message.participantId}\n${message.words} words`
                  }),
                  Plot.ruleY([0])
                ]
              })}
            />
          </section>

          <section className="dashboard-grid">
            <article className="panel">
              <PanelHeading eyebrow="Participation" title="Contribution share" note="Click an agent to toggle its filter." />
              <PlotChart
                data={report.participants}
                label="Messages contributed by each agent"
                onDatumClick={(participant) => participant.id && toggleAgent(participant.id)}
                build={(width) => Plot.plot({
                  width,
                  height: Math.max(300, report.participants.length * 48),
                  marginLeft: 138,
                  color: colorScale,
                  x: { label: "Messages", grid: true },
                  y: { label: null, domain: report.participants.map((participant) => participant.id) },
                  marks: [
                    Plot.barX(report.participants, {
                      x: "messages",
                      y: "id",
                      fill: "id",
                      opacity: (participant) => !selectedAgents.length || selectedAgents.includes(participant.id) ? 1 : 0.18,
                      title: (participant) => `${participant.id}\n${participant.messages} messages\n${participant.words} words`
                    }),
                    Plot.text(report.participants, {
                      x: "messages",
                      y: "id",
                      text: "messages",
                      dx: 5,
                      textAnchor: "start",
                      fill: "#f0f7f3"
                    }),
                    Plot.ruleX([0])
                  ]
                })}
              />
            </article>

            <article className="panel">
              <PanelHeading eyebrow="Communication structure" title="Turn-transition matrix" note="Click a cell to inspect matching transitions." />
              <PlotChart
                data={report.transitions}
                label="Directed transitions between agents"
                onDatumClick={(edge) => {
                  if (!edge.source || !edge.target) return;
                  setTransition((current) =>
                    current?.source === edge.source && current?.target === edge.target ? null : edge
                  );
                }}
                build={(width) => Plot.plot({
                  width,
                  height: Math.max(390, agentIds.length * 58),
                  marginLeft: 138,
                  marginBottom: 112,
                  x: { label: "Next agent", domain: agentIds, tickRotate: -35 },
                  y: { label: "Source agent", domain: agentIds },
                  color: { scheme: "greens", legend: true, label: "Transitions" },
                  marks: [
                    Plot.cell(report.transitions, {
                      x: "target",
                      y: "source",
                      fill: "count",
                      opacity: (edge) => !transition || (transition.source === edge.source && transition.target === edge.target) ? 1 : 0.15,
                      inset: 1,
                      title: (edge) => `${edge.source} → ${edge.target}\n${edge.count} transitions`
                    }),
                    Plot.text(report.transitions, {
                      x: "target",
                      y: "source",
                      text: "count",
                      fill: "#f0f7f3"
                    })
                  ]
                })}
              />
            </article>
          </section>

          <section className="panel span-2">
            <PanelHeading eyebrow="Research prompts, not verdicts" title="Potential failure modes" note="Every flag exposes its deterministic threshold." />
            <div className="failure-grid">
              {report.failureModes.map((mode) => (
                <article key={mode.id} className={`failure-card ${mode.severity}`}>
                  <h4>{mode.title}</h4>
                  <p>{mode.detail}</p>
                  <small>{mode.threshold}</small>
                  <small>{mode.evidence}</small>
                </article>
              ))}
            </div>
          </section>

          <section id="message-explorer" className="panel span-2">
            <PanelHeading
              eyebrow="Trace explorer"
              title={`Messages (${formatNumber(visibleMessages.length)})`}
              note="Select a row to expand its full content."
            />
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Turn</th>
                    <th>Agent</th>
                    <th>Words</th>
                    <th>Questions</th>
                    <th>Signals</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleMessages.slice(0, 500).map((message) => {
                    const expanded = expandedMessages.includes(message.index);
                    const signals = Object.entries(message.signals).filter(([, count]) => count > 0);
                    return (
                      <tr id={`message-${message.index}`} key={message.index} className="message-row" onClick={() => toggleExpanded(message.index)}>
                        <td>#{message.index}</td>
                        <td>{message.participantId}</td>
                        <td>{formatNumber(message.words)}</td>
                        <td>{formatNumber(message.questions)}</td>
                        <td>
                          {signals.map(([name, count]) => <span key={name} className="signal">{name} {count}</span>)}
                        </td>
                        <td className={expanded ? "expanded-message" : ""}>
                          {expanded || message.text.length <= 260 ? message.text : `${message.text.slice(0, 260)}...`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <p className="method-note"><strong>Method note:</strong> structural metrics are deterministic. Agreement, challenge, coordination, question follow-up, and failure-mode labels are lexical or turn-taking proxies; they support triage and hypothesis generation, not outcome evaluation.</p>
        </>
      )}
    </main>
  );
}

createRoot(document.querySelector("#root")).render(<App />);
