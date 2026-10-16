import test from "node:test";
import assert from "node:assert/strict";
import { ingestTrace, loadSavedReport, nativeScoutUrl, requestJson, startAnalysis } from "../src/api.js";

test("native viewer links are limited to completed Scout runs and do not fetch", (t) => {
  t.mock.method(globalThis, "fetch", () => assert.fail("Links must not run an analysis."));
  const run = { id: "run/a", analyzer: { name: "scout_collaboration_v1" }, status: "completed" };
  assert.equal(nativeScoutUrl(run), "/api/analysis-runs/run%2Fa/scout-view");
  for (const status of ["queued", "running", "failed"]) {
    assert.equal(nativeScoutUrl({ ...run, status }), null);
  }
  assert.equal(nativeScoutUrl({ ...run, analyzer: { name: "regex_v1" } }), null);
  assert.equal(nativeScoutUrl({ ...run, id: null }), null);
  assert.equal(nativeScoutUrl(null), null);
});

test("ingests structured source without HTML parsing", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (path, options) => {
    calls.push([path, JSON.parse(options.body)]);
    return { ok: true, json: async () => ({ traceId: "trace_example" }) };
  });
  const source = { type: "share_json", value: { messages: [] } };
  assert.deepEqual(await ingestTrace(source), { traceId: "trace_example" });
  assert.deepEqual(calls, [["/api/traces", { source }]]);
});

test("starts explicit model-backed analysis", async (t) => {
  t.mock.method(globalThis, "fetch", async (path, options) => {
    assert.equal(path, "/api/traces/trace_example/analyses/scout_collaboration_v1");
    assert.deepEqual(JSON.parse(options.body), { model: "mockllm/model" });
    return { ok: true, json: async () => ({ status: "queued" }) };
  });
  assert.equal((await startAnalysis("trace_example", "scout_collaboration_v1", "mockllm/model")).status, "queued");
});

test("surfaces API validation and analysis failures", async (t) => {
  t.mock.method(globalThis, "fetch", async () => ({
    ok: false, json: async () => ({ detail: "Invalid trace source." })
  }));
  await assert.rejects(requestJson("/api/traces/missing"), /Invalid trace source/);
});

test("preserves structured Scout setup errors for the setup dialog", async (t) => {
  const setup = { model: "openai/gpt-5.4-mini", ready: false, issues: [{ code: "openai_api_key_missing" }] };
  t.mock.method(globalThis, "fetch", async () => ({
    ok: false, json: async () => ({
      detail: { code: "scout_setup_required", message: "OPENAI_API_KEY is not set.", setup }
    })
  }));
  await assert.rejects(startAnalysis("trace_example", "scout_collaboration_v1"), (error) => {
    assert.equal(error.message, "OPENAI_API_KEY is not set.");
    assert.equal(error.code, "scout_setup_required");
    assert.deepEqual(error.setup, setup);
    return true;
  });
});

test("loads a saved trace and pins its linked historical analysis", async (t) => {
  const oldRun = { id: "run_old", trace_id: "trace_example", analyzer: { name: "regex_v1", kind: "offline" } };
  t.mock.method(globalThis, "fetch", async (path) => ({
    ok: true,
    json: async () => path === "/api/traces/trace_example"
      ? { traceId: "trace_example", analyses: { regex_v1: { id: "run_latest" } } }
      : oldRun
  }));
  const loaded = await loadSavedReport("?trace=trace_example&run=run_old");
  assert.equal(loaded.report.analyses.regex_v1.id, "run_old");
  assert.equal(loaded.selectedAnalysis, oldRun);
});

test("rejects analysis links for a different trace", async (t) => {
  t.mock.method(globalThis, "fetch", async (path) => ({
    ok: true, json: async () => path.startsWith("/api/traces/")
      ? { traceId: "trace_example", analyses: {} }
      : { trace_id: "trace_other", analyzer: { name: "regex_v1" } }
  }));
  await assert.rejects(loadSavedReport("?trace=trace_example&run=run_other"), /does not belong/);
});

test("trace-only links do not request or start any analysis", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (path) => {
    calls.push(path);
    return { ok: true, json: async () => ({ traceId: "trace_example", analyses: {} }) };
  });
  assert.equal((await loadSavedReport("?trace=trace_example")).selectedAnalysis, null);
  assert.deepEqual(calls, ["/api/traces/trace_example"]);
  assert.equal(await loadSavedReport(""), null);
});
