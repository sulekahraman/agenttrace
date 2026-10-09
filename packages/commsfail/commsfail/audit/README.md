# audit

Human labels for boards, made so they can be trusted:
- Two people label the same posts without seeing where they came from.
- Agreement is measured per label with Cohen's kappa.
- Every disagreement is settled by adjudication.
- The result is a gold file. You can score annotators against it, and use it as training data.

## The steps

```bash
# 1. pick a codebook and read its definitions
commsfail audit codebook                      # modes_v1, discourse_v1, and every taxonomy choice
commsfail audit codebook state_gap:groups     # a choice by class (six labels); state_gap alone labels its patterns

# 2. export: one row per agent post, shuffled. Keep the salt and the key to yourself.
commsfail audit export runs/ep-001 runs/ep-002 --salt "$STUDY_SALT" --out blind.jsonl --key key.jsonl

# 3. two annotators each copy blind.jsonl and fill in every row: labels, uncertain, note

# 4. compare: kappa per label, and the rows to adjudicate
commsfail audit compare a.jsonl b.jsonl --report report.json --adjudicate todo.jsonl

# 5. a third person, or both annotators together, fills in labels in todo.jsonl, with nothing left uncertain

# 6. finalize: gold labels, with the source of each row restored from the key
commsfail audit finalize a.jsonl b.jsonl --adjudicated todo.jsonl --key key.jsonl --out gold.jsonl
```

## What an annotator fills in

Each row is one post. It shows the post, its author's handle, the handles it addresses and the posts before it. Use `--context N` to show only the last N posts before it.

```json
{"labels": ["D1"], "uncertain": ["D2"], "note": "claims tests pass; nothing on the board shows a run"}
```

- `labels`: every label in `choices` that the post shows. Write `[]` for none.
- `uncertain`: the labels you cannot decide from what the row shows. They are left out of kappa and always adjudicated.
- `note`: the items you mean, such as file names or task ids, and anything the adjudicator should know.

Change nothing else. Each row carries a digest of its fixed fields, and `compare` refuses a row whose fixed fields were edited.

## What the blind file leaves out

The blind file leaves out:
- the source path;
- the Room's id and name;
- the seats' models and drivers;
- the checks, the grade and the episode summary;
- the seats' own logs.

Tokens and email addresses are scrubbed from the text. The key holds where each row came from. Never give the key to an annotator, and never look at it before `finalize`.

## Reading the report

`report.json` gives, for each label:
- `kappa`: Cohen's kappa. It is `null` when it is undefined, that is, when nobody used the label.
- `decisions`: how many posts were compared.
- `positives`: how many posts each annotator labelled.
- `uncertain_excluded`: how many posts were left out because someone was unsure.

As a rule of thumb, a kappa below 0.6 means the definition is read in more than one way. When that happens:
1. Sharpen the definition, which makes a new codebook version.
2. Label a fresh sample.

## Rules

1. Judge each post from what the row shows. Do not open the Room, the share page or the run while you label.
2. A label applies when the post itself does what the definition says. When you are torn between yes and no, mark it uncertain.
3. Label independently. Annotators do not compare notes before `compare`.
4. Blind files, keys and gold files are data. Keep them with the experiment, never in this repository.
