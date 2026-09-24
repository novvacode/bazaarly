"""Money is integer paise; format only at the edges (emails, UI)."""

from __future__ import annotations


def format_inr(paise: int) -> str:
    """`123450` → `₹1,234.50`; whole rupees drop the decimals (`65000` → `₹650`).

    Uses Indian digit grouping (1,00,000).
    """
    negative = paise < 0
    paise = abs(paise)
    rupees, rem = divmod(paise, 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join([*groups, tail])
    out = f"₹{digits}" + (f".{rem:02d}" if rem else "")
    return f"-{out}" if negative else out
