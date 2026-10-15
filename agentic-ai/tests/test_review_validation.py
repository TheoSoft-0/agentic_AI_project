import pytest
from datetime import date

from agentic_ai.models import (
    EmailContent,
    TrashReviewFindingDraft,
    TrashReviewReportDraft,
)
from agentic_ai.review_validation import (
    parse_explicit_event_date,
    validate_trash_review_report,
)

def test_discards_future_event_without_date():
    draft = TrashReviewReportDraft(
        findings=[
            TrashReviewFindingDraft(
                conversation_index=14,
                category="future_event",
                event_date=None,
                event_date_text="August 2027",
                evidence="The meeting will take place in August 2027.",
                reason="The message mentions a possible future meeting.",
            )
        ]
    )

    inspected = {
        14: EmailContent(
            conversation_index=14,
            raw_text="The meeting will take place in August 2027.",
        )
    }

    report = validate_trash_review_report(
        draft,
        inspected,
        date(2026, 10, 15),
    )

    assert report.findings == []


def test_accepts_a_valid_future_event():
    draft = TrashReviewReportDraft(
        findings=[
            TrashReviewFindingDraft(
                conversation_index=14,
                category="future_event",
                event_date="2027-08-15",
                event_date_text="August 15, 2027",
                evidence="The meeting will take place on August 15, 2027.",
                reason="The message specifies a future meeting date.",
            )
        ]
    )

    inspected = {
        14: EmailContent(
            conversation_index=14,
            raw_text="The meeting will take place on August 15, 2027.",
        )
    }

    report = validate_trash_review_report(
        draft,
        inspected,
        date(2026, 10, 15),
    )

    assert len(report.findings) == 1
    assert report.findings[0].event_date == date(2027, 8, 15)


def test_discards_event_date_not_supported_by_evidence():
    draft = TrashReviewReportDraft(
        findings=[
            TrashReviewFindingDraft(
                conversation_index=14,
                category="future_event",
                event_date="2027-08-15",
                event_date_text="August 15, 2027",
                evidence="The message refers to an upcoming meeting.",
                reason="The model proposes a specific future date.",
            )
        ]
    )

    inspected = {
        14: EmailContent(
            conversation_index=14,
            raw_text="The message refers to an upcoming meeting.",
        )
    }

    report = validate_trash_review_report(
        draft,
        inspected,
        date(2026, 10, 15),
    )

    assert report.findings == []

def test_month_and_year_is_not_a_specific_date():
    assert parse_explicit_event_date("August 2027") is None


def test_full_written_date_is_parsed():
    assert parse_explicit_event_date("August 15, 2027") == date(
        2027, 8, 15
    )


def test_invalid_calendar_date_is_rejected():
    assert parse_explicit_event_date("February 30, 2027") is None
    

def test_past_event_is_rejected():
    draft = TrashReviewReportDraft(
        findings=[
            TrashReviewFindingDraft(
                conversation_index=7,
                category="future_event",
                event_date="2026-09-25",
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

    with pytest.warns(RuntimeWarning, match="not in the future"):
        result = validate_trash_review_report(
            draft,
            inspected,
            date(2026, 10, 2),
        )

    assert result.findings == []


def test_ambiguous_date_is_rejected():
    draft = TrashReviewReportDraft(
        findings=[
            TrashReviewFindingDraft(
                conversation_index=7,
                category="future_event",
                event_date="2026-10-25",
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

    with pytest.warns(
        RuntimeWarning,
        match="does not contain one valid",
    ):
        result = validate_trash_review_report(
            draft,
            inspected,
            date(2026, 10, 2),
        )

    assert result.findings == []


      
def test_event_today_is_rejected():
    draft = TrashReviewReportDraft(
        findings=[
            TrashReviewFindingDraft(
                conversation_index=7,
                category="future_event",
                event_date="2026-10-02",
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

    with pytest.warns(RuntimeWarning, match="not in the future"):
        result = validate_trash_review_report(
            draft,
            inspected,
            date(2026, 10, 2),
        )

    assert result.findings == []
        

def test_evidence_must_exist_in_inspected_email():
    draft = TrashReviewReportDraft(
        findings=[
            TrashReviewFindingDraft(
                conversation_index=7,
                category="future_event",
                event_date="2026-10-25",
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

    with pytest.warns(RuntimeWarning, match="evidence is not present"):
        result = validate_trash_review_report(
            draft,
            inspected,
            date(2026, 10, 2),
        )

    assert result.findings == []


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