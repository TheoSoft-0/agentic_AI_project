from datetime import date

from agentic_ai.models import (
    EmailContent,
    TrashContextPurposeDraft,
    TrashConversationAssessmentDraft,
    TrashReviewAssessmentReportDraft,
)
from agentic_ai.review_decision import assessment_report_to_review_draft


TODAY = date(2026, 10, 17)
CONTEXT_INDEXES = {98, 99, 101, 102}


def make_assessment(
    *,
    purpose: str,
    evidence: str,
    context_purpose: str,
    event_date_text: str | None = None,
) -> TrashReviewAssessmentReportDraft:
    assessment = TrashConversationAssessmentDraft(
        conversation_index=100,
        purpose=purpose,
        context_classifications=[
            TrashContextPurposeDraft(
                conversation_index=index,
                purpose=context_purpose,
            )
            for index in sorted(CONTEXT_INDEXES)
        ],
        evidence=evidence,
        event_date_text=event_date_text,
    )

    return TrashReviewAssessmentReportDraft(
        assessments=[assessment],
    )


def make_report(
    assessment_report: TrashReviewAssessmentReportDraft,
    email_text: str,
):
    inspected = {
        100: EmailContent(
            conversation_index=100,
            raw_text=email_text,
        )
    }

    return assessment_report_to_review_draft(
        assessment_report,
        inspected,
        {100: CONTEXT_INDEXES},
        TODAY,
    )


def test_routine_application_message_matching_context_is_not_flagged():
    email = (
        "We have received your application and will contact you "
        "if we need additional information."
    )

    assessment = make_assessment(
        purpose="routine_application_admin",
        context_purpose="routine_application_admin",
        evidence=email,
    )

    report = make_report(assessment, email)

    assert report.findings == []


def test_different_action_required_purpose_is_flagged():
    email = (
        "To continue processing your application, please upload "
        "a copy of your degree certificate through the applicant portal."
    )

    assessment = make_assessment(
        purpose="action_required",
        context_purpose="routine_application_admin",
        evidence=email,
    )

    report = make_report(assessment, email)

    assert len(report.findings) == 1
    assert report.findings[0].category == "unusual"


def test_explicit_future_interview_date_is_flagged():
    email = "Your interview is scheduled for October 25, 2026."

    assessment = make_assessment(
        purpose="meeting_or_appointment",
        context_purpose="meeting_or_appointment",
        evidence=email,
        event_date_text="October 25, 2026",
    )

    report = make_report(assessment, email)

    assert len(report.findings) == 1
    assert report.findings[0].category == "future_event"
    assert report.findings[0].event_date == "2026-10-25"


def test_past_event_matching_context_is_not_flagged():
    email = (
        "The webinar took place on October 12, 2026. "
        "The recording is now available to participants."
    )

    assessment = make_assessment(
        purpose="event_information",
        context_purpose="event_information",
        evidence=email,
        event_date_text="October 12, 2026",
    )

    report = make_report(assessment, email)

    assert report.findings == []


def test_month_and_year_alone_does_not_create_future_finding():
    email = (
        "The conference is planned for August 2027. "
        "We will announce the exact date and time later."
    )

    assessment = make_assessment(
        purpose="event_information",
        context_purpose="event_information",
        evidence=email,
        event_date_text="August 2027",
    )

    report = make_report(assessment, email)

    assert report.findings == []