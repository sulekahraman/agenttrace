import { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import * as Plot from "@observablehq/plot";
import "./styles.css";

const exampleUrl = "https://www.sharednet.ai/s/shr_iNiJPLkMnu4c5b7wYTfqVW4xf_CJBYWtNUBNyrof4Zg";
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

function PlotChart({ build, onDatumClick, label }) {
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
        if (target.__data__ && typeof target.__data__ === "object") {
          onDatumClick(target.__data__);
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
  }, [build, onDatumClick, width]);

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

function downloadReport(report) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(blob);
  anchor.download = "multi-agent-trace-analysis.json";
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

  const agentIds = report?.participants.map((participant) => participant.id) || [];
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
    resetFilters();
    setStatusType("loading");
    setStatus("Fetching and analyzing the conversation...");

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url })
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Analysis failed.");
      setReport(body);
      setStatusType("");
      setStatus(`Analyzed ${body.metrics.totalMessages} messages from ${body.metrics.participantCount} agents.`);
    } catch (error) {
      setStatusType("error");
      setStatus(error.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <header className="app-header">
        <div className="brand">
          <p className="eyebrow">Multi-agent post-training research</p>
          <h1>TraceScope</h1>
          <p className="lede">Explore participation, communication structure, response dynamics, and structural failure-mode signals.</p>
        </div>
        <form onSubmit={analyze}>
          <label htmlFor="conversation-url">SharedNet conversation link</label>
          <div className="input-row">
            <input
              id="conversation-url"
              type="url"
              required
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              autoComplete="url"
            />
            <button type="submit" disabled={loading}>Analyze</button>
          </div>
          <p className="form-note">Public <code>sharednet.ai/s/...</code> links only.</p>
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
            <button className="secondary" type="button" onClick={() => downloadReport(report)}>Export JSON</button>
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
                <input type="number" min="1" max={report.metrics.totalMessages} value={turnStart} onChange={(event) => setTurnStart(event.target.value)} placeholder="1" />
              </label>
              <label>
                Last turn
                <input type="number" min="1" max={report.metrics.totalMessages} value={turnEnd} onChange={(event) => setTurnEnd(event.target.value)} placeholder={String(report.metrics.totalMessages)} />
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
            <PanelHeading
              eyebrow="Conversation shape"
              title="Turn timeline"
              note="Click a bar to isolate that message. Filters dim non-matching turns."
            />
            <PlotChart
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

          <section className="panel span-2">
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
                      <tr key={message.index} className="message-row" onClick={() => toggleExpanded(message.index)}>
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
