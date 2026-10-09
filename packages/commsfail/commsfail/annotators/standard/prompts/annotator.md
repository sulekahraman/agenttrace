You are annotating one run of a team of AI agents that coordinated through a shared message board. Find every communication failure in the run and record each one precisely.

Your current directory holds the run, prepared for you:
- `codebook.md`: the six classes, the patterns, the severity scale, and the rule that classes a failure. Read it first.
- `task.md`: the task the team was given.
- `workspace.md`: the files in the shared workspace at the end, and the team's report, when the record has them. Use it to judge what a failure did to the work.
- `timeline.md`: every post and every turn boundary, in time order. Each agent post says what its author had received when it posted.
- `agents/<seat>.md`: each agent's own actions (commands, file changes, reads of the board, posts), with ids like `codex-2:3:10`. Present only when the run has agent logs (evidence level E3).

You do not see the grade, and you must not guess it. Do not change any file.

How to work:
1. Read `codebook.md`, `task.md` and `timeline.md` in full, then every file in `agents/`.
2. List the pieces of work the run named or the task required, as items `W1`, `W2`, and so on.
3. Sweep the timeline post by post; do not skim. For every agent post, ask the codebook's questions of it: had its author received the posts it needed ("had received up to")? Does it claim, assign, or declare something that other posts, the logs, or `workspace.md` contradict? Does it read an earlier post in a way that post does not say? Does it leave a request, an ask, or a piece of work without an owner or an answer? Busy runs have many small gaps, often several in the first few posts; record each one. Then, for each agent in `agents/`, check every file it changed: was the change announced on the board, and did it overwrite a teammate's work?
   Find every point where two states of the run stopped agreeing. Record each as ONE incident, whether it spans one post or many.
4. For each incident, give:
   - `posts`: every post involved, in order, as numbers. `anchor`: the post at which the gap opened, which is the first step that broke. For something never said or never owned, anchor at the earliest post where a careful agent could have closed the gap.
   - `actions`: the agents' actions that show it, by id from `agents/*.md`; `[]` if none or if there are no logs.
   - `class`: ask the six questions of the codebook in order; the class is the first answered "no". `class_reason`: say which earlier steps held and which one broke, with evidence (post numbers, "had received up to Pn", action ids).
   - `pattern`: the codebook id that fits, or `NEW:<short_name>`.
   - `cause`: the mechanism that produced the gap, separate from the class; for example "codex-1 did not read the board during its turn while codex-3 was posting".
   - `consequence`: what it did to the team's work.
   - `severity`: 1 to 5, by what happened to the work (codebook scale). `severity_reason`: begin with the level, "3: ...", and name the condition it meets.
   - `repaired`: whether a later post or action closed the gap. `source`: "agents", or "harness" when the runner caused it. `confidence`: low, medium, or high. `items`: the items it concerns.
5. Look hard at how the run ended. The top of `timeline.md` says how the runner ends a run. First decide whether the post that ended the run meant to declare the work done. If it did, its author chose to end the run: the source is "agents", and you class it like any other post, by the codebook's questions (for example, ask whether its author had received every teammate's post about work still in progress). If it did not mean that, and the runner ended the run anyway, the source is "harness". Then, for every turn cut by the end, read what that agent was doing in `agents/`, and check whether that work reached `workspace.md`. A post that ended the run while required work was still running is an incident: anchor it at the post that ended the run, and rate it by what the cut work would have delivered.
6. Rate severity from the work, literally by the codebook's conditions. The required parts are the deliverables and the outputs `task.md` names; a passing check shows only what the check tests, not that the work is complete. Then: a crossed claim sorted out within the next exchange is 1, one that cost a redo is 2 or 3, and a failure that left a part the task requires missing or wrong in `workspace.md` is 4.
7. Whether something is an incident depends only on whether two states disagreed, never on whether it did harm. A wrong fact posted and corrected two posts later, a claim crossed with another and sorted out at once, a post that says a teammate did something it did not: each is an incident, at severity 1 if nothing was lost. Harm goes in `severity`, not in the decision to record. If your note on a post mentions a correction, a contradiction, an overlap, or a misunderstanding, that post belongs to an incident. Do not record overhead (posts that change no state, such as repeats).
8. Check before you write. An unreceived incident must involve a post that its acting agent had NOT received: look at "had received up to" in `timeline.md` and at the agent's reads in `agents/`.
9. If the evidence level is below E3, put "unsaid" in `undecidable` and report no unsaid incidents.
10. Write the sweep: one entry for every agent post, `{"post": 7, "incidents": ["I2"], "note": "..."}`. `incidents` names every incident whose posts include this post ([] if none); `note` says in a few words what you checked, for example "claims the audit; had received up to P1, P2 also claims it".

Reply with ONLY one JSON object, no prose before or after it, in this shape:

{"items": [{"id": "W1", "name": "report/report.md", "required_by": 1}],
 "incidents": [{"id": "I1", "posts": [24, 25], "anchor": 25, "actions": ["codex-2:3:7"],
   "class": "unreceived", "pattern": "crossed_posts",
   "class_reason": "1 holds: ... 2 fails: ...", "cause": "...", "consequence": "...",
   "severity": 3, "severity_reason": "3: ...", "repaired": false, "source": "agents",
   "confidence": "high", "items": ["W1"]}],
 "undecidable": [],
 "sweep": [{"post": 2, "incidents": [], "note": "..."}]}
