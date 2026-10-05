function transcriptId(report) {
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

export function buildScoutTranscript(report) {
  if (!report?.messages?.length) {
    throw new Error("A TraceScope report with messages is required.");
  }

  const id = transcriptId(report);

  return {
    bridgeVersion: "1.0",
    transcript_id: id,
    source_type: report.source?.provider || "tracescope",
    source_id: id,
    source_uri: report.source?.url || null,
    date: report.conversation?.firstTimestamp || null,
    task_set: "sharednet-conversation",
    task_id: id,
    agent: "multi-agent-room",
    message_count: report.metrics?.totalMessages ?? report.messages.length,
    total_time: report.metrics?.durationMs == null ? null : report.metrics.durationMs / 1000,
    messages: report.messages.map((message) => ({
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
        signals: message.signals
      }
    })),
    metadata: {
      tracescope_schema_version: report.schemaVersion,
      title: report.conversation?.title || "Untitled conversation",
      description: report.conversation?.description || null,
      participants: report.participants,
      metrics: report.metrics,
      transitions: report.transitions,
      structural_flags: report.failureModes
    }
  };
}
