"""Render transactional emails from Jinja2 templates (HTML + plain text)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from app.integrations.email import Email

_TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "email"


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(template: str, to: str, subject: str, context: dict[str, Any]) -> Email:
    env = _env()
    return Email(
        to=to,
        subject=subject,
        html=env.get_template(f"{template}.html").render(**context),
        text=env.get_template(f"{template}.txt").render(**context),
    )
