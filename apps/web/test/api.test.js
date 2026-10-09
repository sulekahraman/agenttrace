import test from "node:test";
import assert from "node:assert/strict";
import { ingestTrace, requestJson, startAnalysis } from "../src/api.js";

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
