"""The source registry. A source is any ``callable(src: str) -> Trace``.

Built in: ``sharednet`` (``commsfail.sources.sharednet.load``), the default. Another transcript format is a
plugin: a function in your package plus one entry point.

    [project.entry-points."commsfail.sources"]
    chat_jsonl = "my_package.sources:load_chat_jsonl"
"""
from __future__ import annotations
from functools import lru_cache
from typing import Callable
from .._plugins import load_group
from ..trace import Trace
from . import sharednet

ENTRY_POINT_GROUP = "commsfail.sources"
DEFAULT = "sharednet"
Source = Callable[[str], Trace]
BUILTIN: dict[str, Source] = {"sharednet": sharednet.load}

def discover() -> dict[str, Source]:
    """Built-in sources plus installed plugins, freshly resolved."""
    return load_group(ENTRY_POINT_GROUP, BUILTIN)

@lru_cache(maxsize=None)
def sources() -> dict[str, Source]:
    return discover()

def get_source(name: str = DEFAULT) -> Source:
    reg = sources()
    try:
        return reg[name]
    except KeyError:
        raise SystemExit(f"unknown source '{name}'; available: {', '.join(sorted(reg))}") from None

def load(src: str, source: str = DEFAULT) -> Trace:
    return get_source(source)(src)

__all__ = ["ENTRY_POINT_GROUP", "DEFAULT", "BUILTIN", "Source", "discover", "sources", "get_source", "load", "sharednet"]
