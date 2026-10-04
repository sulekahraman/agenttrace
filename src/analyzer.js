const SIGNALS = {
  agreement: /\b(agree|agreed|accept|accepted|correct|good point|makes sense|yes)\b/gi,
  challenge: /\b(disagree|however|but|concern|issue|problem|wrong|fail(?:ed|ure)?|critique|attack)\b/gi,
  coordination: /\b(please|could you|can you|need your|next step|action item|follow[- ]?up|owner|assign)\b/gi
};

function countMatches(text, pattern) {
  return [...text.matchAll(pattern)].length;
}

function wordCount(text) {
  return text.match(/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu)?.length || 0;
}

function round(value, digits = 1) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2;
}

function gini(values) {
  if (!values.length || values.every((value) => value === 0)) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const total = sorted.reduce((sum, value) => sum + value, 0);
  const weighted = sorted.reduce((sum, value, index) => sum + (index + 1) * value, 0);
  return (2 * weighted) / (sorted.length * total) - (sorted.length + 1) / sorted.length;
}

function buildParticipants(messages) {
  const participants = new Map();

  for (const message of messages) {
    const current = participants.get(message.participantId) || {
      id: message.participantId,
      sender: message.sender,
      instance: message.instance,
      runtime: message.runtime,
      messages: 0,
      words: 0,
      questions: 0,
      agreement: 0,
      challenge: 0,
      coordination: 0
    };
    current.messages += 1;
    current.words += message.words;
    current.questions += message.questions;
    current.agreement += message.signals.agreement;
    current.challenge += message.signals.challenge;
    current.coordination += message.signals.coordination;
    participants.set(message.participantId, current);
  }

  return [...participants.values()].sort((a, b) => b.messages - a.messages || b.words - a.words);
}

function buildTransitions(messages) {
  const edges = new Map();
  let switches = 0;

  for (let index = 1; index < messages.length; index += 1) {
    const source = messages[index - 1].participantId;
    const target = messages[index].participantId;
    if (source === target) continue;
    switches += 1;
    const key = `${source}\u0000${target}`;
    const edge = edges.get(key) || { source, target, count: 0 };
    edge.count += 1;
    edges.set(key, edge);
  }

  return {
    edges: [...edges.values()].sort((a, b) => b.count - a.count),
    switches
  };
}

function buildFailureModes(metrics, participants, transitions, messages) {
  const flags = [];
  const top = participants[0];
  const totalMessages = metrics.totalMessages || 1;
  const possibleDirectedEdges = participants.length * Math.max(participants.length - 1, 1);
  const density = possibleDirectedEdges ? transitions.edges.length / possibleDirectedEdges : 0;
  const challengeCount = messages.reduce((sum, message) => sum + message.signals.challenge, 0);
  const agreementCount = messages.reduce((sum, message) => sum + message.signals.agreement, 0);

  if (top && top.messages / totalMessages >= 0.4) {
    flags.push({
      id: "dominance",
      severity: "high",
      title: "Contribution dominance",
      detail: `${top.id} produced ${round((top.messages / totalMessages) * 100)}% of all messages.`,
      threshold: "Triggered when one agent produces at least 40% of messages.",
      evidence: "A high share can indicate coordinator bottlenecks or weak participation."
    });
  }

  if (participants.length > 2 && density < 0.35) {
    flags.push({
      id: "siloing",
      severity: density < 0.2 ? "high" : "medium",
      title: "Sparse transition matrix",
      detail: `Only ${round(density * 100)}% of possible directed agent transitions occurred.`,
      threshold: "Triggered when fewer than 35% of possible directed transitions occur.",
      evidence: "Some agents may be communicating through a hub rather than with each other."
    });
  }

  if (metrics.questionFollowUpRate < 0.6 && metrics.questionMessages >= 5) {
    flags.push({
      id: "unresolved-questions",
      severity: "medium",
      title: "Questions may be going unresolved",
      detail: `${round((1 - metrics.questionFollowUpRate) * 100)}% of question messages had no other-agent reply within three turns.`,
      threshold: "Triggered when at least five question messages exist and fewer than 60% receive a near-term follow-up.",
      evidence: "This is a turn-taking proxy; it does not judge whether a reply actually answered the question."
    });
  }

  if (challengeCount > agreementCount * 1.5 && challengeCount >= 10) {
    flags.push({
      id: "conflict",
      severity: "medium",
      title: "Challenge-heavy discourse",
      detail: `${challengeCount} challenge markers versus ${agreementCount} agreement markers.`,
      threshold: "Triggered at 10 or more challenge markers and 1.5 times the agreement-marker count.",
      evidence: "Productive critique and unproductive conflict cannot be separated without semantic evaluation."
    });
  }

  if (metrics.p95WordsPerMessage >= 900) {
    flags.push({
      id: "context-load",
      severity: "medium",
      title: "High context load",
      detail: `The 95th percentile message is ${metrics.p95WordsPerMessage} words.`,
      threshold: "Triggered when the 95th percentile message length is at least 900 words.",
      evidence: "Long messages can hide decisions and increase context-window and attribution errors."
    });
  }

  if (!flags.length) {
    flags.push({
      id: "none",
      severity: "low",
      title: "No strong structural flag",
      detail: "The deterministic thresholds did not identify a strong failure-mode signal.",
      threshold: "No configured threshold was crossed.",
      evidence: "This does not imply the collaboration was successful; inspect the transcript and task outcome."
    });
  }

  return flags;
}

function percentile(values, percentileValue) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil(percentileValue * sorted.length) - 1);
  return sorted[index];
}

export function analyzeConversation(conversation) {
  const messages = conversation.messages.map((message) => ({
    ...message,
    words: wordCount(message.text),
    characters: message.text.length,
    questions: (message.text.match(/\?/g) || []).length,
    signals: {
      agreement: countMatches(message.text, SIGNALS.agreement),
      challenge: countMatches(message.text, SIGNALS.challenge),
      coordination: countMatches(message.text, SIGNALS.coordination)
    }
  }));
  if (!messages.length) {
    throw new Error("The conversation does not contain any messages.");
  }

  const participants = buildParticipants(messages);
  const transitions = buildTransitions(messages);
  const totalWords = messages.reduce((sum, message) => sum + message.words, 0);
  const firstTime = messages.find((message) => message.timestamp)?.timestamp;
  const lastTime = [...messages].reverse().find((message) => message.timestamp)?.timestamp;
  const durationMs = firstTime && lastTime ? Math.max(0, new Date(lastTime) - new Date(firstTime)) : null;
  const latencies = [];
  let questionMessages = 0;
  let followedQuestions = 0;

  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index];
    if (message.questions > 0) {
      questionMessages += 1;
      const hasFollowUp = messages.slice(index + 1, index + 4)
        .some((candidate) => candidate.participantId !== message.participantId);
      if (hasFollowUp) followedQuestions += 1;
    }

    if (index > 0 && message.participantId !== messages[index - 1].participantId) {
      const previousTimestamp = messages[index - 1].timestamp;
      if (previousTimestamp && message.timestamp) {
        const latency = new Date(message.timestamp) - new Date(previousTimestamp);
        if (latency >= 0) latencies.push(latency);
      }
    }
  }

  const messageCounts = participants.map((participant) => participant.messages);
  const metrics = {
    totalMessages: messages.length,
    participantCount: participants.length,
    totalWords,
    averageWordsPerMessage: round(totalWords / messages.length),
    p95WordsPerMessage: percentile(messages.map((message) => message.words), 0.95),
    durationMs,
    contributionBalance: round((1 - gini(messageCounts)) * 100),
    turnSwitchRate: messages.length > 1 ? round((transitions.switches / (messages.length - 1)) * 100) : 0,
    medianResponseLatencyMs: median(latencies),
    questionMessages,
    questionFollowUpRate: questionMessages ? followedQuestions / questionMessages : 1,
    links: messages.reduce((sum, message) => sum + message.links, 0),
    codeBlocks: messages.reduce((sum, message) => sum + message.codeBlocks, 0)
  };

  return {
    schemaVersion: "1.0",
    source: {
      ...conversation.source,
      analyzedAt: new Date().toISOString()
    },
    conversation: {
      title: conversation.title,
      description: conversation.description,
      firstTimestamp: firstTime || null,
      lastTimestamp: lastTime || null
    },
    metrics,
    participants,
    transitions: transitions.edges,
    failureModes: buildFailureModes(metrics, participants, transitions, messages),
    messages
  };
}
