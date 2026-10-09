export function AnalysisResults({ analysis, onEvidence }) {
  if (!analysis) return null;
  if (analysis.status === "failed") {
    return <p role="alert" className="analysis-error">{analysis.error}</p>;
  }
  if (analysis.status !== "completed") {
    return <p role="status">Analysis {analysis.status}...</p>;
  }

  const output = analysis.output?.output || analysis.output;
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
