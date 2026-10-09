You are the judge for the annotation of one run of a team of AI agents that coordinated through a shared message board.

Your current directory holds the run, as the annotators saw it (`codebook.md`, `task.md`, `timeline.md`, `workspace.md`, and `agents/` when there are logs), and three more files:
- `A.json` and `B.json`: two independent annotations of the run.
- `agreement.json`: the pairs of incidents, one from A and one from B, that look like the same failure, and the incidents left unpaired.

Read the codebook and the timeline, then both annotations. Each annotation has a `sweep`, a note on every post. Where one annotator found a gap at a post and the other found none, look at that post yourself. Produce the final record:
- For each pair: if both describe the same failure, keep ONE incident. Use decision "agreed" when class and severity agree; otherwise use "merged", with the class and severity the evidence supports. Set `from` to both ids, e.g. ["A:I1", "B:I2"].
- For each unpaired incident: check it against the timeline and the logs. Either keep it (decision "kept", `from`: ["A:I3"]), or reject it in `rejected` with a reason.
- Reject an incident only when the evidence shows there was no gap: for example, its acting agent had in fact received the post, or the claim it calls ungrounded was attested. A gap that was repaired is still a failure: keep it with `repaired: true` and the severity the codebook gives it, often 1. A rejection's reason must say why there was no gap, citing the post or action that shows it. "It did no harm", "the required work was present", "the check passed", and "the agent followed the task" are reasons for a low severity, never for rejecting.
- Two incidents are the same failure only if they share the anchor AND the cause. If they differ in either, they are separate failures: keep both, even when they concern the same piece of work. Never reject an incident as a duplicate of one with a different anchor or a different consequence.
- Change a severity only by naming the codebook condition the evidence meets. A passing check shows only what the check tests (the top of `timeline.md` says what it tests), not that the work is complete; the required parts are the deliverables and the outputs `task.md` names.
- You may correct a kept incident (decision "adjusted"), or add one that both missed (decision "added", `from`: []). Do either only with evidence you cite.
- Every incident of A and of B must appear exactly once: in the `from` of one final incident, or in `rejected`.
- Each final incident has every field an annotator gives (posts, anchor, actions, class, pattern, class_reason, cause, consequence, severity, severity_reason, repaired, source, confidence, items), plus `decision`, `from`, and `judge_reason`. `severity_reason` begins with the level, "3: ...", as the annotators were told. Number the final incidents I1, I2, and so on.
- `items`: one list for the run. Rename the annotators' items consistently and use the new ids in the incidents. `undecidable`: as the annotators were told.

You do not see the grade. Do not change any file.

Reply with ONLY one JSON object, no prose (the final record has no `sweep`):
{"items": [...], "incidents": [...], "rejected": [{"from": "B:I4", "reason": "..."}], "undecidable": []}
