export async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) {
    const message = typeof body.detail === "string"
      ? body.detail
      : body.detail?.message || JSON.stringify(body.detail || body.error || "Request failed.");
    const error = new Error(message);
    error.code = body.detail?.code;
    error.setup = body.detail?.setup;
    throw error;
  }
  return body;
}

export function ingestTrace(source) {
  return requestJson("/api/traces", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ source })
  });
}

export function startAnalysis(traceId, analyzer, model) {
  return requestJson(`/api/traces/${encodeURIComponent(traceId)}/analyses/${encodeURIComponent(analyzer)}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(model ? { model } : {})
  });
}

export function nativeScoutUrl(analysis) {
  if (analysis?.analyzer?.name !== "scout_collaboration_v1" || analysis.status !== "completed" || !analysis.id) {
    return null;
  }
  return `/api/analysis-runs/${encodeURIComponent(analysis.id)}/scout-view`;
}

export async function loadSavedReport(search, options = {}) {
  const params = new URLSearchParams(search);
  const traceId = params.get("trace");
  if (!traceId) return null;
  const report = await requestJson(`/api/traces/${encodeURIComponent(traceId)}`, options);
  const runId = params.get("run");
  if (!runId) return { report, selectedAnalysis: null };
  const analysis = await requestJson(`/api/analysis-runs/${encodeURIComponent(runId)}`, options);
  if (analysis.trace_id !== report.traceId) {
    throw new Error("The linked analysis does not belong to this trace.");
  }
  return {
    report: { ...report, analyses: { ...report.analyses, [analysis.analyzer.name]: analysis } },
    selectedAnalysis: analysis
  };
}
