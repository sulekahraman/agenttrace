import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildScoutTranscript } from "../src/scout.js";

function sampleReport() {
  const report = JSON.parse(readFileSync(new URL("../../../fixtures/legacy-report.json", import.meta.url)));
  return {
    ...report, traceId: "trace_example", schemaVersion: "2.0",
    source: { kind: "share-file", provider: "sharednet" },
    conversation: { title: "Fixture", firstTimestamp: report.messages[0].timestamp }
  };
}

test("bridge preserves canonical trace identity and messages", () => {
  const report = sampleReport();
  const bridge = buildScoutTranscript(report);
  assert.equal(bridge.transcript_id, report.traceId);
  assert.equal(bridge.source_type, "share-file");
  assert.equal(bridge.message_count, 3);
  assert.equal(bridge.metadata.agenttrace_schema_version, "2.0");
  assert.equal(bridge.messages[1].metadata.sequence, 2);
  assert.equal(bridge.messages[1].content, report.messages[1].text);
});

test("bridge excludes future context and resolves explicit earlier citations", () => {
  const report = sampleReport();
  report.messages[2].text = "Reviewer, check #1 and [M2] in art_sample, not #9.";
  const bridge = buildScoutTranscript(report);
  const context = bridge.messages[2].metadata.annotation_context;
  assert.deepEqual(context.hints.cites, [1, 2]);
  assert.deepEqual(context.hints.artifacts, ["art_sample"]);
  assert.deepEqual(context.hints.addressed_to, ["Reviewer BBBB"]);
  assert.deepEqual(context.previous_messages.map((message) => message.index), [1, 2]);
  assert.deepEqual(bridge.messages[0].metadata.annotation_context.previous_messages, []);
});

test("bridge bounds context text and number of messages", () => {
  const report = sampleReport();
  report.messages = Array.from({ length: 20 }, (_, index) => ({
    ...report.messages[0], index: index + 1, text: "x".repeat(3000)
  }));
  const context = buildScoutTranscript(report).messages[19].metadata.annotation_context;
  assert.equal(context.previous_messages.length, 12);
  assert.equal(context.previous_messages[0].text.length, 500);
  assert.throws(() => buildScoutTranscript({ messages: [] }), /messages/);
});
