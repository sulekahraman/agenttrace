from inspect_ai.model import ChatMessageAssistant
from inspect_scout import Scanner, scanner

from agenttrace.scout.annotations import annotate_message


@scanner(version=2)
def message_annotations() -> Scanner[ChatMessageAssistant]:
    async def scan(message: ChatMessageAssistant):
        return await annotate_message(message)

    return scan
