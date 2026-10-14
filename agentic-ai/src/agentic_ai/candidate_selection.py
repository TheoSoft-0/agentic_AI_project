from .models import (
    TrashCandidateSelection,
    TrashPageInformation,
)


def validate_candidate_selection(
    selection: TrashCandidateSelection,
    overview: TrashPageInformation,
    max_candidates: int = 5,
    allowed_indexes: set[int] | None = None,
) -> list[int]:
    """Validate LLM-selected conversation indexes."""
    if len(selection.candidate_indices) > max_candidates:
        raise ValueError(
            f"Candidate selection contains "
            f"{len(selection.candidate_indices)} indexes, "
            f"but the maximum is {max_candidates}."
        )

    if len(set(selection.candidate_indices)) != len(
        selection.candidate_indices
    ):
        raise ValueError(
            "Candidate selection contains duplicate indexes."
        )

    valid_indexes = {
        conversation.index
        for conversation in overview.conversations
    }

    invalid_indexes = [
        index
        for index in selection.candidate_indices
        if index not in valid_indexes
    ]

    if invalid_indexes:
        raise ValueError(
            f"Candidate selection contains invalid indexes: "
            f"{invalid_indexes}"
        )

    if allowed_indexes is not None:
        outside_allowed = [
            index
            for index in selection.candidate_indices
            if index not in allowed_indexes
        ]

        if outside_allowed:
            raise ValueError(
                "Candidate selection contains indexes outside "
                f"the allowed set: {outside_allowed}"
            )

    return selection.candidate_indices