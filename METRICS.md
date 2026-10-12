# Metric Definitions

AgentTrace metrics are deterministic and computed in Python from a canonical
`commsfail.Trace`, ordered by original sequence number. Non-message events and
goal/runner posts are excluded from UI metrics but retained in the raw trace.
Metrics describe conversation structure, not answer correctness, task success
or causal collaboration quality.

## Message-Level Fields

### Words

The number of Unicode letter-or-number tokens in a message. Internal apostrophes and hyphens remain part of a token.

Examples:

- `multi-agent` counts as one word.
- `agent's` counts as one word.
- Punctuation by itself does not count.

### Characters

UTF-16 code units in the message text, preserving the original JavaScript
string-length convention. An emoji outside the basic multilingual plane
counts as two units.

### Questions

The number of `?` characters in the message. This is punctuation-based and does not determine whether the sentence is semantically a question.

### Links

The number of `https?://` URL spans in the canonical message text. This is a
text estimate, not an HTML anchor count.

### Code Blocks

The number of fenced Markdown code spans or inline backtick spans in the
canonical text. This includes inline code and is not an HTML element count.

### Agreement Markers

The number of case-insensitive lexical matches for:

```text
agree, agreed, accept, accepted, correct, good point, makes sense, yes
```

### Challenge Markers

The number of case-insensitive lexical matches for:

```text
disagree, however, but, concern, issue, problem, wrong,
fail, failed, failure, critique, attack
```

### Coordination Markers

The number of case-insensitive lexical matches for:

```text
please, could you, can you, need your, next step, action item,
follow-up, follow up, owner, assign
```

Lexical markers can occur in quotations, examples, or negated statements. They are useful for trace triage but are not semantic classifications.

## Conversation Metrics

### Total Messages

The number of normalized messages in the conversation:

```text
total_messages = count(messages)
```

### Participant Count

The number of unique participant identifiers. An identifier combines the
display label and full canonical handle when they differ:

```text
participant_id = label + " " + handle
```

Otherwise the handle is used directly. This keeps separate instances distinct.
The former HTML importer used short instance suffixes; do not equate those
identifiers with full canonical handles without an explicit mapping.

### Total Words

The sum of message word counts:

```text
total_words = sum(message.words)
```

### Average Words per Message

```text
average_words_per_message = total_words / total_messages
```

The displayed value is rounded to one decimal place.

### 95th-Percentile Message Length

Message word counts are sorted in ascending order. AgentTrace uses the nearest-rank value:

```text
index = ceil(0.95 * total_messages) - 1
p95_words_per_message = sorted_word_counts[index]
```

### Conversation Duration

The elapsed time between the first timestamped message and the last timestamped message:

```text
duration = last_message_timestamp - first_message_timestamp
```

This is wall-clock span, not active working time. Long pauses are included.

### Contribution Balance

Contribution balance is based on message counts per participant:

```text
contribution_balance = (1 - gini(message_counts)) * 100
```

- `100%` means every participant sent the same number of messages.
- Lower values indicate a less even distribution.
- It measures message-count equality, not equality of words, influence, or useful work.

### Turn Switch Rate

The percentage of adjacent message pairs authored by different participants:

```text
turn_switch_rate =
  different_author_adjacent_pairs / (total_messages - 1) * 100
```

A high value indicates frequent alternation. It does not establish that messages directly respond to each other.

### Median Response Gap

For every adjacent pair authored by different participants, AgentTrace calculates:

```text
gap = current_message_timestamp - previous_message_timestamp
```

Negative gaps and pairs with missing timestamps are excluded. The metric is the median of the remaining gaps.

This is a turn-transition timing measure, not a semantic response-time measure. It includes periods when agents may not have been actively working.

### Question Messages

The number of messages containing at least one `?` character.

### Question Follow-Up Rate

For each question message, AgentTrace inspects the next three messages. A follow-up occurs if at least one was authored by another participant:

```text
question_follow_up_rate =
  question_messages_with_other_agent_in_next_3_turns / question_messages
```

If there are no question messages, the rate is defined as `100%`.

This metric does not determine whether the question was answered, understood, or resolved.

### Total Links

The sum of link counts across all messages.

### Total Code Blocks

The sum of fenced and inline code-span counts across all messages.

## Participant Metrics

Each participant summary contains:

- `messages`: messages authored by the participant
- `words`: words authored by the participant
- `questions`: question marks in the participant's messages
- `agreement`: agreement-marker matches
- `challenge`: challenge-marker matches
- `coordination`: coordination-marker matches

Participant ordering is descending by message count, then descending by word count.

## Transition Metrics

A directed transition is recorded when two consecutive messages have different authors:

```text
source = previous_message.participant_id
target = current_message.participant_id
```

The transition count is the number of times each directed pair occurs. Consecutive messages from the same participant are excluded.

Transitions describe turn order. They do not prove direct replies, information transfer, or social influence.

## Failure-Mode Heuristics

Failure-mode labels are transparent prompts for investigation, not verdicts.

### Contribution Dominance

Triggered when one participant authors at least 40% of all messages.

### Sparse Transition Matrix

First calculate directed transition density:

```text
density =
  observed_directed_pairs / (participant_count * (participant_count - 1))
```

For traces with more than two participants, triggered when density is below
35%. Severity is high below 20% and medium otherwise.

### Questions May Be Going Unresolved

Triggered when:

- At least five question messages exist, and
- The question follow-up rate is below 60%.

### Challenge-Heavy Discourse

Triggered when:

- At least 10 challenge markers occur, and
- Challenge markers exceed 1.5 times the agreement-marker count.

### High Context Load

Triggered when the 95th-percentile message length is at least 900 words.

## Interpretation Principles

1. Compare metrics only when trace collection and participant identity rules are consistent.
2. Inspect message-level evidence before assigning a failure mode.
3. Do not interpret lexical signals as sentiment or intent.
4. Do not treat transition counts as reply edges without explicit reply metadata.
5. Do not treat balanced participation as evidence of productive collaboration.
6. Pair structural metrics with task outcomes and human or validated semantic annotations when making research claims.
