from pydantic import BaseModel

from typing import Literal

from pydantic import BaseModel


class EmailImportance(BaseModel):
    priority: Literal["ignore", "review", "urgent"]
    action_required: bool
    reason: str
    
class RawTrashConversation(BaseModel):
    index: int
    raw_text: str


class TrashPageInformation(BaseModel):
    title: str
    url: str
    conversation_count: int
    conversations: list[RawTrashConversation]


class TrashConversation(BaseModel):
    index: int
    sender: str
    subject: str
    date_text: str
    raw_text: str
    
    
class EmailContent(BaseModel):
    conversation_index: int
    raw_text: str