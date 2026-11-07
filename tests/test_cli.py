"""End-to-end CLI tests: dry-run safety, writing, learning, summary output."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from expense_tagger.cli import main

SAMPLE_CSV = (
    "Date,Description,Amount\n"
    "2026-03-01,WAL*MART SUPERCTR 2244,-52.20\n"
    "2026-03-02,NETFLIX.COM,-15.99\n"
    "2026-03-03,MYSTERY LLC,-30.00\n"
    "2026-03-10,WAL*MART SUPERCTR 2244,-41.10\n"
    "2026-04-01,PAYROLL DIRECT DEPOSIT,2200.00\n"
)
RULES_CSV = "Date,Description,Amount\n2026-03-01,KROGER #2217,-10.00\n"


class CliTestBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.input_csv = os.path.join(self.dir, "bank.csv")
        with open(self.input_csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(SAMPLE_CSV)

    def run_cli(self, argv, stdin_tty=False):
        """Run main() capturing output; stdout is never a real tty."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with mock.patch("sys.stdin") as mocked_stdin:
                mocked_stdin.isatty.return_value = stdin_tty
                exception = None
                try:
                    exit_code = main(argv)
                except SystemExit as exc:
                    exit_code, exception = exc.code, exc
        return exit_code, out.getvalue(), err.getvalue(), exception

    def application_path(self, name="bank_tagged.csv"):
        return os.path.join(self.dir, name)


class DryRunTests(CliTestBase):
    def test_dry_run_writes_nothing(self):
        exit_code, out, err, _ = self.run_cli(["run", self.input_csv])
        self.assertEqual(exit_code, 0, err)
        self.assertEqual(
            sorted(os.listdir(self.dir)), ["bank.csv"], "dry run must not write files"
        )
        self.assertIn("dry-run: nothing written", out)

    def test_dry_run_does_not_write_even_with_yes_flag(self):
        exit_code, out, err, _ = self.run_cli(["run", self.input_csv, "--yes"])
        self.assertEqual(exit_code, 0, err)
        self.assertEqual(sorted(os.listdir(self.dir)), ["bank.csv"])

    def test_dry_run_shows_diff_and_proposals(self):
        exit_code, out, err, _ = self.run_cli(["run", self.input_csv])
        self.assertEqual(exit_code, 0, err)
        self.assertIn("Proposed labels", out)
        self.assertIn("groceries", out)
        self.assertIn("Diff preview (dry run)", out)
        self.assertIn("+Date,Description,Amount,Category", out)

    def test_missing_file_is_a_clean_error(self):
        exit_code, out, err, _ = self.run_cli(["run", os.path.join(self.dir, "nope.csv")])
        self.assertEqual(exit_code, 2)
        self.assertIn("file not found", err)

    def test_untagged_rows_count_is_reported(self):
        exit_code, out, err, _ = self.run_cli(["run", self.input_csv])
        self.assertIn("4 of 5 row(s) labeled", out)


class ApplyTests(CliTestBase):
    def test_apply_without_y_no_tty_refuses_to_write(self):
        exit_code, out, err, _ = self.run_cli(
            ["run", self.input_csv, "--apply"], stdin_tty=False
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("--apply needs -y", out)
        self.assertNotIn("bank_tagged.csv", os.listdir(self.dir))

    def test_apply_yes_writes_tagged_file(self):
        exit_code, out, err, _ = self.run_cli(
            ["run", self.input_csv, "--apply", "-y"]
        )
        self.assertEqual(exit_code, 0, err)
        tagged = os.path.join(self.dir, "bank_tagged.csv")
        self.assertTrue(os.path.isfile(tagged))
        with open(tagged, encoding="utf-8", newline="") as fh:
            self.assertEqual(fh.read(), self._expected_tagged_text())
        self.assertIn("wrote", out)

    def _expected_tagged_text(self):
        return (
            "Date,Description,Amount,Category\r\n"
            "2026-03-01,WAL*MART SUPERCTR 2244,-52.20,groceries\r\n"
            "2026-03-02,NETFLIX.COM,-15.99,subscriptions\r\n"
            "2026-03-03,MYSTERY LLC,-30.00,\r\n"
            "2026-03-10,WAL*MART SUPERCTR 2244,-41.10,groceries\r\n"
            "2026-04-01,PAYROLL DIRECT DEPOSIT,2200.00,income & deposits\r\n"
        )

    def test_apply_to_custom_out_path(self):
        out_path = os.path.join(self.dir, "elsewhere.csv")
        self.run_cli(["run", self.input_csv, "--apply", "-y", "--out", out_path])
        self.assertTrue(os.path.isfile(out_path))

    def test_existing_categories_are_never_overwritten(self):
        with open(self.input_csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(
                "Date,Description,Amount,Category\n"
                "2026-03-01,WAL*MART SUPERCTR 2244,-52.20,MY CHOICE\n"
            )
        exit_code, out, err, _ = self.run_cli(
            ["run", self.input_csv, "--apply", "-y"]
        )
        tagged = os.path.join(self.dir, "bank_tagged.csv")
        with open(tagged, encoding="utf-8", newline="") as fh:
            content = fh.read()
        self.assertIn("MY CHOICE", content)

    def test_interactive_decline_writes_nothing(self):
        with mock.patch("builtins.input", return_value="n"):
            exit_code, out, err, _ = self.run_cli(
                ["run", self.input_csv, "--apply"], stdin_tty=True
            )
        self.assertEqual(exit_code, 0)
        self.assertIn("cancelled; nothing written", out)
        self.assertEqual(sorted(os.listdir(self.dir)), ["bank.csv"])

    def test_interactive_confirm_writes(self):
        with mock.patch("builtins.input", return_value="y"):
            exit_code, out, err, _ = self.run_cli(
                ["run", self.input_csv, "--apply"], stdin_tty=True
            )
        self.assertIn("wrote", out)
        self.assertIn("bank_tagged.csv", os.listdir(self.dir))


class LearnTests(CliTestBase):
    def test_learn_creates_rules_file(self):
        rules_file = os.path.join(self.dir, "rules.json")
        exit_code, out, err, _ = self.run_cli(
            ["run", self.input_csv, "--rules", rules_file, "--learn"]
        )
        self.assertEqual(exit_code, 0, err)
        self.assertTrue(os.path.isfile(rules_file))
        with open(rules_file, encoding="utf-8") as fh:
            data = json.load(fh)
        patterns = [rule["pattern"] for rule in data["rules"]]
        self.assertIn("WAL MART SUPERCTR 2244", patterns)

    def test_learned_rules_take_effect_next_run(self):
        rules_file = os.path.join(self.dir, "rules.json")
        with open(os.path.join(self.dir, "bank.csv"), "w", encoding="utf-8", newline="") as fh:
            fh.write(RULES_CSV)
        self.run_cli(["run", os.path.join(self.dir, "bank.csv"), "--rules", rules_file, "--learn"])
        with open(rules_file, encoding="utf-8") as fh:
            learned = json.load(fh)["rules"]
        self.assertTrue(any(rule["pattern"] == "KROGER 2217" for rule in learned))
        second_exit, second_out, second_err, _ = self.run_cli(
            ["run", os.path.join(self.dir, "bank.csv"), "--rules", rules_file]
        )
        self.assertEqual(second_exit, 0, second_err)
        # The learned rule now resolves the whole description, not just "KROGER".
        self.assertRegex(second_out, r"rule\s+groceries\s+-\$10\.00")

    def test_learn_does_not_add_rules_for_preexisting_categories(self):
        rules_file = os.path.join(self.dir, "rules.json")
        with open(self.input_csv, "w", encoding="utf-8", newline="") as fh:
            fh.write("Date,Description,Amount,Category\n2026-03-01,AGE-OLD CO,-5.00,past\n")
        self.run_cli(["run", self.input_csv, "--rules", rules_file, "--learn"])
        with open(rules_file, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["rules"], [])


class SummaryTests(CliTestBase):
    def test_summary_prints_monthly_totals(self):
        exit_code, out, err, _ = self.run_cli(["summary", self.input_csv])
        self.assertEqual(exit_code, 0, err)
        self.assertIn("2026-03", out)
        self.assertIn("groceries", out)
        self.assertIn("2026-04", out)

    def test_summary_tags_from_rules_even_without_category_column(self):
        exit_code, out, err, _ = self.run_cli(["summary", self.input_csv])
        self.assertIn("subscriptions", out)
        self.assertIn("-$15.99", out)

    def test_summary_missing_file(self):
        exit_code, out, err, _ = self.run_cli(["summary", os.path.join(self.dir, "nope.csv")])
        self.assertEqual(exit_code, 2)

    def test_categories_lists_plain_english_names(self):
        exit_code, out, err, _ = self.run_cli(["categories"])
        self.assertEqual(exit_code, 0)
        self.assertIn("groceries", out)
        self.assertIn("rent & mortgage", out)


if __name__ == "__main__":
    unittest.main()
