import pytest

from agentic_ai.candidate_selection import (
    validate_candidate_selection,
)
from agentic_ai.models import (
    RawTrashConversation,
    TrashCandidateSelection,
    TrashPageInformation,
)


def make_overview() -> TrashPageInformation:
    return TrashPageInformation(
        title="Trash",
        url="https://mail.proton.me/u/1/trash",
        page_number=1,
        page_count=1,
        conversation_count=3,
        conversations=[
            RawTrashConversation(
                index=0,
                page_number=1,
                row_index=0,
                raw_text="one",
            ),
            RawTrashConversation(
                index=1,
                page_number=1,
                row_index=1,
                raw_text="two",
            ),
            RawTrashConversation(
                index=2,
                page_number=1,
                row_index=2,
                raw_text="three",
            ),
        ],
    )


def test_valid_candidates_are_accepted():
    selection = TrashCandidateSelection(
        candidate_indices=[0, 2],
    )

    result = validate_candidate_selection(
        selection,
        make_overview(),
    )

    assert result == [0, 2]


def test_invalid_index_is_rejected():
    selection = TrashCandidateSelection(
        candidate_indices=[0, 99],
    )

    with pytest.raises(ValueError, match="invalid indexes"):
        validate_candidate_selection(
            selection,
            make_overview(),
        )


def test_duplicate_index_is_rejected():
    selection = TrashCandidateSelection(
        candidate_indices=[1, 1],
    )

    with pytest.raises(ValueError, match="duplicate"):
        validate_candidate_selection(
            selection,
            make_overview(),
        )


def test_more_than_five_candidates_are_rejected():
    selection = TrashCandidateSelection(
        candidate_indices=[0, 1, 2, 3, 4, 5],
    )

    with pytest.raises(ValueError):
        validate_candidate_selection(
            selection,
            make_overview(),
        )
        

def test_candidate_outside_allowed_indexes_is_rejected():
    selection = TrashCandidateSelection(
        candidate_indices=[2],
    )

    with pytest.raises(ValueError, match="outside the allowed set"):
        validate_candidate_selection(
            selection,
            make_overview(),
            allowed_indexes={0, 1},
        )


def test_candidates_inside_allowed_indexes_are_accepted():
    selection = TrashCandidateSelection(
        candidate_indices=[0, 2],
    )

    result = validate_candidate_selection(
        selection,
        make_overview(),
        allowed_indexes={0, 1, 2},
    )

    assert result == [0, 2]