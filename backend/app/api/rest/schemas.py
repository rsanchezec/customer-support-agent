"""Pydantic v2 schemas for the conversations REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MessageOut(BaseModel):
    """A single message in a conversation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    """A conversation summary (no messages)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_at: datetime
    message_count: int


class ConversationDetailOut(BaseModel):
    """A conversation with all its messages."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_at: datetime
    foundry_conversation_id: str
    messages: list[MessageOut]


class ConversationCreate(BaseModel):
    """Body for POST /conversations — title is optional."""

    title: str | None = None


class ConversationUpdate(BaseModel):
    """Body for PATCH /conversations/{id}."""

    title: str
