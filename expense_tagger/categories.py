"""Plain-English category names used across the tool."""

CATEGORY_ORDER = [
    "groceries",
    "dining out",
    "gas & fuel",
    "utilities",
    "rent & mortgage",
    "phone & internet",
    "insurance",
    "healthcare & pharmacy",
    "shopping",
    "subscriptions",
    "entertainment",
    "travel",
    "fees & charges",
    "income & deposits",
    "transfers & payments",
    "other",
]

CATEGORY_SET = set(CATEGORY_ORDER)


def is_valid_category(name):
    """A category is valid if it is one of the known plain-English names."""
    return name in CATEGORY_SET
