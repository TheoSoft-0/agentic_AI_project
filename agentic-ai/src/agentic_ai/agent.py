from pydantic_ai                  import Agent, RunContext
from dataclasses                  import dataclass, field
from pydantic_ai.models.openai    import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from playwright.async_api         import Page
from datetime                     import date

from .models import (
    TrashReviewAssessmentReportDraft,
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

def validate_write_permission(
    deps: ProtonAgentDeps,
    index: int,
) -> None:
    """Reject writes unless enabled and the conversation was inspected."""
    if not deps.allow_writes:
        raise RuntimeError("Write actions are disabled for this agent run.")

    if index not in deps.inspected_conversations:
        raise RuntimeError(
            "Cannot star a conversation that has not been "
            "inspected during this run."
        )

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

        content = await open_trash_conversation(ctx.deps.page, index=index, )
        ctx.deps.inspected_conversations[index] = content
        return content

    @agent.tool
    async def mark_conversation_important(
        ctx: RunContext[ProtonAgentDeps],
        index: int,
    ) -> str:
        """Star a Trash conversation after the agent decides it is important."""
        validate_write_permission(ctx.deps, index)
        await star_conversation( ctx.deps.page, index=index, )
        return f"Conversation {index} was successfully starred."
    return agent



def create_trash_review_agent() -> Agent:
    """Create the agent that classifies inspected Trash conversations."""

    return Agent(
        create_local_model(),
        output_type=TrashReviewAssessmentReportDraft,
        model_settings={"temperature": 0.0},
        instructions="""
You classify already-inspected Proton Mail Trash conversations.

Your output is a structured assessment, not a final review report.
Python will decide whether a finding should be emitted.

PURPOSE CATEGORIES

Use exactly these categories:

- routine_application_admin:
  Routine application receipt confirmations, rejections,
  and ordinary application status updates.

- action_required:
  Requests for documents, technical assessments, uploads,
  or other concrete actions the recipient must take.

- event_information:
  Conference and webinar announcements, event promotions,
  and follow-ups about events.

- meeting_or_appointment:
  Interviews, meetings, appointments, and scheduling messages.

- other:
  Messages that do not fit the categories above.

CLASSIFICATION RULES

1. Classify every inspected conversation using its actual content.
2. For each inspected conversation, classify every surrounding
   conversation listed in that target's context block.
3. Return exactly one context classification for each listed
   surrounding conversation index.
4. Never include the inspected conversation's own index in its
   context_classifications.
5. Use only indices present in the supplied context.
6. Do not infer unseen email content.
7. A difference in job title, employer, wording, or tone does not
   change a routine application message into an unusual message.
8. A different message purpose can be meaningful, but Python will
   decide whether the purpose differs from the surrounding pattern.
9. Do not invent evidence or dates.

EVIDENCE RULES

- Evidence must be a verbatim excerpt from the inspected email.
- Choose one continuous excerpt rather than combining separate
  parts of the email.
- Do not invent evidence.
- If event_date_text is supplied, it must be the complete,
  explicit event date and must appear verbatim in evidence.
- Do not use a received timestamp or other email-header date as
  an event date.
- A year in a subject, product name, or event name is not enough
  to establish an event date.
- A month and year without a specific day is not a complete date.
- Never invent a day to complete an incomplete date.
- Populate event_date_text only when the email explicitly gives
  a complete date for an actual meeting, event, appointment,
  or deadline that is in the future relative to today's date.
- If no such date exists, leave event_date_text empty.

OUTPUT RULES

- Return one assessment for each inspected conversation.
- Use the supplied conversation index.
- Classify every surrounding index shown for that conversation.
- Do not decide which conversations should appear in the final
  report. Python applies that decision after your assessment.
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