"""Tests for the monthly totals summary."""

import unittest

from expense_tagger.io_utils import detect_columns, to_decimal
from expense_tagger.summary import _month_of, format_monthly_totals, monthly_totals, fmt_money


def _columns():
    return detect_columns(["Date", "Description", "Amount", "Category"])


class MonthParsingTests(unittest.TestCase):
    def test_iso_date(self):
        self.assertEqual(_month_of("2026-03-14"), "2026-03")

    def test_us_date(self):
        self.assertEqual(_month_of("3/14/2026"), "2026-03")

    def test_blank_or_garbage(self):
        self.assertEqual(_month_of(""), "")
        self.assertEqual(_month_of("not a date"), "")


class ToDecimalTests(unittest.TestCase):
    def test_currency_and_thousands(self):
        self.assertEqual(to_decimal("$1,234.56"), 1234.56)

    def test_parentheses_are_negative(self):
        self.assertEqual(to_decimal("(12.50)"), -12.5)

    def test_garbage_is_none(self):
        self.assertIsNone(to_decimal("kiosk coffee"))
        self.assertIsNone(to_decimal(""))
        self.assertIsNone(to_decimal(None))


class MonthlyTotalsTests(unittest.TestCase):
    def test_groups_by_month_and_category(self):
        rows = [
            {"Date": "2026-03-01", "Description": "WALMART", "Amount": "-52.20", "Category": "groceries"},
            {"Date": "2026-03-09", "Description": "NETFLIX", "Amount": "-15.99", "Category": "subscriptions"},
            {"Date": "2026-03-20", "Description": "WALMART", "Amount": "-40.00", "Category": "groceries"},
            {"Date": "2026-04-02", "Description": "PAYROLL", "Amount": "2200.00", "Category": "income & deposits"},
        ]
        columns = _columns()
        totals = monthly_totals(rows, columns)
        self.assertEqual(totals["2026-03"]["groceries"], -92.2)
        self.assertEqual(totals["2026-03"]["subscriptions"], -15.99)
        self.assertEqual(totals["2026-04"]["income & deposits"], 2200.0)

    def test_untagged_rows_get_untagged_bucket(self):
        rows = [
            {"Date": "2026-05-11", "Description": "MYSTERY LLC", "Amount": "-9.00", "Category": ""},
        ]
        totals = monthly_totals(rows, _columns())
        self.assertEqual(totals["2026-05"]["untagged"], -9.0)

    def test_signed_debit_credit_columns(self):
        fields = ("Date", "Description", "Debit", "Credit", "Category")
        columns = detect_columns(list(fields))
        rows = [
            {"Date": "2026-01-05", "Description": "GROCERY", "Debit": "40.00", "Credit": "", "Category": "groceries"},
            {"Date": "2026-01-07", "Description": "DEPOSIT", "Debit": "", "Credit": "900.50", "Category": "income & deposits"},
        ]
        totals = monthly_totals(rows, columns)
        self.assertEqual(totals["2026-01"]["groceries"], -40.0)
        self.assertEqual(totals["2026-01"]["income & deposits"], 900.5)

    def test_invalid_amount_counts_as_zero(self):
        rows = [
            {"Date": "2026-02-02", "Description": "ODD", "Amount": "n/a", "Category": "other"},
            {"Date": "2026-02-03", "Description": "OK", "Amount": "-10.00", "Category": "other"},
        ]
        totals = monthly_totals(rows, _columns())
        self.assertEqual(totals["2026-02"]["other"], -10.0)


class FormattingTests(unittest.TestCase):
    def test_money_format(self):
        self.assertEqual(fmt_money(1234.5), "$1,234.50")
        self.assertEqual(fmt_money(-40), "-$40.00")
        self.assertEqual(fmt_money(0), "$0.00")

    def test_format_includes_months_and_categories(self):
        rows = [
            {"Date": "2026-03-01", "Description": "PAY", "Amount": "100", "Category": "income & deposits"},
            {"Date": "2026-03-02", "Description": "BUY", "Amount": "-4", "Category": "groceries"},
        ]
        text = format_monthly_totals(rows, _columns())
        self.assertIn("2026-03", text)
        self.assertIn("groceries", text)
        self.assertIn("income & deposits", text)


if __name__ == "__main__":
    unittest.main()
