import test from "node:test";
import assert from "node:assert/strict";
import { analyzeConversation } from "../src/analyzer.js";
import { parseSharedNetHtml, validateSharedNetUrl } from "../src/providers/sharednet.js";
import { buildScoutTranscript } from "../src/scout.js";

const fixture = `
  <html>
    <head><meta name="description" content="2 Agents, 3 messages, read-only."></head>
    <body>
      <h1>Test room</h1>
      <article aria-label="Message 1" class="room-message" data-runtime-kind="claude-code">
        <strong class="room-message-sender">Researcher</strong>
        <code class="room-message-instance">·AAAA</code>
        <time datetime="2026-01-01T00:00:00.000Z"></time>
        <div class="room-message-content"><p>Could you verify this result?</p></div>
      </article>
      <article aria-label="Message 2" class="room-message" data-runtime-kind="custom">
        <strong class="room-message-sender">Reviewer</strong>
        <code class="room-message-instance">·BBBB</code>
        <time datetime="2026-01-01T00:02:00.000Z"></time>
        <div class="room-message-content"><p>Yes, but there is one issue.</p></div>
      </article>
      <article aria-label="Message 3" class="room-message" data-runtime-kind="claude-code">
        <strong class="room-message-sender">Researcher</strong>
        <code class="room-message-instance">·AAAA</code>
        <time datetime="2026-01-01T00:05:00.000Z"></time>
        <div class="room-message-content"><p>Agreed. I will follow up.</p></div>
      </article>
    </body>
  </html>
`;

test("validates only public SharedNet conversation URLs", () => {
  assert.equal(
    validateSharedNetUrl("https://www.sharednet.ai/s/shr_example").href,
    "https://www.sharednet.ai/s/shr_example"
  );
  assert.throws(() => validateSharedNetUrl("http://sharednet.ai/s/shr_example"), /Only HTTPS/);
  assert.throws(() => validateSharedNetUrl("https://example.com/s/shr_example"), /sharednet.ai/);
  assert.throws(() => validateSharedNetUrl("https://www.sharednet.ai/profile"), /public conversation/);
});

test("extracts messages and computes collaboration metrics", () => {
  const conversation = parseSharedNetHtml(fixture, "https://www.sharednet.ai/s/shr_example");
  const result = analyzeConversation(conversation);

  assert.equal(result.conversation.title, "Test room");
  assert.equal(result.metrics.totalMessages, 3);
  assert.equal(result.metrics.participantCount, 2);
  assert.equal(result.metrics.turnSwitchRate, 100);
  assert.equal(result.metrics.medianResponseLatencyMs, 150_000);
  assert.equal(result.metrics.questionFollowUpRate, 1);
  assert.equal(result.participants[0].messages, 2);
  assert.deepEqual(
    result.transitions.map(({ source, target, count }) => ({ source, target, count })),
    [
      { source: "Researcher AAAA", target: "Reviewer BBBB", count: 1 },
      { source: "Reviewer BBBB", target: "Researcher AAAA", count: 1 }
    ]
  );
  assert.equal(result.messages[1].signals.challenge, 2);
});

test("rejects pages without trace messages", () => {
  assert.throws(() => parseSharedNetHtml("<html><h1>Empty</h1></html>"), /No SharedNet messages/);
});

test("exports a stable Inspect Scout bridge without changing the report", () => {
  const report = analyzeConversation(
    parseSharedNetHtml(fixture, "https://www.sharednet.ai/s/shr_example")
  );
  const original = structuredClone(report);
  const bridge = buildScoutTranscript(report);

  assert.equal(bridge.bridgeVersion, "1.0");
  assert.equal(bridge.transcript_id, "shr_example");
  assert.equal(bridge.source_type, "sharednet");
  assert.equal(bridge.message_count, 3);
  assert.equal(bridge.messages[0].content, "Could you verify this result?");
  assert.deepEqual(bridge.messages[0].metadata, {
    participant_id: "Researcher AAAA",
    sender: "Researcher",
    instance: "AAAA",
    runtime: "claude-code",
    sequence: 1,
    timestamp: "2026-01-01T00:00:00.000Z",
    words: 5,
    questions: 1,
    signals: {
      agreement: 0,
      challenge: 0,
      coordination: 1
    }
  });
  assert.deepEqual(report, original);
});

test("rejects Scout export without messages", () => {
  assert.throws(() => buildScoutTranscript({ messages: [] }), /with messages is required/);
});
