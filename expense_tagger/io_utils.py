"""CSV reading/writing with forgiving column detection for bank exports."""

import csv
import io

DETECTION_HINTS = {
    "date": ["date", "posted date", "transaction date", "post date", "time"],
    "description": [
        "description",
        "description raw",
        "payee",
        "merchant",
        "memo",
        "details",
        "narrative",
        "name",
    ],
    "amount": ["amount", "transaction amount", "value"],
    "debit": ["debit", "withdrawal", "money out"],
    "credit": ["credit", "deposit", "money in"],
    "category": ["category", "my category"],
}


def _score_header(header):
    scores = {}
    pairs = [(h, h.strip().lower()) for h in header]
    for role, hints in DETECTION_HINTS.items():
        for h, low in pairs:
            if any(low == hint for hint in hints):
                scores[role] = h
                break
    for role, hints in DETECTION_HINTS.items():
        if role in scores:
            continue
        for h, low in pairs:
            if h in scores.values():
                continue
            if any(hint in low for hint in hints):
                scores[role] = h
                break
    return scores


def read_rows(path):
    """Return (fieldnames, rows) where rows are dicts of str -> str."""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def detect_columns(fieldnames):
    """Map logical roles (date/description/amount/debit/credit) to real columns."""
    return _score_header(fieldnames)


def to_decimal(raw_value):
    """Parse a human/CSV amount string; None when it does not look numeric."""
    if raw_value is None:
        return None
    text = str(raw_value).strip().replace("$", "").replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    if not text or text in {"-", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def row_amount(row, columns):
    """Signed amount for a row; debit/credit columns keep their sign meaning."""
    if columns.get("amount"):
        return to_decimal(row.get(columns["amount"]))
    debit = abs(to_decimal(row.get(columns.get("debit", ""))) or 0)
    credit = abs(to_decimal(row.get(columns.get("credit", ""))) or 0)
    total = credit - debit
    return total if (debit or credit) else None


def rows_to_text(fieldnames, rows):
    """Rows -> CSV text in memory (used for the dry-run diff preview)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: row.get(name, "") for name in fieldnames})
    return buffer.getvalue()


def write_rows(path, fieldnames, rows):
    """Write rows as a CSV file on disk (only called after --apply)."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
