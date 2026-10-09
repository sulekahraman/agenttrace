"""A Trace is one board in a normalized shape. Every source produces it. Every annotator reads it.

    Trace
      .room      {id, name, created_at, latest_sequence, state}
      .seats     [{handle, label, driver, model, joined_at, principal, member_id}]
      .posts     [{seq, id, who, text, created_at, reply_to, type, role}]
                 who = a seat handle; reply_to = a seq; role = "goal" | "agent" | "runner" | "other" | None (unknown)
      .artifacts [{id, by, created_at, name, sha256}]
      .ops       {handle: [{turn, i, kind, command, exit_code, output, posted, paths, query, name, text}]}
                 what each seat did, read from its own harness log; kind = command | file_change |
                 web_search | tool | message | error; posted = the seq a `sharednet say` command made
      .checks    [{at, trigger, command, cause, exit_code, passed, sequence, output}]
      .wakes     [{seat, turn, fired, from, through, messages, started_at, ended_at, exit_code, failed, tokens}]
      .episode   the run's own summary: goal, ended_by, totals, agents, ...
      .source    {kind, path | token, room_id, loaded_at}

A field a source cannot show is empty, never invented. ``commsfail.sources.sharednet`` documents which
SharedNet source fills which field.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field

# Sources that carry artifact rows, so a claimed upload can be checked against the record.
ARTIFACT_KINDS = ("export", "episode")

@dataclass
class Trace:
    room: dict
    seats: list
    posts: list
    artifacts: list = field(default_factory=list)
    ops: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    wakes: list = field(default_factory=list)
    episode: dict = field(default_factory=dict)
    source: dict = field(default_factory=dict)

    @property
    def has_record(self) -> bool:
        """True when the source carries artifact rows, so a claimed upload can be checked by rule."""
        return self.source.get("kind") in ARTIFACT_KINDS

    @property
    def has_ops(self) -> bool:
        """True when at least one seat's own harness log was read."""
        return any(self.ops.values())

    def to_dict(self) -> dict:
        return asdict(self)
