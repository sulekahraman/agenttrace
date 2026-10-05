from inspect_scout import Scanner, Transcript, llm_scanner, scanner


@scanner(messages="all")
def duplicated_work() -> Scanner[Transcript]:
    return llm_scanner(
        question="""
Does this conversation contain substantial duplicated work by different agents?

Return true only when agents independently repeat materially equivalent analysis
or execution without a clear verification, synthesis, or handoff purpose. Do not
count short acknowledgements, summaries needed for context, or deliberate
independent checks. Explain the finding and cite the relevant message numbers.
""",
        answer="boolean",
    )


@scanner(messages="all")
def weak_handoff() -> Scanner[Transcript]:
    return llm_scanner(
        question="""
Does this conversation contain a weak or failed handoff between agents?

Look for delegated or requested work that was not acknowledged, completed work
that was not delivered, delivered results that were not integrated, unclear
ownership, or an abandoned request. Return true only when the transcript
contains concrete evidence. Explain the finding and cite the delegation,
response, and downstream messages when available.
""",
        answer="boolean",
    )


@scanner(messages="all")
def unintegrated_information() -> Scanner[Transcript]:
    return llm_scanner(
        question="""
Does an agent provide relevant information that the group later ignores,
contradicts without resolution, or fails to incorporate into its decision?

Do not infer private knowledge or missing messages. Judge only information
visible in this transcript. Return true only when there is evidence of both the
contribution and a later opportunity to use it. Explain the finding and cite
the relevant messages.
""",
        answer="boolean",
    )
