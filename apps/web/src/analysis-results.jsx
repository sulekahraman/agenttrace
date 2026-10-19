function IncidentResults({ analysis, output, onEvidence }) {
  const events = new Map(output.evidence.map((event) => [event.id, event]));
  function citations(items) {
    return items.map((item, index) => {
      const event = events.get(item.event_id);
      return <div key={`${item.event_id}-${index}`}>
        <blockquote>{item.quote}</blockquote>
        {event?.kind === "post"
          ? <button className="secondary compact" type="button" onClick={() => onEvidence(event.sequence)}>Message #{event.sequence}</button>
          : <details><summary>{item.event_id}</summary><pre>{event?.text || "Evidence unavailable"}</pre></details>}
      </div>;
    });
  }
  return <>
    <p className="muted">{analysis.analyzer.name} v{analysis.analyzer.version} | {analysis.provenance.model} | {output.taxonomy_version}</p>
    <p>{output.explanation}</p>
    <div className="failure-grid">
      {output.classes.map((item) => <article className="failure-card low" key={item.failure_class}>
        <h4>{item.failure_class}</h4><strong>{item.status.replaceAll("_", " ")}</strong><p>{item.explanation}</p>
      </article>)}
    </div>
    {!output.incidents.length && <p>No incidents retained. Check class assessments and coverage; this is not proof of failure-free communication.</p>}
    {output.incidents.map((incident) => <article className="failure-card medium" key={incident.id}>
      <h4>{incident.id}: {incident.failure_class || "Undecidable"} — {incident.work_item}</h4>
      <p>{incident.actors.join(", ")} | Anchor: {incident.anchor} | {incident.status}</p>
      <p>{incident.consequence}</p>
      <p>Severity: {incident.severity ?? "unknown"} — {incident.severity_reason}</p>
      {Object.entries(incident.transitions).map(([name, transition]) => <details key={name}>
        <summary>{name}: {transition.status}</summary>
        <p>{transition.explanation}</p>{citations(transition.evidence)}
      </details>)}
      <p>Recovery: {incident.recovery.status} — {incident.recovery.explanation}</p>
      {citations(incident.recovery.evidence)}
    </article>)}
    <p className="muted">Evidence: {output.coverage.supplied_events}/{output.coverage.total_events} events; {output.coverage.truncated_events.length} shortened; {output.coverage.omitted_events.length} omitted. Raw turns: {output.coverage.raw_turns}. Missing full model inputs and workspace history limit attribution.</p>
    {output.caveats.map((caveat) => <p className="muted" key={caveat}>{caveat}</p>)}
    <details><summary>Incident record, evidence and provenance</summary><pre>{JSON.stringify(analysis, null, 2)}</pre></details>
  </>;
}

export function AnalysisResults({ analysis, onEvidence }) {
  if (!analysis) return null;
  if (analysis.status === "failed") {
    return <p role="alert" className="analysis-error">{analysis.error}</p>;
  }
  if (analysis.status !== "completed") {
    return <p role="status">Analysis {analysis.status}...</p>;
  }

  const output = analysis.output?.output || analysis.output;
  if (output?.schema === "agenttrace/communication-analysis.v1") {
    return <IncidentResults analysis={analysis} output={output} onEvidence={onEvidence} />;
  }
  const modes = output?.modes?.filter((mode) => mode.present);
  const findings = output?.findings?.filter((finding) => typeof finding.category === "string");
  const facts = output?.findings?.filter((finding) => typeof finding.fact === "string");
  const evidenceButtons = (numbers) => [...new Set(numbers)].filter((number) => number > 0).map((number) => (
    <button key={number} className="secondary compact" type="button" onClick={() => onEvidence(number)}>
      Message #{number}
    </button>
  ));

  return (
    <>
      <p className="muted">
        {analysis.analyzer.name} v{analysis.analyzer.version}
        {analysis.provenance?.model && ` | ${analysis.provenance.model}`}
        {analysis.provenance?.completed_at && ` | ${analysis.provenance.completed_at}`}
      </p>
      {modes && (
        <div className="failure-grid">
          {!modes.length && <p>No communication failure patterns detected. This is not a success verdict.</p>}
          {modes.map((mode) => (
            <article key={mode.id} className={`failure-card ${mode.severity}`}>
              <h4>{mode.id}: {mode.name}</h4>
              <p>{mode.description || mode.definition}</p>
              <small>{mode.severity} | Count {mode.count} | Confidence {mode.confidence}</small>
              {(mode.evidence || []).map((item, index) => (
                <div key={index}>
                  <p>{item.why}</p>
                  {evidenceButtons([item.seq])}
                </div>
              ))}
            </article>
          ))}
        </div>
      )}
      {findings?.length > 0 && (
        <div className="failure-grid">
          {findings.map((finding) => (
            <article key={finding.category} className={`failure-card ${finding.found ? "medium" : "low"}`}>
              <h4>{finding.category.replaceAll("_", " ")}</h4>
              <p>{finding.explanation}</p>
              <small>{finding.found ? "Evidence found" : "Insufficient evidence"} | Confidence {finding.confidence}</small>
              <div className="report-actions">{evidenceButtons(finding.message_numbers || [])}</div>
            </article>
          ))}
        </div>
      )}
      {facts?.length > 0 && (
        <div className="failure-grid">
          {facts.map((fact, index) => (
            <article key={`${fact.seq}-${fact.fact}-${index}`} className="failure-card medium">
              <h4>{fact.fact.replaceAll("_", " ")}</h4>
              <p>{fact.why}</p>
              <small>{fact.who}{fact.mode && ` | ${fact.mode}`}</small>
              <blockquote>{fact.excerpt}</blockquote>
              <div className="report-actions">{evidenceButtons([fact.seq])}</div>
            </article>
          ))}
        </div>
      )}
      {output?.applies === true && facts?.length === 0 && (
        <p>No execution-log failure evidence detected. This is not a success verdict.</p>
      )}
      {output?.coverage && (
        <p className="muted">
          Annotated {output.coverage.annotated_messages} messages; inspected {output.coverage.candidate_messages} candidates.
          {output.coverage.truncated && " Candidate evidence was truncated; findings do not cover the entire trace."}
        </p>
      )}
      {output?.caveats?.map((caveat) => <p className="muted" key={caveat}>{caveat}</p>)}
      <details>
        <summary>Full analysis record and provenance</summary>
        <pre className="analysis-json">{JSON.stringify(analysis, null, 2)}</pre>
      </details>
    </>
  );
}
