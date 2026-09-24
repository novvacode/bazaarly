from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

# Reusable bounded string types (SPEC §17: input limits on every text field).
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
