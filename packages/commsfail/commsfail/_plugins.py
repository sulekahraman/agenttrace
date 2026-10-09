"""Entry-point discovery shared by the annotator and loader registries.

A plugin is any installed distribution that declares an entry point in a commsfail group. Discovery runs on
first use rather than on import, so a plugin module may ``import commsfail`` at its top. A plugin that fails
to import is skipped with a warning: one broken package must not take the CLI down for everyone else.
"""
from __future__ import annotations
import warnings
from importlib.metadata import entry_points

def load_group(group: str, builtin: dict, key=lambda obj, ep: ep.name) -> dict:
    """``builtin`` plus every object an installed entry point in ``group`` resolves to, keyed by ``key(obj, ep)``."""
    found = dict(builtin)
    for ep in entry_points(group=group):
        try:
            obj = ep.load()
        except Exception as exc:  # noqa: BLE001  the plugin's import error is its own, not ours
            warnings.warn(f"commsfail: skipping {group} plugin {ep.name!r} ({ep.value}): {type(exc).__name__}: {exc}",
                          RuntimeWarning, stacklevel=3)
            continue
        name = key(obj, ep)
        if name in found and found[name] is not obj:
            warnings.warn(f"commsfail: {group} plugin {ep.value} replaces {name!r}", RuntimeWarning, stacklevel=3)
        found[name] = obj
    return found
