"""The annotator contract.

An annotator is a class:

    class MyV1:
        name = "my_v1"            # lowercase letters, digits and _; for a built-in, also its folder name
        version = "0.1.0"         # change it whenever the output for the same trace changes
        schema = "schema.json"    # its output schema (JSON Schema 2020-12), relative to the class's file
        def annotate(self, trace) -> dict: ...    # deterministic, offline, leaves the trace unchanged
        def markdown(self, output) -> str: ...    # optional: a short view for people (`--markdown`)
        taxonomy = "state_gap"      # optional: a choice in taxonomy-choices/ (see taxonomy.py)
        def modes_in(self, output) -> list[str]: ...  # required with a taxonomy: the pattern ids an output reports

Each annotator owns its output schema. commsfail puts every output in one envelope, the record:

    {"record": "commsfail/record.v1",
     "annotator": {"name": ..., "version": ..., "schema": <the schema's $id>},
     "source": the trace's source (kind, path or redacted token, room_id, loaded_at),
     "output": what annotate() returned}
"""
from __future__ import annotations
import inspect, json, re
from functools import lru_cache
from pathlib import Path
from typing import Protocol, runtime_checkable
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from ..trace import Trace
from .taxonomy import check_taxonomy, taxonomy_of

RECORD = "commsfail/record.v1"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

@runtime_checkable
class Annotator(Protocol):
    name: str
    version: str
    def annotate(self, trace: Trace) -> dict: ...

def _cls(x) -> type:
    return x if isinstance(x, type) else type(x)

def schema_path(annotator) -> Path | None:
    """Where the annotator's schema file is, or None when the schema is given inline as a dict."""
    cls = _cls(annotator)
    s = getattr(cls, "schema", "schema.json")
    return None if isinstance(s, dict) else Path(inspect.getfile(cls)).resolve().parent / s

@lru_cache(maxsize=None)
def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")

def schema_of(annotator) -> dict:
    """The annotator's output schema, as a dict."""
    s = getattr(_cls(annotator), "schema", "schema.json")
    return s if isinstance(s, dict) else json.loads(_read(str(schema_path(annotator))))

def check_annotator(annotator) -> list[str]:
    """Problems with the annotator itself, before it runs: name, version, annotate(), schema."""
    cls, errs = _cls(annotator), []
    if not isinstance(getattr(cls, "name", None), str) or not NAME_RE.match(cls.name):
        errs.append("name must be 2 to 41 characters: lowercase letters, digits and _, starting with a letter")
    if not isinstance(getattr(cls, "version", None), str) or not cls.version:
        errs.append("version must be a string such as '0.1.0'")
    if not callable(getattr(cls, "annotate", None)):
        errs.append("annotate(trace) is missing")
    try:
        schema = schema_of(cls)
    except FileNotFoundError:
        return errs + [f"schema file not found: {schema_path(cls)}"]
    except json.JSONDecodeError as e:
        return errs + [f"schema file is not valid JSON: {e}"]
    for k in ("$schema", "$id", "title", "description"):
        if k not in schema:
            errs.append(f"the schema must have '{k}'")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as e:
        errs.append(f"the schema is not a valid JSON Schema: {e.message}")
    try:
        tax = taxonomy_of(cls)
    except KeyError as e:
        return errs + [f"taxonomy: {e.args[0]}"]
    if tax is not None:
        errs += [f"taxonomy: {e}" for e in check_taxonomy(tax)]
        if not callable(getattr(cls, "modes_in", None)):
            errs.append("an annotator with a taxonomy must implement modes_in(output): the pattern ids an output reports")
    return errs

def _short(s: str, n: int = 240) -> str:
    return s if len(s) <= n else s[:n] + "…"

def validate_output(annotator, output) -> list[str]:
    """Where the output breaks the annotator's own schema; empty means it conforms."""
    v = Draft202012Validator(schema_of(annotator))
    errors = sorted(v.iter_errors(output), key=lambda e: [str(x) for x in e.absolute_path])
    return [f"{'/'.join(str(x) for x in e.absolute_path) or '(root)'}: {_short(e.message)}" for e in errors]

def make_record(annotator, trace: Trace, output) -> dict:
    return {"record": RECORD,
            "annotator": {"name": annotator.name, "version": annotator.version, "schema": schema_of(annotator).get("$id")},
            "source": dict(trace.source), "output": output}

def validate_record(record, registry: dict | None = None) -> list[str]:
    """Check a record: the envelope, then its output against the installed annotator's schema."""
    if not isinstance(record, dict):
        return ["a record must be a JSON object"]
    errs = [f"missing '{k}'" for k in ("record", "annotator", "source", "output") if k not in record]
    if record.get("record") not in (None, RECORD):
        errs.append(f"'record' must be '{RECORD}'")
    if errs:
        return errs
    if registry is None:
        from . import registry as current
        registry = current()
    name = (record["annotator"] or {}).get("name")
    cls = registry.get(name)
    if cls is None:
        return [f"annotator '{name}' is not installed, so its output cannot be checked"]
    sid = schema_of(cls).get("$id")
    if record["annotator"].get("schema") != sid:
        errs.append(f"the record was made with schema '{record['annotator'].get('schema')}'; the installed {name} has '{sid}'")
    return errs + validate_output(cls, record["output"])
