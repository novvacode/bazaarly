from __future__ import annotations

import re
import uuid
from typing import Annotated

from pydantic import Field, StringConstraints, field_validator

from app.schemas.common import Name, Schema

ItemName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]
Answer = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Price = Annotated[int, Field(gt=0, le=10_000_000)]

_TAG_RE = re.compile(r"^[a-z0-9][a-z0-9 -]{0,29}$")


def _clean_tags(tags: list[str] | None) -> list[str] | None:
    if tags is None:
        return None
    out: list[str] = []
    for raw in tags:
        tag = raw.strip().lower()
        if not _TAG_RE.fullmatch(tag):
            raise ValueError(f"Invalid tag: {raw!r} (lowercase letters, digits, spaces, hyphens)")
        if tag not in out:
            out.append(tag)
    if len(out) > 10:
        raise ValueError("At most 10 tags")
    return out


class CategoryIn(Schema):
    name: Name


class CategoryOut(Schema):
    id: uuid.UUID
    name: str
    position: int


class ItemIn(Schema):
    name: ItemName
    description: Description | None = None
    price_paise: Price
    category_id: uuid.UUID | None = None
    is_available: bool = True
    is_veg: bool = True
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return _clean_tags(v) or []


class ItemPatch(Schema):
    name: ItemName | None = None
    description: Description | None = None
    price_paise: Price | None = None
    category_id: uuid.UUID | None = None
    is_available: bool | None = None
    is_veg: bool | None = None
    tags: list[str] | None = None

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str] | None) -> list[str] | None:
        return _clean_tags(v)


class ItemOut(Schema):
    id: uuid.UUID
    category_id: uuid.UUID | None
    name: str
    description: str | None
    price_paise: int
    image_url: str | None
    is_available: bool
    is_veg: bool
    tags: list[str]
    position: int


class ReorderIn(Schema):
    """`items` maps a category id (or "uncategorized") to the ordered item ids in it."""

    categories: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    items: dict[str, list[uuid.UUID]] = Field(default_factory=dict)


class FaqIn(Schema):
    question: Question
    answer: Answer


class FaqPatch(Schema):
    question: Question | None = None
    answer: Answer | None = None


class FaqOut(Schema):
    id: uuid.UUID
    question: str
    answer: str
    position: int


class FaqReorderIn(Schema):
    ids: list[uuid.UUID] = Field(max_length=500)
