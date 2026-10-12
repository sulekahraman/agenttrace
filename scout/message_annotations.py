"""Compatibility entry point for standalone message-annotation scans."""

from inspect_ai.model import ChatMessageAssistant
from inspect_scout import Scanner, scanner

from agenttrace.scout.message_annotations import message_annotations as pipeline


@scanner(version=1)
def message_annotations() -> Scanner[ChatMessageAssistant]:
    return pipeline()
