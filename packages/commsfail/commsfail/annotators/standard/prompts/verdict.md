The failure incidents of this run are final, and you may not change them. You now see the grade.

Your current directory holds the run (`codebook.md`, `task.md`, `timeline.md`, `workspace.md`, `agents/` when there are logs), `final.json` (the final incidents), and `grade.json` (the grade: each rubric item, its weight, its score from 0 to 100, and the grader's reasoning).

For each rubric item that lost points (score below 100), say what caused the loss, using the grader's reasoning and the run. The cause is one or more of:
- `incident`: one or more incidents of `final.json`, by id;
- `capability`: the agreed work was done, and it is weak or wrong;
- `collective_judgement`: the team agreed on a poor choice;
- `task_data`: the data the task gives cannot support the item;
- `harness`: the run's mechanics, for example the run ended before the work did;
- `grader`: the grade does not match what the run produced.

Then say whether the communication failures explain the score ("no", "partly", or "yes"), and write a summary of two to four sentences.

Reply with ONLY one JSON object, no prose:
{"items": [{"index": 0, "score": 0, "weight": 0.4,
   "causes": [{"kind": "collective_judgement", "incidents": [], "note": "..."}]}],
 "explains_score": "no", "summary": "..."}
