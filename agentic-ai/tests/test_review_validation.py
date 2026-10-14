from datetime import date

from agentic_ai.review_validation import parse_explicit_event_date


import pytest

from agentic_ai.models import (
    EmailContent,
    TrashReviewFinding,
    TrashReviewReport,
)
from agentic_ai.review_validation import (
    validate_trash_review_report,
)


def test_valid_future_event_is_accepted():
    report = TrashReviewReport(
        findings=[
            TrashReviewFinding(
                conversation_index=7,
                category="future_event",
                event_date=date(2026, 10, 25),
                event_date_text="October 25, 2026",
                evidence="Your interview is on October 25, 2026.",
                reason="The email contains a future interview.",
            )
        ]
    )

    inspected = {
        7: EmailContent(
            conversation_index=7,
            raw_text="Your interview is on October 25, 2026.",
        )
    }

    result = validate_trash_review_report(
        report,
        inspected,
        date(2026, 10, 2),
    )

    assert result == report



def test_past_event_is_rejected():
    report = TrashReviewReport(
        findings=[
            TrashReviewFinding(
                conversation_index=7,
                category="future_event",
                event_date=date(2026, 9, 25),
                event_date_text="September 25, 2026",
                evidence="Your interview is on September 25, 2026.",
                reason="The email contains an event.",
            )
        ]
    )

    inspected = {
        7: EmailContent(
            conversation_index=7,
            raw_text="Your interview is on September 25, 2026.",
        )
    }

    with pytest.raises(ValueError, match="not in the future"):
        validate_trash_review_report(
            report,
            inspected,
            date(2026, 10, 2),
        )


def test_ambiguous_date_is_rejected():
    report = TrashReviewReport(
        findings=[
            TrashReviewFinding(
                conversation_index=7,
                category="future_event",
                event_date=date(2026, 10, 25),
                event_date_text="25/26",
                evidence="IMC Amsterdam HackerRank 25/26",
                reason="The model interpreted this as a date.",
            )
        ]
    )

    inspected = {
        7: EmailContent(
            conversation_index=7,
            raw_text="IMC Amsterdam HackerRank 25/26",
        )
    }
def test_event_today_is_rejected():
    report = TrashReviewReport(
        findings=[
            TrashReviewFinding(
                conversation_index=7,
                category="future_event",
                event_date=date(2026, 10, 2),
                event_date_text="October 2, 2026",
                evidence="Your interview is on October 2, 2026.",
                reason="The email contains an event today.",
            )
        ]
    )

    inspected = {
        7: EmailContent(
            conversation_index=7,
            raw_text="Your interview is on October 2, 2026.",
        )
    }

    with pytest.raises(
        ValueError,
        match="not in the future",
    ):
        validate_trash_review_report(
            report,
            inspected,
            date(2026, 10, 2),
        )
        
        
def test_evidence_must_exist_in_inspected_email():
    report = TrashReviewReport(
        findings=[
            TrashReviewFinding(
                conversation_index=7,
                category="future_event",
                event_date=date(2026, 10, 25),
                event_date_text="October 25, 2026",
                evidence="Invented sentence about October 25, 2026.",
                reason="Future event.",
            )
        ]
    )

    inspected = {
        7: EmailContent(
            conversation_index=7,
            raw_text="The interview is scheduled for October 25, 2026.",
        )
    }

    with pytest.raises(ValueError, match="evidence"):
        validate_trash_review_report(
            report,
            inspected,
            date(2026, 10, 2),
        )


    with pytest.raises(ValueError):
        validate_trash_review_report(
            report,
            inspected,
            date(2026, 10, 2),
        )

def test_parse_full_date():
    result = parse_explicit_event_date(
        "Friday, October 25th, 2026"
    )

    assert result == date(2026, 10, 25)


def test_parse_day_month_date():
    result = parse_explicit_event_date(
        "25 October 2026"
    )

    assert result == date(2026, 10, 25)


def test_reject_ambiguous_25_26():
    result = parse_explicit_event_date("25/26")

    assert result is None