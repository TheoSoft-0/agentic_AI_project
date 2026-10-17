from dataclasses import dataclass
from datetime import date

from playwright.async_api import Page
from pydantic_ai import UsageLimits
import re
from .agent import (
    ProtonAgentDeps,
    create_candidate_selection_agent,
    create_trash_review_agent,
)
from .candidate_selection import validate_candidate_selection
from .models import (
    EmailContent,
    TrashPageInformation,
    TrashReviewReport,
)
from .proton import (
    get_recent_trash_conversations,
    open_trash_conversation,
    return_to_trash,
)
from .review_validation import validate_trash_review_report







@dataclass
class TrashReviewRun:
    """Result of one Trash-review execution."""

    report: TrashReviewReport
    candidate_indexes: list[int]
    inspected_indexes: list[int]
    analysis_date: date



def remove_email_header_timestamps(text: str) -> str:
    """Remove a recognized timestamp in an email-header context."""

    lines = text.splitlines()
    cleaned: list[str] = []
    index = 0

    weekday_pattern = re.compile(
        r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)$",
        re.IGNORECASE,
    )

    timestamp_pattern = re.compile(
        r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
        r"[A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4}\s+at\s+"
        r"\d{1,2}:\d{2}\s*(?:AM|PM)$",
        re.IGNORECASE,
    )

    header_fields = {"to", "from", "cc", "bcc", "subject"}

    while index < len(lines):
        # Match the specific pattern:
        # weekday / full timestamp / email header field.
        if (
            index + 2 < len(lines)
            and weekday_pattern.fullmatch(lines[index].strip())
            and timestamp_pattern.fullmatch(lines[index + 1].strip())
            and lines[index + 2].strip().casefold() in header_fields
        ):
            # Skip the standalone weekday and timestamp.
            index += 2
            continue

        cleaned.append(lines[index])
        index += 1

    return "\n".join(cleaned)


def make_review_excerpt( text: str, *, max_chars: int = 2400, ) -> str:
    """Create a bounded excerpt for the review model."""

    text = remove_email_header_timestamps(text)

    marker = "\n\n[Middle omitted to limit prompt size.]\n\n"

    if len(text) <= max_chars:
        return text



    if max_chars <= len(marker):
        raise ValueError( "max_chars must be greater than the omission marker length." )

    head_chars = min(1700, max_chars - len(marker))
    tail_chars = max_chars - len(marker) - head_chars

    return (
        text[:head_chars].rstrip()
        + marker
        + (text[-tail_chars:].lstrip() if tail_chars else "")
    )

async def review_trash(
    page: Page,
    *,
    today: date | None = None,
    max_inspections: int = 5,
) -> TrashReviewRun:
    analysis_date = today or date.today()

    # 1. Collect only the two most recent Trash pages.
    conversations = await get_recent_trash_conversations(
        page,
        max_pages=2,
    )

    if not conversations:
        return TrashReviewRun(
            report=TrashReviewReport(findings=[]),
            candidate_indexes=[],
            inspected_indexes=[],
            analysis_date=analysis_date,
        )

    overview = TrashPageInformation(
        title=await page.title(),
        url=page.url,
        page_number=1,
        page_count=max(
            conversation.page_number
            for conversation in conversations
        ),
        conversation_count=len(conversations),
        conversations=conversations,
    )

    # 2. Ask the model to select at most five candidates.
    # Use short previews to keep the prompt within a sensible size.
    batch_text = "\n".join(
        (
            f"Index {conversation.index}: "
            f"{conversation.raw_text[:80]}"
        )
        for conversation in conversations
    )

    allowed_indexes = {
        conversation.index
        for conversation in conversations
    }

    candidate_agent = create_candidate_selection_agent()

    candidate_result = await candidate_agent.run(
        f"""
You are selecting candidate Trash conversations for human review.

Today's date is {analysis_date.isoformat()}.

Select at most five candidates from ONLY the indexes supplied.

A conversation is a candidate if:
1. It meaningfully deviates from the surrounding Trash messages, OR
2. It may contain an actual meeting, event, invitation, appointment,
   or deadline whose date is strictly after today.

Do not invent indexes.
The received email date is not an event date.
Do not infer dates from ambiguous values such as "25/26".
Prefer concrete evidence. This is candidate selection, not final review.

Trash overview:
{batch_text}
""",
        usage_limits=UsageLimits(
            request_limit=2,
            input_tokens_limit=6_000,
            output_tokens_limit=500,
        ),
    )

    candidate_indexes = validate_candidate_selection(
        candidate_result.output,
        overview,
        max_candidates=5,
        allowed_indexes=allowed_indexes,
    )

    # Preserve order and remove duplicates defensively.
    candidate_indexes = list(dict.fromkeys(candidate_indexes))

    if len(candidate_indexes) > 5:
        raise RuntimeError( "Candidate selection exceeded the five-candidate limit." )

    # Build compact comparison context around the selected candidates.
    # Use list positions rather than assuming indexes are consecutive.
    conversation_positions = {
        conversation.index: position
        for position, conversation in enumerate(conversations)
    }

    context_positions: set[int] = set()

    for candidate_index in candidate_indexes:
        candidate_position = conversation_positions[candidate_index]

        # Include up to two rows before and two rows after each candidate.
        context_positions.update(
            range(
                max(0, candidate_position - 2),
                min(len(conversations), candidate_position + 3),
            )
        )

    comparison_text = "\n".join(
        (
            f"Index {conversations[position].index}: "
            f"{conversations[position].raw_text[:80]}"
        )
        for position in sorted(context_positions)
    )


    # 3. Enforce the inspection budget in Python.
    deps = ProtonAgentDeps(
        page=page,
        today=analysis_date,
        max_inspections=max_inspections,
        max_tool_calls=10,
        allow_writes=False,
    )

    if len(candidate_indexes) > deps.max_inspections:
        raise RuntimeError(
            "Candidate selection exceeds the inspection budget."
        )

    inspected_conversations: list[EmailContent] = []

    for index in candidate_indexes:
        content = await open_trash_conversation(
            page,
            index=index,
        )

        deps.inspected_conversations[index] = content
        inspected_conversations.append(content)
        deps.inspections_used += 1

        # Return to Trash before opening the next conversation.
        await return_to_trash(page)


    # 4. Perform one final semantic review.
    inspected_text = "\n\n".join(
    (
        f"CONVERSATION INDEX: {content.conversation_index}\n"
        f"{make_review_excerpt(content.raw_text)}"
    )
    for content in inspected_conversations
)

    review_agent = create_trash_review_agent()

    result = await review_agent.run(
        f"""
Review these selected Proton Mail Trash conversations.

Today's date is {analysis_date.isoformat()}.

Your task is to identify only conversations that genuinely need
human checking.

A conversation qualifies if:
1. It meaningfully deviates from the surrounding Trash messages, OR
2. It contains an actual future event with an explicit,
   unambiguous calendar date strictly after today.

For the unusual category:
- Compare each inspected conversation with the Trash overview below.
- Identify the specific pattern in the surrounding messages and
  explain how the inspected conversation meaningfully differs.
- A different subject or generic message type alone is not enough.
  Explain why the difference makes this conversation worth checking.
- Do not claim a surrounding pattern unless the overview supports it.
- If no meaningful deviation can be established, omit the finding.
- Do not contradict yourself in the explanation.
- Treat routine variations in metadata as normal, not unusual.
- For job application confirmations, differences in job title,
  employer name, job level, or wording do not by themselves
  constitute a meaningful deviation.
- A message confirming receipt of an application remains a
  routine confirmation even when it names a specific role.
- Look for a meaningful difference in the message's purpose,
  status, requested action, or substantive content.
- Examples that may warrant checking include a rejection,
  an assessment invitation, a request for additional documents,
  a concrete deadline, or unexpected or conflicting instructions.
- Do not claim that a message has extra relevance or intent
  unless its content supports that conclusion.
- The reason must explain why the difference matters, not
  merely describe how the subject differs.

For future events:
- Events dated today or earlier do NOT qualify.
- The received email date is not an event date.
- Dates in email headers, including weekday/timestamp combinations,
  must not be treated as event dates.
- Do not infer dates from ambiguous values such as "25/26".
- event_date and event_date_text are required for future_event
  and both findings.
- event_date must be a string in ISO YYYY-MM-DD format.
- event_date_text must be an exact substring of evidence.
- Evidence must be an exact substring of the inspected conversation.
- A month and year alone, such as "August 2027", is insufficient.
- Never invent a day to complete an incomplete date.
- Do not include a future_event or both finding without a valid,
  explicit date and supporting evidence.

Evidence rules:
- Evidence must be an exact excerpt from the inspected conversation.
- Never invent evidence, event dates, or surrounding-message patterns.
- The Trash overview provides comparison context only.
  It must not be used as evidence for a finding.
- Do not assume that a candidate actually needs review.
- If neither criterion is met, omit that conversation.

Nearby Trash comparison context
(short previews of rows around selected candidates):
{comparison_text}

Inspected conversations
(full or bounded excerpts; use these as the source of evidence):
{inspected_text}
""",
        usage_limits=UsageLimits(
            request_limit=2,
            input_tokens_limit=10_000,
            output_tokens_limit=1_200,
        ),
    )

    # 5. Validate the report deterministically in Python.
    validated_report = validate_trash_review_report(
        result.output,
        deps.inspected_conversations,
        deps.today,
    )

    return TrashReviewRun(
        report=validated_report,
        candidate_indexes=candidate_indexes,
        inspected_indexes=[
            content.conversation_index
            for content in inspected_conversations
        ],
        analysis_date=analysis_date,
    )
