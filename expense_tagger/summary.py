"""Monthly totals summary for a tagged (or untagged) CSV."""

from collections import defaultdict

import re

from .io_utils import row_amount

_ISO = re.compile(r"^(\d{4})-(\d{1,2})")
_US = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})")


def _month_of(date_text):
    """Best-effort 'YYYY-MM' from ISO (2026-03-14) or US (3/14/2026) dates."""
    text = (date_text or "").strip()
    match = _ISO.match(text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    match = _US.match(text)
    if match:
        return f"{match.group(3)}-{int(match.group(1)):02d}"
    text = text[:7] if text else ""
    return text if re.match(r"^\d{4}-\d{2}$", text) else ""
    return (date_text or "").strip()[:7]


def monthly_totals(rows, columns):
    """Return {month: {category: signed_total}} plus shareable display order.

    Untagged rows collect under 'untagged' so nothing silently disappears.
    """
    category_column = columns.get("category")
    totals = defaultdict(lambda: defaultdict(float))
    for row in rows:
        month = _month_of(row.get(columns.get("date", ""), ""))
        if not month:
            month = "(no date)"
        category = (row.get(category_column, "") or "untagged").strip() if category_column else "untagged"
        amount = row_amount(row, columns)
        if amount is None:
            amount = 0.0
        totals[month][category] += round(amount, 2)
    return {month: dict(cats) for month, cats in sorted(totals.items())}


def format_monthly_totals(rows, columns, width=22):
    """Human-readable monthly summary text (spends negative, income positive)."""
    totals = monthly_totals(rows, columns)
    all_categories = sorted(
        {cat for cats in totals.values() for cat in cats},
        key=lambda c: c.lower(),
    )
    lines = ["Monthly totals", "=" * (width + 14)]
    for month, cats in totals.items():
        month_total = sum(cats.values())
        lines.append(f"{month}  (net: {fmt_money(month_total)})")
        for category in all_categories:
            if category not in cats:
                continue
            value = cats[category]
            lines.append(f"  {category.ljust(width)} {fmt_money(value)}")
    return "\n".join(lines)


def fmt_money(value):
    """Format like a bank statement would, negative with '-($12.34)' style."""
    negative = value < 0
    cents = round(abs(value) * 100) / 100
    text = f"{cents:,.2f}"
    return f"-${text}" if negative else f"${text}"
