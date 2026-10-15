from pydantic_ai                  import Agent, RunContext
from dataclasses                  import dataclass, field
from pydantic_ai.models.openai    import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from playwright.async_api         import Page
from datetime                     import date

from .models import (
    TrashCandidateSelection,
    TrashReviewReportDraft,
    TrashPageInformation,
    TrashReviewReport,
    EmailImportance,
    EmailContent,
)
from .proton import (
    get_trash_page_information,
    open_trash_conversation,
    star_conversation,
    return_to_trash,
    is_trash_page,
    open_trash,
)


def create_local_model() -> OpenAIChatModel:
    """Create the local Ollama model adapter."""
    return OpenAIChatModel(
        model_name="qwen3:4b-instruct",
        provider=OllamaProvider(
            base_url="http://localhost:11434/v1"
        ),
    )


def create_email_triage_agent() -> Agent:
    """Create the local email-triage agent."""
    return Agent(
        create_local_model(),
        output_type=EmailImportance,
        model_settings={"temperature": 0.0},
    )


@dataclass
class ProtonAgentDeps:
    page: Page
    today: date
    max_inspections:  int = 5
    inspections_used: int = 0
    max_tool_calls:   int = 10
    tool_calls_used:  int = 0
    allow_writes:    bool = False
    inspected_conversations: dict[int, EmailContent] = field( default_factory=dict )

def consume_tool_call_budget(deps: ProtonAgentDeps,) -> None:
    """Reserve one agent tool call."""
    if deps.tool_calls_used >= deps.max_tool_calls:
        raise RuntimeError("Tool-call budget exhausted.")
    deps.tool_calls_used += 1


def consume_inspection_budget(deps: ProtonAgentDeps,) -> None:
    """Reserve one detailed conversation inspection."""
    if deps.inspections_used >= deps.max_inspections:
        raise RuntimeError( "Inspection budget exhausted." )
    deps.inspections_used += 1
    
def create_proton_agent() -> Agent:
    """Create the Proton Mail agent."""
    agent = Agent(
        create_local_model(),
        deps_type=ProtonAgentDeps,
        output_type=EmailImportance,
        model_settings={"temperature": 0.0},
        instructions="""
You are an email triage agent operating on Proton Mail Trash.

Your job is to inspect the requested conversation and determine
whether it should be ignored, reviewed, or treated as urgent.

You must:

1. Use the inspect_trash_conversation tool to inspect the
   requested conversation.

2. Base your classification only on the returned email content.

3. Never invent email content.

4. Never navigate outside Trash.

5. Never modify a conversation unless the user explicitly
   requests that action.

6. When the user explicitly asks for important messages to be
   marked, use mark_conversation_important only when your
   classification is "review" or "urgent".

7. The Python tools enforce the browser safety rules.
""",
    )

    @agent.tool
    async def inspect_trash_conversation(
        ctx: RunContext[ProtonAgentDeps],
        index: int,
    ) -> EmailContent:
        """Open and return one Trash conversation by its index."""
        if not await is_trash_page(ctx.deps.page):
            raise RuntimeError(
                "The browser is not currently on Trash."
            )

        return await open_trash_conversation(
            ctx.deps.page,
            index=index,
        )

    @agent.tool
    async def mark_conversation_important(
        ctx: RunContext[ProtonAgentDeps],
        index: int,
    ) -> str:
        """Star a Trash conversation after the agent decides it is important."""
        if not ctx.deps.allow_writes:
            raise RuntimeError(
                "Write actions are disabled for this agent run."
            )

        await star_conversation(
            ctx.deps.page,
            index=index,
        )

        return f"Conversation {index} was successfully starred."

    return agent



def create_trash_review_agent() -> Agent:
    """Create the agent that analyzes already-inspected conversations."""
    return Agent(
        create_local_model(),
        output_type=TrashReviewReportDraft,
        model_settings={"temperature": 0.0},
        instructions="""
You analyze already-inspected Proton Mail Trash conversations.

Your task is to identify which conversations actually need
human checking.

A conversation needs checking when:

1. It meaningfully deviates from the surrounding conversations.

OR

2. It contains an actual meeting, event, invitation,
   appointment, deadline, or similar future event.

Important rules:

- Only analyze the conversations supplied in the user prompt.
- Do not use browser tools.
- Do not request more conversations.
- Every finding must represent a conversation that actually
  needs review.
- evidence is required and must be an exact excerpt from the
  inspected conversation.
- Never invent evidence.

For category "unusual":

- Compare the inspected conversation with the Trash overview
  supplied in the user prompt.
- Identify the specific surrounding pattern and the meaningful
  deviation from that pattern.
- A different subject or generic message type alone is insufficient.
  Explain why the deviation makes this conversation worth checking.
- Do not claim a pattern that is not supported by the overview.
- Do not contradict yourself in the reason.
- If the available context does not establish a meaningful
  deviation, do not create an unusual finding.
- The overview is for comparison only. Finding evidence must come
  from the inspected conversation.

For category "future_event":

- event_date is required.
- event_date_text is required.
- event_date_text must contain an explicit calendar date.
- event_date must be the normalized version of event_date_text.
- The received date of an email is not an event date.
- Never infer a date from values such as "25/26", "25-26",
  application round numbers, job codes, filenames, or IDs.
- If there is no unambiguous future event date, do not create
  a "future_event" finding.
- A valid event date must specify a day, month, and year.
- A month and year alone, such as "August 2027", is insufficient.
- Never invent a day to turn a month and year into a full date.
- Never convert "August 2027" to "2027-08-01".
- If the inspected email does not establish a specific calendar
  date, do not create a future_event finding.
- A valid event date must specify a day, month, and year.
- A month and year alone, such as "August 2027", is insufficient.
- Never invent a day to turn a month and year into a full date.
- Never convert "August 2027" to "2027-08-01".
- If the inspected email does not establish a specific calendar
  date, do not create a future_event finding.

For category "both":

- The same future-event requirements apply.

Return only conversations that actually need checking.
""",
    )

def create_candidate_selection_agent() -> Agent:
    """Create the agent that selects Trash conversations for inspection."""
    return Agent(
        create_local_model(),
        output_type=TrashCandidateSelection,
        model_settings={"temperature": 0.0},
        instructions="""
You select candidate conversations from a Proton Mail Trash overview.

Your job is to identify at most five conversation indexes that
deserve detailed inspection.

Select a conversation when the visible overview suggests that:

1. It meaningfully deviates from the surrounding conversations, OR
2. It may contain a meeting, event, invitation, appointment,
   deadline, or similar future event.

Important rules:

- Return at most five indexes.
- Only return indexes that appear in the supplied Trash overview.
- Do not invent indexes.
- Prefer conversations whose subject or visible text provides
  concrete evidence for one of the two criteria.
- Do not treat an email's received date as an event date.
- Do not infer a future event merely because a message is recent.
- Values such as "25/26" are ambiguous and must not be treated
  as calendar dates.
- This is candidate selection, not final classification.
- It is acceptable to select a candidate that later turns out
  not to need review.
""",
    )