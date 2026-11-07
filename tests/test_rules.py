"""Tests for rule matching: built-ins, user rules, and learning."""

import json
import tempfile
import os
import unittest

from expense_tagger.categories import CATEGORY_ORDER
from expense_tagger.rules import BUILTIN_RULES, RuleEngine, normalize


class NormalizeTests(unittest.TestCase):
    def test_uppercases_and_collapses_whitespace(self):
        self.assertEqual(normalize("  WAL*MART   Supercenter "), "WAL MART SUPERCENTER")

    def test_punctuation_becomes_separators(self):
        self.assertEqual(normalize("wal*mart#9"), "WAL MART 9")
        self.assertEqual(normalize("NETFLIX.COM"), "NETFLIX COM")

    def test_handles_none(self):
        self.assertEqual(normalize(None), "")


class BuiltInRuleTests(unittest.TestCase):
    def test_every_builtin_category_is_valid(self):
        for _pattern, category in BUILTIN_RULES:
            self.assertIn(category, CATEGORY_ORDER)

    def test_common_merchants_match(self):
        engine = RuleEngine()
        self.assertEqual(engine.match("WAL*MART SUPERCTR 2244"), "groceries")
        self.assertEqual(engine.match("netflix.com 4085551234 CA"), "subscriptions")
        self.assertEqual(engine.match("SHELL OIL 5288 OMAHA"), "gas & fuel")
        self.assertEqual(engine.match("CVS/PHARMACY #4431"), "healthcare & pharmacy")

    def test_match_is_case_and_spacing_forgiving(self):
        engine = RuleEngine()
        self.assertEqual(engine.match("  netFLIX.com"), "subscriptions")
        self.assertEqual(engine.match("wal mart supercenter"), "groceries")

    def test_no_builtin_match_returns_none(self):
        engine = RuleEngine()
        self.assertIsNone(engine.match("ZEBRAS AND CUPCAKES CO"))
        self.assertIsNone(engine.match(""))
        self.assertIsNone(engine.match(None))


class UserRuleTests(unittest.TestCase):
    def test_user_rules_win_over_builtins(self):
        engine = RuleEngine([{"pattern": "amazon", "category": "fees & charges"}])
        self.assertEqual(engine.match("AMAZON.COM*MKTGP3412"), "fees & charges")

    def test_invalid_entries_are_dropped(self):
        engine = RuleEngine([{"pattern": "amazon", "category": "made-up place"}])
        self.assertEqual(engine.match("AMAZON.COM"), "shopping")

    def test_from_file_loads_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rules.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"rules": [{"pattern": "bob's donuts", "category": "dining out"}]}, fh)
            engine = RuleEngine.from_file(path)
            self.assertEqual(engine.match("BOB'S DONUTS #12"), "dining out")

    def test_from_file_missing_file_is_empty_engine(self):
        engine = RuleEngine.from_file("/tmp/definitely-not-here-rules.json")
        self.assertEqual(engine.user_rules, [])

    def test_round_trip_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rules.json")
            engine = RuleEngine([{"pattern": "ACME", "category": "shopping"}])
            engine.to_file(path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertEqual(data["rules"][0]["category"], "shopping")
            reloaded = RuleEngine.from_file(path)
            self.assertEqual(reloaded.match("ACME HARDWARE"), "shopping")


class ExactPatternTests(unittest.TestCase):
    def test_leading_equals_requires_full_match(self):
        engine = RuleEngine([{"pattern": "=hash house llc", "category": "other"}])
        self.assertEqual(engine.match("HASH HOUSE LLC"), "other")
        self.assertIsNone(engine.match("HASH HOUSE LLC PAYMENT"))

    def test_exact_is_normalized_too(self):
        engine = RuleEngine([{"pattern": "=  HASH   HOUSE LLC", "category": "other"}])
        self.assertEqual(engine.match("hash   house llc"), "other")


class LearnTests(unittest.TestCase):
    def test_learn_appends_unique_pairs(self):
        engine = RuleEngine()
        engine.learn([("Zoe's Diner", "dining out"), ("Acme", "shopping")])
        engine.learn([("Zoe's Diner again", "dining out")])
        engine.learn([("Zoe's Diner", "dining out")])  # duplicate, ignored
        patterns = [p for p, _, _exact in engine.user_rules]
        self.assertIn("ZOE S DINER", patterns)
        self.assertIn("ACME", patterns)
        self.assertEqual(len(patterns), 3)

    def test_learned_rules_are_persisted_and_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "rules.json")
            engine = RuleEngine()
            engine.learn([("Quirk Mart", "groceries")])
            engine.to_file(path)
            reloaded = RuleEngine.from_file(path)
            self.assertEqual(reloaded.match("QUIRK MART #9"), "groceries")

    def test_learn_skips_invalid_category(self):
        engine = RuleEngine()
        engine.learn([("Sketchy Payee", "crypto gains")])
        self.assertEqual(engine.user_rules, [])


if __name__ == "__main__":
    unittest.main()
