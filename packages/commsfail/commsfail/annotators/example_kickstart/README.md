# example_kickstart

<!-- kickstart -->
> **Start here.** This annotator is a working sample that you copy. `commsfail new <name>` makes `commsfail/annotators/<name>/` from this folder, and `tests/annotators/test_<name>.py` from its test. The copy runs and passes its tests at once. Then you make it yours, one file at a time:
>
> 1. **Pick a taxonomy.** Set `taxonomy = "<choice>"` to one of the choices in [taxonomy-choices](../taxonomy-choices): `ten_modes`, `state_gap` or `decision_point`. Do not write a taxonomy of your own here. If your method finds a failure that no pattern in `patterns.json` describes, add the pattern there, and place it in every complete choice. The tests will tell you which.
> 2. **Write your method** in `__init__.py`. Your method finds *signals*. In `SIGNALS`, say which catalog pattern each signal is evidence for. `modes_in()` returns the patterns an output reports.
> 3. **Describe your output** in `schema.json`.
> 4. **Fill in every section** of this README below.
> 5. **Write your expectations** in `tests/annotators/test_<name>.py`: which posts your method points at on the samples, and why.
>
> Because every choice groups the same catalog, your findings read in any taxonomy. `commsfail audit export ... --codebook <choice>` lets people label the same patterns by hand.
<!-- /kickstart -->

Open questions and bare claims, read in the `state_gap` taxonomy. Replace this sentence with what your annotator reports.

**Output:** [schema.json](schema.json). For each signal found in a post, the output gives:
- the post and the seat;
- the signal;
- the catalog pattern it is evidence for;
- that pattern's class in the chosen taxonomy;
- a redacted excerpt, and why.

It also counts findings by class.

**Signals:**
- `open_question` is evidence of pattern **B1**, which is in the *disagreement* class in `state_gap`: a question that no later post answers or cites.
- `bare_claim` is evidence of pattern **D1**, which is in the *ungrounded* class in `state_gap`: "done" or "passes", with no file, item or post number a reader could check.

**How:** text rules over the agent posts.
- A question is a post that ends in "?". It counts as answered when a later post replies to it or cites its number.
- A bare claim is a done or pass word in a post that names nothing checkable: no backticked item, no file name, no `#n`.

**Good at:** short boards where questions end in "?" and where claims name what they are about.

**Weak at:**
- a question asked without "?";
- an answer that neither replies nor cites;
- a claim that names a file but is still false, which needs the seat's own log (see facts_v1).

**Checked on:** the samples in `tests/fixtures/` and the synthetic board in `tests/conftest.py`, read by hand.
