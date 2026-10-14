import re
from datetime import date

from .models import EmailContent, TrashReviewReport



_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_EXPLICIT_DATE_PATTERNS = [
    re.compile(
        r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?"
        r"\s+(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+(\d{4})\b",
        re.IGNORECASE,
    ),
]


def parse_explicit_event_date(text: str) -> date | None:
    """Parse one unambiguous written date.

    Ambiguous values such as '25/26' are deliberately rejected.
    """

    matches: list[date] = []

    for pattern in _EXPLICIT_DATE_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()

            if groups[0].isdigit():
                day = int(groups[0])
                month_name = groups[1]
                year = int(groups[2])
            else:
                month_name = groups[0]
                day = int(groups[1])
                year = int(groups[2])

            month = _MONTHS[month_name.lower()]

            try:
                matches.append(date(year, month, day))
            except ValueError:
                continue

    unique_matches = set(matches)

    if len(unique_matches) != 1:
        return None

    return unique_matches.pop()




def validate_trash_review_report(
    report: TrashReviewReport,
    inspected_conversations: dict[int, EmailContent],
    today: date,
) -> TrashReviewReport:
    """Reject review findings that contain unsupported future dates."""

    for finding in report.findings:
        if finding.category not in {"future_event", "both"}:
            continue

        if finding.event_date is None:
            raise ValueError(
                f"Conversation {finding.conversation_index} is marked "
                "as a future event but has no event_date."
            )

        if finding.event_date_text is None:
            raise ValueError(
                f"Conversation {finding.conversation_index} does not "
                "provide the source date text."
            )

        if finding.evidence is None:
            raise ValueError(
                f"Conversation {finding.conversation_index} does not "
                "provide evidence."
            )

        expected_date = parse_explicit_event_date(
            finding.event_date_text
        )

        if expected_date != finding.event_date:
            raise ValueError(
                f"Conversation {finding.conversation_index}: "
                f"event_date={finding.event_date} does not match "
                f"event_date_text={finding.event_date_text!r}."
            )

        if finding.event_date <= today:
            raise ValueError(
                f"Conversation {finding.conversation_index}: "
                f"event date {finding.event_date} is not in the future."
            )

        conversation = inspected_conversations.get(
            finding.conversation_index
        )

        if conversation is None:
            raise ValueError(
                f"Conversation {finding.conversation_index} was "
                "reported but was never inspected."
            )

        if finding.evidence not in conversation.raw_text:
            raise ValueError(
                f"Conversation {finding.conversation_index}: "
                "reported evidence does not exist in the inspected "
                "email content."
            )

    return report