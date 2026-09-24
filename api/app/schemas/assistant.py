from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import StringConstraints

from app.schemas.common import Schema

SessionId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{8,64}$")]
Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class AssistantAskIn(Schema):
    session_id: SessionId
    message: Message


class SourceOut(Schema):
    type: str
    title: str


class AssistantReplyOut(Schema):
    answer: str
    answered: bool
    sources: list[SourceOut]


class AssistantLogOut(Schema):
    id: uuid.UUID
    session_id: str
    question: str
    answer: str
    answered: bool
    top_score: float | None
    latency_ms: int
    model: str
    created_at: datetime


class AssistantLogListOut(Schema):
    items: list[AssistantLogOut]
    next_cursor: str | None


class FaqDraftOut(Schema):
    question: str
    answer: str
