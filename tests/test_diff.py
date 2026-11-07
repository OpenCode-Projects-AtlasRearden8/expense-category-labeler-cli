"""Tests for diff safety: nothing writes without --apply, diffs are honest."""

import unittest

from expense_tagger.diff import ensure_apply_allowed, render_diff, summarize_diff


class RenderDiffTests(unittest.TestCase):
    def test_added_lines_are_counted(self):
        old = "a\nb\n"
        new = "a\nb\nc\n"
        diff = render_diff(old, new, "old.csv", "new.csv")
        added, removed = summarize_diff(diff)
        self.assertEqual((added, removed), (1, 0))

    def test_removed_lines_are_counted(self):
        diff = render_diff("a\nb\n", "a\n", "old.csv", "new.csv")
        added, removed = summarize_diff(diff)
        self.assertEqual((added, removed), (0, 1))

    def test_identical_text_gives_empty_diff(self):
        self.assertEqual(render_diff("same\n", "same\n", "o", "n"), [])

    def test_metadata_lines_not_counted(self):
        diff = render_diff("x\n", "x\ny\n", "old.csv", "new.csv")
        self.assertTrue(any(line.startswith("+++") for line in diff))
        added, removed = summarize_diff(diff)
        self.assertEqual((added, removed), (1, 0))

    def test_full_csv_change_appears_in_diff(self):
        old = "Date,Description,Amount\n2026-03-01,KIOSK,-4.50\n"
        new = "Date,Description,Amount,Category\n2026-03-01,KIOSK,-4.50,other\n"
        diff = render_diff(old, new, "old.csv", "new.csv")
        added, removed = summarize_diff(diff)
        self.assertEqual((added, removed), (2, 2))


class ApplyGateTests(unittest.TestCase):
    def test_no_apply_flag_means_no_write_even_if_yes(self):
        allowed, message = ensure_apply_allowed(False, True, True)
        self.assertFalse(allowed)
        self.assertIn("dry-run", message)

    def test_apply_with_yes_writes(self):
        allowed, message = ensure_apply_allowed(True, True, False)
        self.assertTrue(allowed)
        self.assertEqual(message, "")

    def test_apply_with_tty_confirms_interactively(self):
        allowed, message = ensure_apply_allowed(True, False, True)
        self.assertTrue(allowed)

    def test_apply_without_yes_in_noninteractive_refuses(self):
        # A script piping us in will piped stdin be non-tty; never write
        allowed, message = ensure_apply_allowed(True, False, False)
        self.assertFalse(allowed)
        self.assertIn("--apply needs -y", message)


if __name__ == "__main__":
    unittest.main()
