# Multi-Agent Trace Analysis: MVP Design

## Goal

Build a simple research tool that turns a public multi-agent conversation link into an inspectable collaboration trace.

The MVP should help researchers understand:

- How much each agent contributes
- How agents take turns and interact
- How information flows through the group
- Which conversations may contain structural collaboration failures
- What normalized data can be exported for later dataset-level analysis

The tool analyzes one conversation at a time. Large-scale storage and cohort analysis are intentionally deferred.

## User Flow

1. Paste a public multi-agent conversation URL.
2. Select **Analyze**.
3. View a report containing:
   - Basic conversation statistics
   - Agent contribution breakdown
   - Turn-by-turn timeline
   - Agent transition matrix
   - Searchable message list
4. Export normalized JSON for downstream research.

## Architecture

```text
SharedNet source adapter
        |
        v
Normalized conversation
        |
        v
Pure deterministic metric functions
        |
        v
Versioned report object
        |
        +-- React: interaction state and linked filtering
        +-- Observable Plot: timeline, contributions, transition matrix
        +-- Native HTML: summary cards, flags, message explorer
        |
        v
Unchanged JSON export
```

Provider-specific parsing is kept separate from normalization and metric computation. Supporting another conversation platform should only require a new parser that produces the same normalized model.

## Technology and Scope

Use the smallest practical implementation:

- Node.js HTTP server
- React for the browser UI and linked exploration state
- Plain CSS
- Cheerio for parsing server-rendered HTML
- Observable Plot for all charts
- Vite for resolving and bundling the browser dependency
- Native HTML for summary cards and the searchable message table

The MVP will not include:

- A database
- Authentication
- LLM-based classification
- Cytoscape.js
- Tabulator
- Batch processing
- Cross-conversation comparisons
- A router or external state-management library

Cytoscape.js can be added later if interactive graph exploration proves useful. Tabulator can be added later if traces become too large or the explorer needs sorting, pagination, or spreadsheet-like behavior.

## Normalized Data Model

```js
{
  conversation: {
    title,
    sourceUrl,
    startedAt,
    endedAt
  },
  agents: [
    {
      id,
      name,
      runtime
    }
  ],
  messages: [
    {
      index,
      agentId,
      timestamp,
      text,
      wordCount
    }
  ]
}
```

Derived metrics and visualizations should consume this normalized representation rather than provider-specific HTML.

## Initial Metrics

The first version will compute:

- Number of agents
- Number of messages
- Conversation duration
- Total and average message word counts
- Messages and words per agent
- Contribution balance
- Agent switching rate
- Median response gap
- Directed turn transitions between agents
- Message-length distribution
- Questions followed by another agent within a small number of turns

Question follow-up is a structural proxy. It does not establish that a question was understood or answered correctly.

Exact formulas, lexical dictionaries, thresholds, and interpretation limitations are documented in [`METRICS.md`](METRICS.md).

## Visualizations

### Summary Cards

Show the headline metrics for quick comparison and inspection.

### Turn Timeline

Render one colored mark per message:

- Color identifies the agent.
- Position identifies turn order.
- Height identifies relative message length.

### Contribution Breakdown

Use an Observable Plot horizontal bar chart to show messages contributed by each agent. Agent word totals remain available in chart tooltips and the exported report.

### Transition Matrix

Use an Observable Plot heatmap in which:

- Rows identify the source agent.
- Columns identify the next agent.
- Cell color and label identify the transition count.

The matrix is stable across renders, exposes exact counts, and is easier to compare across traces than a force-directed graph. A transition is based on consecutive turns and does not prove that one agent directly responded to another.

### Message Explorer

Provide a searchable table containing:

- Turn number
- Agent
- Message length
- Question count
- Structural signals
- Message excerpt

The explorer provides raw evidence behind aggregate metrics and heuristic flags.

## Linked Exploration

React owns a small shared filter state:

```js
{
  query,
  selectedAgents,
  turnStart,
  turnEnd,
  transition
}
```

The interface supports:

- Toggling agents from filter chips or the contribution chart
- Clicking a timeline bar to isolate a turn
- Selecting a transition-matrix cell to show matching consecutive turns
- Filtering by an inclusive turn range
- Searching agents and message content
- Expanding individual messages
- Resetting all filters

Charts continue to render the original deterministic aggregates. Filters highlight chart marks and select message-level evidence; the browser does not recompute research metrics.

## Layout

The analysis workspace uses the full browser width with responsive gutters. Large screens show contribution and transition views side by side, while narrow screens collapse to a single column.

## Failure-Mode Heuristics

The MVP may surface transparent, deterministic flags such as:

- One agent dominates the conversation.
- Interaction is concentrated through one agent.
- Questions receive no near-term response from another agent.
- Messages are unusually long.
- Extended runs occur without agent switching.

Each flag must expose:

- The measured value
- The threshold that triggered it
- The messages or agents involved
- A limitation explaining what the heuristic cannot establish

These flags are investigation prompts, not conclusions that collaboration failed.

## Export

The report can be exported as versioned JSON containing:

- Source metadata
- Normalized conversation data
- Agent summaries
- Aggregate metrics
- Transition edges
- Triggered heuristic flags

The export should preserve enough message-level information to reproduce every deterministic metric.

The downloaded file must be the exact report object returned by the analysis API. The browser must not recalculate or mutate report metrics for export.

## Phase 2: Semantic Analysis Bridge

Phase 2 remains optional and does not change the deterministic report. The
browser can derive a versioned Inspect Scout bridge record from the report and
download it separately.

The bridge preserves:

- Stable transcript and source identifiers
- Ordered message text
- Agent identity, runtime, turn number, and timestamp
- Deterministic message metrics and lexical signals
- Conversation metrics, transitions, and structural flags as metadata

A small Python importer converts the bridge into a local Inspect Scout
transcript database. Starter scanners inspect duplicated work, weak handoffs,
and visible information that was not integrated. These are semantic model
judgments and require human-labeled validation before use as research metrics.

Phase 2 does not add model calls to the TraceScope server or browser. API keys,
scanner execution, result storage, and validation stay in the separate Scout
environment.

## Future Scaling Path

Large-scale analysis should reuse the normalized model and metric functions:

```text
URL collection
  -> normalized JSON or JSONL
  -> batch metric computation
  -> cohort-level distributions
  -> condition and failure-mode comparisons
```

Potential later capabilities include:

- Batch URL ingestion
- Persistent trace storage
- Dataset and experiment identifiers
- Cross-conversation comparisons
- Statistical distributions by model, task, or training condition
- Semantic communication analysis
- Human annotation and validation of failure-mode labels

These capabilities should not add complexity to the single-trace MVP until the normalized schema and initial metrics are validated on real research data.

## Design Principles

1. Keep provider ingestion separate from analysis.
2. Prefer deterministic and reproducible metrics.
3. Make every heuristic transparent and inspectable.
4. Preserve raw evidence behind aggregate results.
5. Avoid causal or quality claims that the available data cannot support.
6. Keep the MVP useful without introducing infrastructure needed only for future scale.
7. Normalize once, aggregate once, and render every view from the same report object.
