from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TrashCandidateSelection(BaseModel):
    candidate_indices: list[int] = Field(
        default_factory=list,
    )


class EmailImportance(BaseModel):
    priority: Literal["ignore", "review", "urgent"]
    action_required: bool
    reason: str


class EmailContent(BaseModel):
    conversation_index: int
    raw_text: str


class RawTrashConversation(BaseModel):
    index: int
    page_number: int
    row_index: int
    raw_text: str

class TrashPageInformation(BaseModel):
    title: str
    url: str
    page_number: int
    page_count: int
    conversation_count: int
    conversations: list[RawTrashConversation]


class TrashConversation(BaseModel):
    index: int
    sender: str
    subject: str
    date_text: str
    raw_text: str


class TrashReviewFinding(BaseModel):
    conversation_index: int
    category: Literal["unusual", "future_event", "both"]

    event_date: date | None = None
    event_date_text: str | None = None

    evidence: str
    reason: str

    @model_validator(mode="after")
    def validate_future_event_fields(self) -> "TrashReviewFinding":
        if self.category in {"future_event", "both"}:
            if self.event_date is None:
                raise ValueError(
                    "future_event and both findings require event_date."
                )

            if self.event_date_text is None:
                raise ValueError(
                    "future_event and both findings require "
                    "event_date_text."
                )

        return self


class TrashReviewReport(BaseModel):
    findings: list[TrashReviewFinding]
    

class TrashReviewFindingDraft(BaseModel):
    """Untrusted model output before strict validation."""

    conversation_index: int
    category: Literal["unusual", "future_event", "both"]
    event_date: str | None = None
    event_date_text: str | None = None
    evidence: str
    reason: str


class TrashReviewReportDraft(BaseModel):
    """Raw report returned by the LLM."""

    findings: list[TrashReviewFindingDraft]
    
    
TrashMessagePurpose = Literal[
    "routine_application_admin",
    "action_required",
    "event_information",
    "meeting_or_appointment",
    "other",
]


class TrashContextPurposeDraft(BaseModel):
    """Model's classification of one surrounding Trash conversation."""

    conversation_index: int
    purpose: TrashMessagePurpose


class TrashConversationAssessmentDraft(BaseModel):
    """Structured assessment of one inspected conversation."""

    conversation_index: int
    purpose: TrashMessagePurpose

    # Classifications of all visible surrounding conversations.
    # The inspected conversation itself must not appear in this list.
    context_classifications: list[TrashContextPurposeDraft]

    # Verbatim excerpt supporting a potential finding.
    evidence: str | None = None

    # A complete, explicit date for an actual future event or deadline.
    event_date_text: str | None = None


class TrashReviewAssessmentReportDraft(BaseModel):
    """Untrusted structured classifications returned by the model."""

    assessments: list[TrashConversationAssessmentDraft]