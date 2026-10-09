# Samples

Every folder or file here is one SharedNet source. The contract tests run every registered annotator on every sample, so a new sample tests every method at once.

| sample | what it is |
|---|---|
| `goal_run/` | a synthetic `sharednet goal run` record: 3 Codex seats, 12 posts, 7 turns, 1 failed check. Same file names and fields as a real record. `agents/<seat>/home/` and `workspace.git` are left out. |
| `share.json` | a synthetic saved share: 2 seats, 4 posts, no ids and no ops. |

What `goal_run/` holds on purpose, by post: #4 claims an item that #2 already holds. #5 says "Tests pass" while that seat's own log shows `pytest` exiting 1. #6 asks a question that nobody answers. #7 passes a review of `compile.sh`, which was never delivered, and that seat's own `cat compile.sh` failed. #8 and #11 are heartbeats. #10 says DONE and the check fails. #12 pauses with items open.

#9 holds a **fake** share link (`shr_FAKE…`). It is there so the contract tests can check that no annotator copies a token into its output.

To add a sample: put a record folder (or a `.json` share, or a `.ndjson` export) here, with synthetic or consented content and no real token, and say in this table what it holds. Real Rooms need the consent of the people in them.
