"""Deterministic decisions derived from structured Trash classifications."""

from datetime import date
from collections import Counter
import re
from .models import (
    EmailContent,
    TrashReviewAssessmentReportDraft,
    TrashReviewFindingDraft,
    TrashReviewReportDraft,
)
from .review_validation import (
    evidence_is_supported,
    parse_explicit_event_date,
)


EVENT_PURPOSES = {
    "action_required",
    "event_information",
    "meeting_or_appointment",
}


_ACTION_REQUEST_PATTERNS = (
    r"\bplease\s+(?:complete|submit|upload|provide|send|confirm|"
    r"register|schedule|book|respond|reply|return|sign|follow|fill)\b",
    r"\b(?:you must|you need to|you are required to|"
    r"you are invited to|we ask you to)\s+(?:complete|submit|upload|"
    r"provide|send|confirm|register|schedule|book|respond|reply|"
    r"return|sign|follow|fill)\b",
    r"\b(?:du bedes|bedes du|du skal|vi beder dig om at)\b",
    r"\b(?:indsend|fremsend|upload|bekræft|udfyld|underskriv|besvar)\b",
)


def has_explicit_action_request(text: str) -> bool:
    """Check for common explicit requests for the recipient to act."""
    return any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in _ACTION_REQUEST_PATTERNS
    )


def assessment_report_to_review_draft(
    assessments: TrashReviewAssessmentReportDraft,
    inspected_conversations: dict[int, EmailContent],
    allowed_context_indexes_by_candidate: dict[int, set[int]],
    today: date,
) -> TrashReviewReportDraft:
    """Convert model classifications into a report draft using Python rules.

    An unusual finding requires a complete set of context classifications
    and a message purpose absent from that context.

    A future-event finding requires a supported, explicit date strictly
    after today, associated with an eligible message purpose.

    Unsupported evidence and incomplete context classifications cannot
    create an unusual finding.
    """

    findings: list[TrashReviewFindingDraft] = []
    seen_indexes: set[int] = set()

    for assessment in assessments.assessments:
        index = assessment.conversation_index

        # Do not accept duplicate assessments or uninspected conversations.
        if index in seen_indexes:
            continue
        seen_indexes.add(index)

        inspected = inspected_conversations.get(index)
        allowed_context = allowed_context_indexes_by_candidate.get(index)

        if inspected is None or allowed_context is None:
            continue

        # The target conversation is never part of its own context.
        expected_context = allowed_context - {index}

        returned_context_indexes = [
            item.conversation_index
            for item in assessment.context_classifications
        ]

        # Missing, duplicate, or unexpected context rows make the
        # comparison incomplete. In that case, do not infer unusualness.
        context_is_complete = (
            len(returned_context_indexes)
            == len(set(returned_context_indexes))
            and set(returned_context_indexes) == expected_context
        )

        # "other" means the model could not identify a useful purpose.
        # Treat it as an abstention, not as a competing purpose.
        context_purpose_list = [
            item.purpose
            for item in assessment.context_classifications
            if item.purpose != "other"
        ]

        purpose_counts = Counter(context_purpose_list)

        dominant_purpose = None
        dominant_count = 0

        if purpose_counts:
            dominant_purpose, dominant_count = purpose_counts.most_common(1)[0]

        # An action_required classification must be supported by an actual
        # request. A routine rejection is not a request for the recipient to act.
        purpose_for_comparison = assessment.purpose

        if (
            purpose_for_comparison == "action_required"
            and not has_explicit_action_request(inspected.raw_text)
        ):
            purpose_for_comparison = "other"

        # Require a strict majority among context messages with usable
        # purpose classifications. Ties and empty contexts are inconclusive.
        has_clear_context_majority = (
            bool(context_purpose_list)
            and dominant_count > len(context_purpose_list) / 2
        )

        dominant_context_description = (
            f"{dominant_purpose} "
            f"({dominant_count}/{len(context_purpose_list)} messages)"
            if dominant_purpose is not None
            else "no reliable context purpose"
        )

        is_unusual = (
            context_is_complete
            and bool(expected_context)
            and purpose_for_comparison != "other"
            and has_clear_context_majority
            and purpose_for_comparison != dominant_purpose
        )

        evidence = assessment.evidence
        evidence_is_valid = (
            evidence is not None
            and bool(evidence.strip())
            and evidence_is_supported(evidence, inspected.raw_text)
        )

        # A finding must always have evidence from the inspected message.
        if not evidence_is_valid:
            continue

        event_date_text = assessment.event_date_text
        parsed_event_date = (
            parse_explicit_event_date(event_date_text)
            if event_date_text
            else None
        )

        # Keep date detection independent of unusual-message detection.
        # The date must exist verbatim in both the inspected email and
        # the evidence excerpt.
        is_future_event = (
            assessment.purpose in EVENT_PURPOSES
            and event_date_text is not None
            and parsed_event_date is not None
            and parsed_event_date > today
            and event_date_text in inspected.raw_text
            and event_date_text in evidence
            and evidence_is_supported(event_date_text, evidence)
        )

        if not is_unusual and not is_future_event:
            continue

        if is_unusual and is_future_event:
            category = "both"
            reason = (
                f"The message purpose ({assessment.purpose}) differs from "
                f"the dominant surrounding purpose "
                f"({dominant_context_description}), and the email contains "
                f"the explicit future date {event_date_text}."
            )
        elif is_unusual:
            category = "unusual"
            reason = (
                f"The message purpose ({assessment.purpose}) differs from "
                f"the dominant surrounding purpose "
                f"({dominant_context_description})."
            )
        else:
            category = "future_event"
            reason = (
                f"The email contains the explicit future date "
                f"{event_date_text}, which is after {today.isoformat()}."
            )

        findings.append(
            TrashReviewFindingDraft(
                conversation_index=index,
                category=category,
                event_date=(
                    parsed_event_date.isoformat()
                    if is_future_event
                    else None
                ),
                event_date_text=(
                    event_date_text
                    if is_future_event
                    else None
                ),
                evidence=evidence,
                reason=reason,
            )
        )

    return TrashReviewReportDraft(findings=findings)