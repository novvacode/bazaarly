"""What a job handler gets to work with."""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.email import EmailSender
from app.queue.envelope import Envelope


@dataclass(frozen=True, slots=True)
class JobContext:
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: Redis
    email: EmailSender
    envelope: Envelope
