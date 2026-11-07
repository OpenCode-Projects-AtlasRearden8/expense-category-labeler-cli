"""Deterministic merchant-matching rules for repeat merchants.

Two rule tiers, applied in order:
1. user rules  - read from a JSON rules file (learned or hand-edited)
2. built-ins   - a starter list bundled with the tool

Matches are case-insensitive and substring based, because bank exports are
messy ("WAL*MART SUPERCTR 2244" should still match "walmart").
"""

import json
import re

from .categories import is_valid_category

# Substring (lowercased) -> plain-English category.
BUILTIN_RULES = [
    ("walmart", "groceries"),
    ("wal-mart", "groceries"),
    ("wal mart", "groceries"),
    ("kroger", "groceries"),
    ("albertson", "groceries"),
    ("safeway", "groceries"),
    ("trader joe", "groceries"),
    ("aldi", "groceries"),
    ("publix", "groceries"),
    ("food lion", "groceries"),
    ("whole foods", "groceries"),
    ("heb", "groceries"),
    ("meijer", "groceries"),
    ("target store", "groceries"),
    ("dollar general", "shopping"),
    ("dollar tree", "shopping"),
    ("cvs", "healthcare & pharmacy"),
    ("walgreen", "healthcare & pharmacy"),
    ("pharmacy", "healthcare & pharmacy"),
    ("starbucks", "dining out"),
    ("dunkin", "dining out"),
    ("mcdonald", "dining out"),
    ("chick-fil-a", "dining out"),
    ("chipotle", "dining out"),
    ("subway", "dining out"),
    ("pizza", "dining out"),
    ("burger", "dining out"),
    ("taco", "dining out"),
    ("restaurant", "dining out"),
    ("coffee", "dining out"),
    ("shell oil", "gas & fuel"),
    ("shell", "gas & fuel"),
    ("chevron", "gas & fuel"),
    ("exxon", "gas & fuel"),
    ("bp gas", "gas & fuel"),
    ("speedway", "gas & fuel"),
    ("sheetz", "gas & fuel"),
    ("wawa", "gas & fuel"),
    ("gas station", "gas & fuel"),
    ("casey's", "gas & fuel"),
    ("circle k", "gas & fuel"),
    ("netflix", "subscriptions"),
    ("spotify", "subscriptions"),
    ("hulu", "subscriptions"),
    ("disney+", "subscriptions"),
    ("hbo", "subscriptions"),
    ("youtube premium", "subscriptions"),
    ("apple.com/bill", "subscriptions"),
    ("audible", "subscriptions"),
    ("kindle unlimited", "subscriptions"),
    ("amazon", "shopping"),
    ("ebay", "shopping"),
    ("etsy", "shopping"),
    ("home depot", "shopping"),
    ("lowes", "shopping"),
    ("menards", "shopping"),
    ("ace hardware", "shopping"),
    ("amazon web services", "fees & charges"),
    ("aws", "fees & charges"),
    ("godaddy", "fees & charges"),
    ("service fee", "fees & charges"),
    ("overdraft", "fees & charges"),
    ("atm fee", "fees & charges"),
    ("mug fee", "fees & charges"),
    ("interest charge", "fees & charges"),
    ("verizon", "phone & internet"),
    ("at&t", "phone & internet"),
    ("t-mobile", "phone & internet"),
    ("comcast", "phone & internet"),
    ("xfinity", "phone & internet"),
    ("spectrum", "phone & internet"),
    ("cox internet", "phone & internet"),
    ("electric", "utilities"),
    ("power", "utilities"),
    ("water bill", "utilities"),
    ("sewer", "utilities"),
    ("gas company", "utilities"),
    ("trash", "utilities"),
    ("geico", "insurance"),
    ("state farm", "insurance"),
    ("progressive", "insurance"),
    ("allstate", "insurance"),
    ("usaa ins", "insurance"),
    ("policy premium", "insurance"),
    ("lyft", "travel"),
    ("uber", "travel"),
    ("delta air", "travel"),
    ("southwest air", "travel"),
    ("hotel", "travel"),
    ("airbnb", "travel"),
    ("parking", "travel"),
    ("payroll", "income & deposits"),
    ("direct deposit", "income & deposits"),
    ("rent payment", "rent & mortgage"),
    ("mortgage", "rent & mortgage"),
    ("landlord", "rent & mortgage"),
]


def normalize(text):
    """Normalize for matching: uppercase, punctuation -> space, squash spaces.

    "WAL*MART SUPERCTR 2244" -> "WAL MART SUPERCCTR 2244"-style keys, so bank
    noise ($, *, -, '/') never blocks a repeat merchant from matching.
    """
    return re.sub(r"[^A-Z0-9]+", " ", (text or "").upper()).strip()

_NORMALIZED_BUILTINS = [
    (normalize(pattern), category, False) for pattern, category in BUILTIN_RULES
]


class RuleEngine:
    """Applies user rules first, then built-ins, via (normalized) substring matching."""

    def __init__(self, user_rules=None):
        self.user_rules = []
        for rule in user_rules or []:
            self.add_rule(rule)

    @staticmethod
    def _parse(rule):
        """ rule = {"pattern": ..., "category": ...}; '=' prefix = exact match."""
        raw = str(rule.get("pattern", ""))
        exact = raw.strip().startswith("=")
        pattern = normalize(raw.lstrip("=").strip())
        category = str(rule.get("category", "")).strip().lower()
        return pattern, category, exact

    def add_rule(self, rule):
        pattern, category, exact = self._parse(rule)
        if pattern and is_valid_category(category):
            self.user_rules.append((pattern, category, exact))

    @classmethod
    def from_file(cls, path):
        """Load a JSON rules file of shape {"rules": [{"pattern": ..., "category": ...}]}."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return cls()
        if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
            return cls()
        return cls(data["rules"])

    def match(self, description):
        """Return the first category whose pattern appears in the description.

        User rules win over built-ins. An exact rule (leading '=' in the
        rules file) matches only if the whole normalized description equals
        the pattern, e.g. \"=HASH HOUSE LLC\" matches nothing longer.
        """
        desc = normalize(description)
        if not desc:
            return None
        for pattern, category, exact in list(self.user_rules) + _NORMALIZED_BUILTINS:
            if exact:
                if desc == pattern:
                    return category
            elif pattern in desc:
                return category
        return None

    def to_file(self, path):
        """Persist the current user rules as pretty, hand-editable JSON."""
        rules = []
        for pattern, category, exact in self.user_rules:
            rules.append(
                {"pattern": ("=" + pattern) if exact else pattern, "category": category}
            )
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"rules": rules}, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    def learn(self, descriptions_to_categories):
        """Merge this run's merchant->category pairs into the user rule tier.

        Duplicates are skipped so repeated --learn runs stay idempotent.
        """
        known = {(p, c, exact) for p, c, exact in self.user_rules}
        for description, category in descriptions_to_categories:
            pattern = normalize(description)
            entry = (pattern, str(category).lower(), False)
            if pattern and is_valid_category(entry[1]) and entry not in known:
                self.user_rules.append(entry)
