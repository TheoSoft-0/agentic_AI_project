import re
import warnings
from datetime import date

from .models import (
    EmailContent,
    TrashReviewFinding,
    TrashReviewFindingDraft,
    TrashReviewReport,
    TrashReviewReportDraft,
)


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


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace without changing the words or their order."""
    return " ".join(text.split())

def evidence_is_supported(evidence: str, source_text: str) -> bool:
    """Check that evidence appears in the source, ignoring whitespace differences."""
    normalized_evidence = normalize_whitespace(evidence)
    normalized_source = normalize_whitespace(source_text)

    return (
        bool(normalized_evidence)
        and normalized_evidence in normalized_source
    ) 

def validate_trash_review_report(
    report: TrashReviewReportDraft,
    inspected_conversations: dict[int, EmailContent],
    today: date,
) -> TrashReviewReport:
    """Convert untrusted model output into a validated report.

    Invalid findings are discarded individually. A finding cannot
    enter the final report unless its evidence and date requirements
    pass deterministic Python validation.
    """
    validated_findings: list[TrashReviewFinding] = []

    for finding in report.findings:

        def discard(message: str) -> None:
            warnings.warn(
                (
                    f"Discarding finding for conversation "
                    f"{finding.conversation_index}: {message}"
                ),
                RuntimeWarning,
                stacklevel=2,
            )

        # Every reported conversation must have been inspected.
        conversation = inspected_conversations.get(
            finding.conversation_index
        )

        if conversation is None:
            discard("conversation was never inspected.")
            continue

        # Evidence must be an exact substring of the inspected email.
        if not evidence_is_supported(finding.evidence, conversation.raw_text):
            discard("evidence is not present in the inspected email.")
            continue

        validated_event_date: date | None = None
        validated_event_date_text: str | None = None

        if finding.category in {"future_event", "both"}:
            event_date_text = (
                finding.event_date_text.strip()
                if finding.event_date_text
                else ""
            )

            event_date_value = (
                finding.event_date.strip()
                if finding.event_date
                else ""
            )

            if not event_date_text:
                discard("event_date_text is missing.")
                continue

            if not event_date_value:
                discard("event_date is missing.")
                continue

            # Require the date text to appear within the cited evidence.
            if not evidence_is_supported(event_date_text, finding.evidence):
                discard(
                    "event_date_text is not contained in the evidence."
                )
                continue

            # Parse the actual date supported by the source text.
            expected_date = parse_explicit_event_date(event_date_text)

            if expected_date is None:
                discard(
                    "event_date_text does not contain one valid, "
                    "explicit day-month-year date."
                )
                continue

            # The model must provide event_date in ISO YYYY-MM-DD format.
            try:
                model_date = date.fromisoformat(event_date_value)
            except ValueError:
                discard(
                    "event_date must use ISO YYYY-MM-DD format."
                )
                continue

            if model_date.isoformat() != event_date_value:
                discard(
                    "event_date must use ISO YYYY-MM-DD format."
                )
                continue

            # The normalized model date must agree with the source text.
            if model_date != expected_date:
                discard(
                    "event_date does not match event_date_text."
                )
                continue

            # Events today or in the past do not qualify.
            if model_date <= today:
                discard("event date is not in the future.")
                continue

            validated_event_date = model_date
            validated_event_date_text = event_date_text

        # Create the strict finding only after its checks have passed.
        validated_findings.append(
            TrashReviewFinding(
                conversation_index=finding.conversation_index,
                category=finding.category,
                event_date=validated_event_date,
                event_date_text=validated_event_date_text,
                evidence=finding.evidence,
                reason=finding.reason,
            )
        )

    return TrashReviewReport(findings=validated_findings)