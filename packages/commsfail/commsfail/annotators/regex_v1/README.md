# regex_v1

The reference annotator. Calibrated text patterns over the posts of one Room.

**Output:** `analysis.v1` ([schema.json](schema.json)). One entry for each of the ten modes (R1 R2 REP, B1 B2, D1 D2 D3 D4 HB), each with severity, count, confidence, the layer that removes it, and evidence rows `{seq, who, excerpt, why}`. Also room metrics, the work items found in the text, and empty slots for human labels.

**How:** it finds work items in the text (file names, backticked names, task ids), then follows each item through claims, "done" posts, reviews and uploads. It counts asks and whether a later post answers or cites them. It finds near-duplicate posts and "no change" status posts. It skips the goal post and the runner's check reports.

**Good at:** repetition (REP) and heartbeat cost (HB).

**Weak at:** anything that needs a judgment about silence (B1, D3, D4), and anything that needs a fact the source cannot show. On a share there are no artifact rows, so D1 is `unknown`. It does not read the seats' own logs yet, so a goal-run record does not make it smarter than a share. A record-based annotator should do that.

**Calibrated on:** SharedNet Rooms, in English and Chinese. Every evidence row is a pointer for a person to read, not a label.
