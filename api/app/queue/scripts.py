"""Lua scripts loaded once per Redis client."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from redis.asyncio import Redis
from redis.commands.core import AsyncScript

_DIR = Path(__file__).with_name("lua")


@dataclass(frozen=True, slots=True)
class Scripts:
    retry: AsyncScript
    dead: AsyncScript
    promote: AsyncScript

    @classmethod
    def load(cls, redis: Redis) -> Scripts:
        def script(name: str) -> AsyncScript:
            return redis.register_script((_DIR / f"{name}.lua").read_text())

        return cls(retry=script("retry"), dead=script("dead"), promote=script("promote"))
