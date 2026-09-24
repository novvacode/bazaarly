"""Tenant slug rules (SPEC §6.1)."""

from __future__ import annotations

import re

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$")

RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "app",
        "assets",
        "auth",
        "b",
        "bazaarly",
        "billing",
        "blog",
        "dashboard",
        "docs",
        "help",
        "home",
        "invite",
        "login",
        "logout",
        "o",
        "orders",
        "public",
        "root",
        "settings",
        "signup",
        "static",
        "status",
        "support",
        "system",
        "www",
    }
)


def slug_problem(slug: str) -> str | None:
    if not SLUG_RE.fullmatch(slug):
        return (
            "Use 3 to 40 lowercase letters, digits or hyphens, starting and ending with a "
            "letter or digit"
        )
    if "--" in slug:
        return "Slug cannot contain consecutive hyphens"
    if slug in RESERVED_SLUGS:
        return "This name is reserved; please choose another"
    return None
