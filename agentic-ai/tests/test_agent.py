import pytest
from datetime import date
from agentic_ai.agent import (
    ProtonAgentDeps,
    consume_inspection_budget,
    consume_tool_call_budget,
    validate_write_permission,
)

from agentic_ai.models import TrashReviewFinding

def test_write_permission_rejects_when_writes_are_disabled():
    deps = ProtonAgentDeps(
        page=None,
        today=date(2026, 10, 20),
        allow_writes=False,
    )

    with pytest.raises(
        RuntimeError,
        match="Write actions are disabled",
    ):
        validate_write_permission(deps, index=7)


def test_write_permission_rejects_uninspected_conversation():
    deps = ProtonAgentDeps(
        page=None,
        today=date(2026, 10, 20),
        allow_writes=True,
    )

    with pytest.raises(
        RuntimeError,
        match="has not been inspected",
    ):
        validate_write_permission(deps, index=7)


def test_write_permission_allows_inspected_conversation():
    from unittest.mock import MagicMock

    deps = ProtonAgentDeps(
        page=None,
        today=date(2026, 10, 20),
        allow_writes=True,
    )
    deps.inspected_conversations[7] = MagicMock()

    # No exception means the safety checks permit the action.
    validate_write_permission(deps, index=7)
def test_trash_review_finding_represents_a_review_item():
    finding = TrashReviewFinding(
        conversation_index=7,
        category="future_event",
        event_date=date(2026, 10, 2),
        event_date_text="October 2, 2026",
        evidence="Your interview is scheduled for October 2, 2026.",
        reason="Contains a future event.",
    )

    assert finding.conversation_index == 7
    assert finding.category == "future_event"
    assert finding.event_date == date(2026, 10, 2)
    assert finding.evidence == (
        "Your interview is scheduled for October 2, 2026."
    )


def test_inspection_budget_allows_inspection():
    deps = ProtonAgentDeps(
        page=None,
        today=date(2026, 10, 1),
        max_inspections=5,
    )

    consume_inspection_budget(deps)

    assert deps.inspections_used == 1


def test_inspection_budget_allows_final_inspection():
    deps = ProtonAgentDeps(
        page=None,
        today=date(2026, 10, 1),
        max_inspections=5,
        inspections_used=4,
    )

    consume_inspection_budget(deps)

    assert deps.inspections_used == 5


def test_inspection_budget_rejects_excess_inspection():
    deps = ProtonAgentDeps(
        page=None,
        today=date(2026, 10, 1),
        max_inspections=5,
        inspections_used=5,
    )

    with pytest.raises(RuntimeError, match="Inspection budget exhausted"):
        consume_inspection_budget(deps)

    assert deps.inspections_used == 5


def test_inspection_budget_does_not_exceed_limit():
    deps = ProtonAgentDeps(
        page=None,
        today=date(2026, 10, 1),
        max_inspections=2,
    )

    consume_inspection_budget(deps)
    consume_inspection_budget(deps)

    with pytest.raises(RuntimeError, match="Inspection budget exhausted"):
        consume_inspection_budget(deps)

    assert deps.inspections_used == 2
    
    
def test_tool_call_budget_allows_call():
    deps = ProtonAgentDeps(
        page=None,
        today=date(2026, 10, 1),
        max_tool_calls=3,
    )

    consume_tool_call_budget(deps)

    assert deps.tool_calls_used == 1


def test_tool_call_budget_allows_final_call():
    deps = ProtonAgentDeps(
        page=None,
        today=date(2026, 10, 1),
        max_tool_calls=3,
        tool_calls_used=2,
    )

    consume_tool_call_budget(deps)

    assert deps.tool_calls_used == 3


def test_tool_call_budget_rejects_excess_call():
    deps = ProtonAgentDeps(
        page=None,
        today=date(2026, 10, 1),
        max_tool_calls=3,
        tool_calls_used=3,
    )

    with pytest.raises(
        RuntimeError,
        match="Tool-call budget exhausted",
    ):
        consume_tool_call_budget(deps)

    assert deps.tool_calls_used == 3
    
    
def test_past_event_is_not_future():
    today = date(2026, 10, 1)
    event_date = date(2026, 9, 28)

    assert event_date <= today


def test_future_event_is_future():
    today = date(2026, 10, 1)
    event_date = date(2026, 10, 14)

    assert event_date > today