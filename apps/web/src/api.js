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
