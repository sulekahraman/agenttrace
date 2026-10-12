"""commsfail: communication-failure analysis of multi-agent message boards.

A board is any place where several agents post to one ordered log and read each other. The default board is
a SharedNet Room. commsfail reads one board into a ``Trace``, runs an annotator over it, and writes a record:
the annotator's output, in its own schema, inside one envelope.

    from commsfail import load, run, validate_record
    trace = load("runs/rom_…")              # a goal-run record folder, a room.ndjson, a share JSON or link
    record = run("regex_v1", trace)         # {"record", "annotator", "source", "output"}
    assert validate_record(record) == []

Layout:

- ``commsfail.sources.sharednet``  everything about SharedNet: readers for each source, and tools over a Trace
- ``commsfail.annotators``         the contract (``base``), the registry, one folder per annotator, each with its own taxonomy
- ``commsfail.audit``              human labels: blind export, Cohen's kappa, adjudication, gold
- ``commsfail.trace``              the Trace shape
- ``commsfail.cli``                ``commsfail analyse | trace | annotators | sources | schema | taxonomy | validate | new | audit``
"""
from __future__ import annotations
from .trace import Trace
from .sources import load, get_source
from .annotators import (Annotator, get_annotator, run, check_annotator, schema_of, validate_output, validate_record,
                         RECORD)

__version__ = "0.4.0"
__all__ = ["Trace", "load", "get_source", "Annotator", "get_annotator", "run", "check_annotator", "schema_of",
           "validate_output", "validate_record", "RECORD", "REGISTRY", "SOURCES", "__version__"]

def __getattr__(name: str):
    if name == "REGISTRY":
        from .annotators import registry
        return registry()
    if name == "SOURCES":
        from .sources import sources
        return sources()
    raise AttributeError(f"module 'commsfail' has no attribute {name!r}")
