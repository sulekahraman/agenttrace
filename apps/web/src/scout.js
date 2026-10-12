function transcriptId(report) {
  if (report?.traceId) return report.traceId;
  const sourceUrl = report?.source?.url;
  if (sourceUrl) {
    try {
      const match = new URL(sourceUrl).pathname.match(/^\/s\/([^/]+)/);
      if (match) return match[1];
    } catch {
      // Fall through to the deterministic report-based identifier.
    }
  }

  const title = report?.conversation?.title || "untitled";
  const firstTimestamp = report?.conversation?.firstTimestamp || "unknown-date";
  return `${title}:${firstTimestamp}`.toLowerCase().replace(/[^a-z0-9:._-]+/g, "-");
}

function unique(values) {
  return [...new Set(values)];
}

function extractCitations(text, targetIndex, validIndexes) {
  const citations = [];
  const pattern = /(?:#|\[M)(\d+)\]?/gi;
  for (const match of text.matchAll(pattern)) {
    const index = Number(match[1]);
    if (index < targetIndex && validIndexes.has(index)) citations.push(index);
  }
  return unique(citations).slice(0, 6);
}

function extractArtifacts(text) {
  return unique(
    [...text.matchAll(/\b(?:art|shr|run|tool|file)_[A-Za-z0-9_-]+\b/g)]
      .map((match) => match[0])
  );
}

function extractAddressedAgents(text, participants, currentParticipantId) {
  const addressed = [];
  for (const participant of participants) {
    if (participant.id === currentParticipantId) continue;
    const names = [participant.instance, participant.sender]
      .filter((name) => name && name.length >= 3);
    if (names.some((name) => text.toLowerCase().includes(name.toLowerCase()))) {
      addressed.push(participant.id);
    }
  }
  return unique(addressed);
}

function annotationContext(report, messagePosition) {
  const message = report.messages[messagePosition];
  const validIndexes = new Set(report.messages.map((candidate) => candidate.index));
  const citations = extractCitations(message.text, message.index, validIndexes);
  const byIndex = new Map(report.messages.map((candidate) => [candidate.index, candidate]));
  const summarize = (candidate, limit) => ({
    index: candidate.index,
    participant_id: candidate.participantId,
    timestamp: candidate.timestamp,
    text: candidate.text.slice(0, limit)
  });

  return {
    guide_version: "1.0",
    roster: report.participants.map((participant) => ({
      id: participant.id,
      sender: participant.sender,
      instance: participant.instance,
      runtime: participant.runtime
    })),
    cited_messages: citations
      .map((index) => byIndex.get(index))
      .filter(Boolean)
      .map((candidate) => summarize(candidate, 2_000)),
    previous_messages: report.messages
      .slice(Math.max(0, messagePosition - 12), messagePosition)
      .map((candidate) => summarize(candidate, 500)),
    hints: {
      cites: citations,
      addressed_to: extractAddressedAgents(
        message.text,
        report.participants,
        message.participantId
      ),
      artifacts: extractArtifacts(message.text),
      heartbeat: /^\s*(?:heartbeat|ping|still working|working on it|status update|no update)\b/i
        .test(message.text)
    }
  };
}

export function buildScoutTranscript(report) {
  if (!report?.messages?.length) {
    throw new Error("An AgentTrace report with messages is required.");
  }

  const id = transcriptId(report);

  return {
    bridgeVersion: "1.0",
    transcript_id: id,
    source_type: report.source?.kind || report.source?.provider || "agenttrace",
    source_id: id,
    source_uri: report.source?.url || null,
    date: report.conversation?.firstTimestamp || null,
    task_set: "sharednet-conversation",
    task_id: id,
    agent: "multi-agent-room",
    message_count: report.metrics?.totalMessages ?? report.messages.length,
    total_time: report.metrics?.durationMs == null ? null : report.metrics.durationMs / 1000,
    messages: report.messages.map((message, position) => ({
      role: "assistant",
      content: message.text,
      metadata: {
        participant_id: message.participantId,
        sender: message.sender,
        instance: message.instance,
        runtime: message.runtime,
        sequence: message.index,
        timestamp: message.timestamp,
        words: message.words,
        questions: message.questions,
        signals: message.signals,
        annotation_context: annotationContext(report, position)
      }
    })),
    metadata: {
      agenttrace_schema_version: report.schemaVersion,
      title: report.conversation?.title || "Untitled conversation",
      description: report.conversation?.description || null,
      participants: report.participants,
      metrics: report.metrics,
      transitions: report.transitions,
      structural_flags: report.failureModes
    }
  };
}
