# commsfail example plugin

A complete plugin: one annotator (`example_v1`, with its `schema.json`) and one source (`chat_jsonl`), announced through the two entry points in `pyproject.toml`. Use a plugin when your method lives in your own repository, for example next to a training codebase.

```bash
pip install -e .                                   # with commsfail installed
commsfail annotators                               # example_v1 appears, with the module it comes from
commsfail sources                                  # chat_jsonl appears
commsfail analyse sample_chat.jsonl --source chat_jsonl --annotator example_v1
commsfail analyse sample_chat.jsonl --source chat_jsonl --markdown      # regex_v1 on the same trace
```

To make your own: copy this directory, rename the package, set `name` on the class, write its `schema.json`, and change the two entry points. Ship `schema.json` as package data. The contract tests of the main repository run on your annotator when both packages are installed.
