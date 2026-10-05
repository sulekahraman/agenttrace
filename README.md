# TraceScope

A small local web app for turning a public SharedNet multi-agent conversation into an inspectable collaboration trace.

See [`METRICS.md`](METRICS.md) for exact formulas, counting rules, heuristic thresholds, and interpretation limitations.

## What it measures

- Conversation size, duration, words, and response latency
- Agent contribution share and balance
- Turn switching and directed agent-to-agent transitions
- Question follow-up within three turns
- Lexical agreement, challenge, and coordination signals
- Deterministic heuristic flags for dominance, sparse interaction, unresolved questions, challenge-heavy discourse, and high context load
- Message-level data export as JSON for downstream analysis
- Optional Inspect Scout export for semantic collaboration scanners

The heuristic signals are research prompts, not judgments of task quality or causal claims about collaboration.

## Run locally

```bash
npm install
npm start
```

Open `http://localhost:3000`, paste a public `https://www.sharednet.ai/s/...` link, and select **Analyze trace**.

For development:

```bash
npm run dev
npm test
```

The React UI uses Observable Plot for the timeline, contribution chart, and transition matrix. Linked filters support agent selection, turn ranges, transition selection, text search, and expandable messages. Summary cards, failure-mode prompts, and the message explorer use native HTML.

## Inspect Scout bridge

After analyzing a trace, select **Export for Scout** to download a stable bridge
record. The optional files in [`scout/`](scout/) import that record into a local
Inspect Scout transcript database and provide starter scanners for:

- Duplicated work
- Weak or failed handoffs
- Relevant information that was not integrated

See [`scout/README.md`](scout/README.md) for setup and commands. Scout findings
are semantic model judgments and should be validated against human labels
before being used as research measures.

## Current scope

The importer intentionally accepts only public SharedNet conversation links. It validates redirect targets, limits response size, and applies a timeout before parsing the server-rendered message log. The analysis schema includes source metadata, conversation metadata, aggregate metrics, participants, transition edges, failure-mode hypotheses, and normalized messages.

For larger studies, persist exported records by `schemaVersion`, add provider adapters that produce the same normalized message shape, and compute cohort-level distributions separately from this per-trace explorer.
