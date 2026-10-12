"""The annotator registry: every annotator folder in this package, plus installed plugins.

A built-in annotator is a folder, commsfail/annotators/<name>/, with three files:

    __init__.py   the code; it sets ANNOTATOR = <the class>, and taxonomy = "<a choice>" if it reports failures
    schema.json   the output schema
    README.md     what it reports, how, and what it is good and bad at

Taxonomies are not kept per annotator: taxonomy-choices/ holds one catalog of patterns and the ways to group
them, and an annotator names the choice it reports in (see taxonomy.py).

Live pipelines such as standard/ declare PIPELINE = True and run through their own CLI commands;
they are excluded from this offline registry. Adding an ANNOTATOR folder registers it. There is no list to edit. ``example_kickstart`` is the one to copy:
``commsfail new <name>`` does that.

A plugin annotator is a class in any installed package, announced through an entry point:

    [project.entry-points."commsfail.annotators"]
    my_v1 = "my_package.annotators:MyV1"

``REGISTRY`` resolves on first access; ``discover()`` is the uncached form.
"""
from __future__ import annotations
import importlib, pkgutil
from functools import lru_cache
from .._plugins import load_group
from ..trace import Trace
from .base import (RECORD, Annotator, check_annotator, make_record, schema_of, schema_path, validate_output,
                   validate_record)
from .taxonomy import check_choice, check_taxonomy, choices, load_choice, taxonomy_of

ENTRY_POINT_GROUP = "commsfail.annotators"

def builtin() -> dict[str, type]:
    """The annotator folders in this package, by name."""
    found = {}
    for m in pkgutil.iter_modules(__path__):
        if not m.ispkg or m.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{m.name}")
        if getattr(module, "PIPELINE", False):
            continue
        cls = getattr(module, "ANNOTATOR", None)
        if cls is None:
            raise ImportError(f"commsfail/annotators/{m.name}/__init__.py must set ANNOTATOR = <the class>")
        if getattr(cls, "name", None) != m.name:
            raise ImportError(f"commsfail/annotators/{m.name}/ holds an annotator named {getattr(cls, 'name', None)!r}; they must match")
        found[m.name] = cls
    return found

def discover() -> dict[str, type]:
    """Built-in annotators plus installed plugins, freshly resolved. A class is keyed by its own name."""
    return load_group(ENTRY_POINT_GROUP, builtin(), key=lambda cls, ep: getattr(cls, "name", ep.name))

@lru_cache(maxsize=None)
def registry() -> dict[str, type]:
    return discover()

def get_annotator(name: str):
    reg = registry()
    try:
        return reg[name]()
    except KeyError:
        raise SystemExit(f"unknown annotator '{name}'; available: {', '.join(sorted(reg))}") from None

def origin(cls: type) -> str:
    """'builtin' for an annotator folder in this package, otherwise the module the plugin class lives in."""
    return "builtin" if cls.__module__.startswith(__name__ + ".") else cls.__module__

def run(annotator, trace: Trace) -> dict:
    """Annotate one trace and return the record: the envelope around the annotator's output."""
    ann = get_annotator(annotator) if isinstance(annotator, str) else annotator
    return make_record(ann, trace, ann.annotate(trace))

def __getattr__(name: str):
    if name == "REGISTRY":
        return registry()
    raise AttributeError(f"module 'commsfail.annotators' has no attribute {name!r}")

__all__ = ["ENTRY_POINT_GROUP", "RECORD", "Annotator", "builtin", "discover", "registry", "get_annotator", "origin", "run",
           "check_annotator", "make_record", "schema_of", "schema_path", "validate_output", "validate_record",
           "taxonomy_of", "check_taxonomy", "check_choice", "choices", "load_choice", "REGISTRY"]
