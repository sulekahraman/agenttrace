"""Compatibility entry point for the installed AgentTrace Scout pipeline."""

from inspect_scout import Scanner, Transcript, scanner

from agenttrace.scout.scanners import annotation_guided_collaboration as pipeline


@scanner(messages="all", version=4)
def annotation_guided_collaboration() -> Scanner[Transcript]:
    return pipeline()
