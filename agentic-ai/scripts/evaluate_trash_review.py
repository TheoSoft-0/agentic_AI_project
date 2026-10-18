from __future__ import annotations

import asyncio
import re
import sys
import warnings
from datetime import date
from pathlib import Path

from pydantic_ai import UsageLimits

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agentic_ai.agent import create_trash_review_agent
from agentic_ai.models import EmailContent
from agentic_ai.review_decision import assessment_report_to_review_draft
from agentic_ai.review_validation import (
    parse_explicit_event_date,
    validate_trash_review_report,
)
from agentic_ai.workflow import remove_email_header_timestamps

TODAY = date(2026, 10, 17)
CONVERSATION_INDEX = 100


CASES = [
    {
        "id": "routine_application_confirmation",
        "expected": None,
        "overview": """
Index 98: Tak for din ansøgning til stillingen som udvikler.
Index 99: Bekræftelse på modtagelse af din ansøgning.

Index 101: Tak for din ansøgning til en software-stilling.
Index 102: Bekræftelse på modtagelse af din ansøgning.
""",
        "email": """
Subject: Bekræftelse på modtagelse af din ansøgning som
BI- og AI-konsulent (Junior/Graduate)

Vi har modtaget din ansøgning og vender tilbage, når vi
har behandlet den.
""",
    },
    {
        "id": "assessment_invitation_without_date",
        "expected": "unusual",
        "overview": """
Index 98: Tak for din ansøgning.
Index 99: Bekræftelse på modtagelse af din ansøgning.

Index 101: Tak for din ansøgning til en anden stilling.
Index 102: Bekræftelse på modtagelse af din ansøgning.
""",
        "email": """
Subject: Invitation to Complete the Online Technical Assessment

You are invited to complete the online technical assessment.
Please follow the instructions in the assessment portal.
""",
    },
    {
        "id": "future_interview_date",
        "expected": "future_event",
        "expected_date": "2026-10-25",
        "overview": """
Index 98: Interview confirmation for a software role.
Index 99: Interview scheduling details for another candidate.

Index 101: Interview reminder.
Index 102: Interview scheduling confirmation.
""",
       "email": """
Subject: Interview confirmation

Your interview is scheduled for October 25, 2026.
We look forward to speaking with you.
""",
    },
    {
        "id": "past_event_date",
        "expected": None,
        "overview": """
Index 98: Webinar announcement and recording.
Index 99: Details about a completed online event.

Index 101: Recording of a completed webinar.
Index 102: Follow-up message about a completed event.
""",
        "email": """
Subject: Webinar follow-up

The webinar took place on October 12, 2026.
The recording is now available to participants.
""",
    },
    {
        "id": "received_timestamp_is_not_event_date",
        "expected": None,
        "overview": """
Index 98: Application receipt confirmation.
Index 99: Standard confirmation of a submitted application.

Index 101: Standard application status update.
Index 102: Application receipt confirmation.
""",
        "email": """
Friday
Friday, October 23rd, 2026 at 12:29 PM
To
the applicant
Subject
Application confirmation

We have received your application and will contact you
if we need additional information.
""",
    },
    {
        "id": "month_and_year_without_specific_day",
        "expected": None,
        "overview": """
Index 98: Annual conference announcement; exact date to follow.
Index 99: Industry conference planning newsletter.

Index 101: Annual event announcement; further details pending.
Index 102: Conference newsletter.
""",
        "email": """
Subject: Conference announcement

The conference is planned for August 2027.
We will announce the exact date and time later.
""",
    },
    {
        "id": "industry_event_amid_job_applications",
        "expected": "unusual",
        "overview": """
Index 98: Tak for din ansøgning.
Index 99: Bekræftelse på modtagelse af din ansøgning.

Index 101: Application status update.
Index 102: Tak for din ansøgning til stillingen som udvikler.
""",
        "email": """
Subject: Meet KeyShot Leaders + Industry Experts at KeyShot World 2026!

Join industry experts at KeyShot World 2026.
Explore product visualization and connect with the community.
""",
    },
    {
        "id": "unexpected_request_for_documents",
        "expected": "unusual",
        "overview": """
Index 98: Standard application receipt confirmation.
Index 99: Confirmation that an application was received.

Index 101: Standard application receipt confirmation.
Index 102: Application status update.
""",
        "email": """
Subject: Additional documents required

To continue processing your application, please upload
a copy of your degree certificate through the applicant portal.
""",
    },
    {
        "id": "future_document_deadline",
        "expected": "future_event",
        "expected_date": "2026-10-28",
        "overview": """
Index 98: Reminder about outstanding application documents.
Index 99: Request to submit supporting documents by a deadline.

Index 101: Application document reminder.
Index 102: Notice about supporting documentation.
""",
        "email": """
Subject: Reminder: upload remaining documents

Please upload the requested certificate by October 28, 2026.
""",
    },
    {
        "id": "routine_rejection_amid_status_updates",
        "expected": None,
        "overview": """
Index 98: Application receipt confirmation.
Index 99: Standard rejection following an application.

Index 101: Standard job application rejection.
Index 102: Confirmation of application receipt.
""",
        "email": """
Subject: Update on your application

Thank you for applying. We regret to inform you that
we will not be proceeding with your application.
""",
    },
]


def build_prompt(case: dict) -> str:
    """Build a bounded assessment request for one synthetic scenario."""

    email_for_analysis = remove_email_header_timestamps(case["email"])

    return f"""
Assess this synthetic Proton Mail Trash conversation.

Today's date is {TODAY.isoformat()}.

Return one structured assessment for conversation index
{CONVERSATION_INDEX}.

Nearby Trash context for this target:
{case["overview"]}

Inspected conversation:
CONVERSATION INDEX: {CONVERSATION_INDEX}
{email_for_analysis}

Follow the structured assessment schema and purpose categories
provided in your instructions.

Classify every surrounding index listed above, excluding the
inspected conversation's own index.

Use evidence from the inspected conversation only.
Do not treat email-header timestamps as event dates.
Do not infer a full date from a month and year.
Only provide event_date_text for a genuine future event or
deadline whose complete date is explicitly stated in the email.
"""

def normalize_whitespace(text: str) -> str:
    """Treat repeated spaces and line breaks as equivalent formatting."""
    return " ".join(text.split())


def evaluate_output(case: dict, report) -> tuple[bool, list[str], str]:
    """Compare a generated review report with the expected outcome."""
    findings = report.findings
    expected = case["expected"]
    problems: list[str] = []

    # Check how many findings should exist.
    if expected is None:
        if findings:
            problems.append("Expected no findings.")
    elif len(findings) != 1:
        problems.append(
            f"Expected exactly one finding; got {len(findings)}."
        )

    # Check the expected finding, if exactly one was returned.
    if expected is not None and len(findings) == 1:
        finding = findings[0]

        if finding.conversation_index != CONVERSATION_INDEX:
            problems.append("Incorrect conversation index.")

        if expected == "future_event":
            if finding.category not in {"future_event", "both"}:
                problems.append(
                    f"Expected a future-event finding; "
                    f"got category {finding.category!r}."
                )

            expected_date = case.get("expected_date")
            reported_date = (
                finding.event_date.isoformat()
                if isinstance(finding.event_date, date)
                else finding.event_date
            )

            if expected_date and reported_date != expected_date:
                problems.append(
                    f"Expected event date {expected_date!r}; "
                    f"got {reported_date!r}."
                )

        elif finding.category != expected:
            problems.append(
                f"Expected category {expected!r}; "
                f"got {finding.category!r}."
            )

    # Validate every finding, including unexpected extra findings.
    for finding in findings:
        if finding.conversation_index != CONVERSATION_INDEX:
            problems.append(
                f"Unexpected finding index: "
                f"{finding.conversation_index}."
            )

        if (
            not finding.evidence 
            or normalize_whitespace(finding.evidence) 
            not in normalize_whitespace(case["email"])
            ):
                problems.append(
                    "Evidence is not an exact excerpt from the original email."
                )

        if finding.category not in {"future_event", "both"}:
            continue

        if not finding.event_date or not finding.event_date_text:
            problems.append(
                "Future-event finding is missing date information."
            )
            continue

        try:
            normalized_date = (
                finding.event_date
                if isinstance(finding.event_date, date)
                else date.fromisoformat(finding.event_date)
            )
        except (ValueError, TypeError):
            problems.append("event_date is not a valid ISO date.")
            continue

        reported_date = (
            finding.event_date.isoformat()
            if isinstance(finding.event_date, date)
            else finding.event_date
        )

        if normalized_date.isoformat() != reported_date:
            problems.append(
                "event_date is not normalized to ISO format."
            )

        parsed_text_date = parse_explicit_event_date(
            finding.event_date_text
        )

        if parsed_text_date is None:
            problems.append(
                "event_date_text is not a specific, valid date."
            )
        elif parsed_text_date != normalized_date:
            problems.append(
                "event_date does not match event_date_text."
            )

        if finding.event_date_text not in finding.evidence:
            problems.append(
                "event_date_text is not included in the evidence."
            )

        if normalized_date <= TODAY:
            problems.append("Event date is not in the future.")

    actual = (
        "none"
        if not findings
        else ", ".join(
            f"{finding.conversation_index}:{finding.category}"
            for finding in findings
        )
    )

    return not problems, problems, actual


async def main() -> None:
    agent = create_trash_review_agent()

    decision_results: list[bool] = []
    validated_results: list[bool] = []

    print(f"Trash review evaluation — analysis date: {TODAY}")
    print(f"Scenarios: {len(CASES)}")
    print("=" * 60)

    for case in CASES:
        try:
            # 1. Ask the model for structured purpose assessments.
            result = await agent.run(
                build_prompt(case),
                usage_limits=UsageLimits(
                    request_limit=2,
                    input_tokens_limit=3500,
                    output_tokens_limit=1200,
                ),
            )
            assessment_report = result.output

            # 2. Create the inspected-conversation data used in production.
            inspected = {
                CONVERSATION_INDEX: EmailContent(
                    conversation_index=CONVERSATION_INDEX,
                    raw_text=case["email"],
                )
            }

            # 3. Extract the context indexes supplied in the prompt.
            context_indexes = {
                int(index)
                for index in re.findall(
                    r"Index\s+(\d+):",
                    case["overview"],
                )
            }

            # 4. Apply deterministic decision rules.
            decision_report = assessment_report_to_review_draft(
                assessment_report,
                inspected,
                {CONVERSATION_INDEX: context_indexes},
                TODAY,
            )

            decision_success, decision_problems, decision_actual = (
                evaluate_output(case, decision_report)
            )

            # 5. Apply the production validation layer.
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always", RuntimeWarning)

                validated_report = validate_trash_review_report(
                    decision_report,
                    inspected,
                    TODAY,
                )

            final_success, final_problems, final_actual = (
                evaluate_output(case, validated_report)
            )

            decision_results.append(decision_success)
            validated_results.append(final_success)

            decision_label = "PASS" if decision_success else "FAIL"
            final_label = "PASS" if final_success else "FAIL"

            print(
                f"[DECISION {decision_label}] "
                f"{case['id']}: {decision_actual}"
            )
            print(
                f"[FINAL {final_label}] "
                f"{case['id']}: {final_actual}"
            )

            if not decision_success or not final_success:
                for assessment in assessment_report.assessments:
                    print(f"    Purpose: {assessment.purpose}")
                    print(
                        "    Context classifications: "
                        f"{[(item.conversation_index, item.purpose) for item in assessment.context_classifications]}"
                    )
                    print(f"    Evidence: {assessment.evidence!r}")
                    print(
                        "    Evidence supported after whitespace normalization:",
                        normalize_whitespace(assessment.evidence)
                        in normalize_whitespace(case["email"]),
                    )
                    print(f"    Event date text: {assessment.event_date_text!r}")
                for problem in decision_problems:
                    print(f"    Decision: {problem}")

                for problem in final_problems:
                    print(f"    Final report: {problem}")

            for warning in caught_warnings:
                print(f"    Validation: {warning.message}")

        except Exception as exc:
            decision_results.append(False)
            validated_results.append(False)

            print(
                f"[ERROR] {case['id']}: "
                f"{type(exc).__name__}: {exc}"
            )

        print()

    print("=" * 60)

    total = len(CASES)

    print(
        f"Decision-layer matches: "
        f"{sum(decision_results)}/{total} "
        f"({sum(decision_results) / total:.0%})"
    )

    print(
        f"Validated report matches: "
        f"{sum(validated_results)}/{total} "
        f"({sum(validated_results) / total:.0%})"
    )

    print(
        "These scores evaluate synthetic scenarios, not general "
        "real-world accuracy."
    )



if __name__ == "__main__":
    asyncio.run(main())

