"""Command line interface for expense-tagger.

Typical flow:

    expense-tagger run bank.csv            # dry run: proposals + diff, nothing written
    expense-tagger run bank.csv --apply    # diff first, then write <input>_tagged.csv
    expense-tagger run bank.csv --apply -y # for scripts / piped workflows
    expense-tagger summary bank.csv        # monthly totals
    expense-tagger categories              # list the plain-English category names
"""

import argparse
import os
import sys

from . import __version__
from . import diff as diffmod
from . import summary as summarymod
from . import io_utils
from .categories import CATEGORY_ORDER
from .llm import propose_unresolved
from .rules import RuleEngine

DEFAULT_RULES_PATH = "expense_rules.json"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="expense-tagger",
        description=(
            "Tag bank-export CSVs into plain-English categories. "
            "Rules first, optional local LLM second, dry-run-with-diff always. "
            "All data stays on your machine."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="propose categories, show diff, optionally write"
    )
    run_parser.add_argument("input", help="bank-export CSV file")
    run_parser.add_argument(
        "--out", help="write here when --apply is used (default: <input>_tagged.csv)"
    )
    run_parser.add_argument("--rules", default=DEFAULT_RULES_PATH, help="JSON rules file")
    run_parser.add_argument(
        "--learn",
        action="store_true",
        help="save this run's labels as rules for repeat merchants",
    )
    run_parser.add_argument(
        "--llm",
        metavar="URL",
        help="OpenAI-compatible base URL, e.g. Ollama http://localhost:11434/v1",
    )
    run_parser.add_argument(
        "--model", default="llama3.2", help="model name for --llm (default: llama3.2)"
    )
    run_parser.add_argument(
        "--apply", action="store_true", help="write the tagged CSV (diff is shown first)"
    )
    run_parser.add_argument(
        "-y", "--yes", action="store_true", help="skip the write confirmation (for scripts)"
    )

    stat_parser = subparsers.add_parser("summary", help="monthly totals by category")
    stat_parser.add_argument("input", help="bank-export CSV file (tagged or not)")
    stat_parser.add_argument("--rules", default=DEFAULT_RULES_PATH, help="JSON rules file")

    subparsers.add_parser("categories", help="list category names")
    return parser


def _columns_or_fail(input_path, columns):
    """Explain kindly and stop if the CSV does not look like a bank export."""
    missing = [role for role in ("date", "description") if role not in columns]
    if missing:
        print(
            f"could not find a {'/'.join(missing)} column in {input_path}; "
            "expected headers like Date, Description, Amount (or Debit/Credit)",
            file=sys.stderr,
        )
        return False
    if "amount" not in columns and not ({"debit", "credit"} <= set(columns)):
        print(
            f"could not find an amount in {input_path}; "
            "expected an Amount column, or Debit and Credit columns",
            file=sys.stderr,
        )
        return False
    return True


def _resolve_rows(rows, columns, engine, args):
    """Fill row["_resolved"] in place: existing category > rules > local LLM.

    Returns (resolved, from_llm) keyed by row index so the proposal table can
    show where each label came from.
    """
    category_column = columns.get("category") or "Category"
    resolved = {}
    from_llm = {}
    for idx, row in enumerate(rows):
        existing = (row.get(category_column, "") or "").strip()
        if existing:
            row["_resolved"] = existing
            resolved[idx] = existing
            continue
        matched = engine.match(row.get(columns.get("description", ""), ""))
        row["_resolved"] = matched
        if matched:
            resolved[idx] = matched

    if args.llm:
        unresolved = [idx for idx, row in enumerate(rows) if not row["_resolved"]]
        if unresolved:
            print(
                f"asking {args.model} at {args.llm} about {len(unresolved)} unresolved row(s)..."
            )
            proposed = propose_unresolved(rows, columns, args.llm, args.model)
            for idx, category in proposed.items():
                rows[idx]["_resolved"] = category
                resolved[idx] = category
                from_llm[idx] = True
    return resolved, from_llm


def _print_proposals(rows, columns, from_llm):
    print()
    print("Proposed labels")
    print("-" * 78)
    any_shown = False
    for idx in sorted(set(from_llm) | {i for i, r in enumerate(rows) if r["_resolved"]}):
        category = rows[idx]["_resolved"]
        if not category:
            continue
        any_shown = True
        description = (rows[idx].get(columns.get("description", ""), "") or "").strip() or "(blank)"
        amount = io_utils.row_amount(rows[idx], columns)
        amount_text = summarymod.fmt_money(amount) if amount is not None else "n/a"
        source = "LLM" if idx in from_llm else "rule"
        print(f"{source:>8}  {category:<22} {amount_text:>10}  {description[:38]}")
    if not any_shown:
        print("  (nothing to label)")
    print("-" * 78)


def _build_output_args(fieldnames, rows, columns):
    """Rows ready for CSV output: category filled in, helper keys dropped."""
    category_column = columns.get("category") or "Category"
    out_fieldnames = list(fieldnames)
    if category_column not in out_fieldnames:
        out_fieldnames.append(category_column)
    out_rows = []
    for row in rows:
        out_row = {name: row.get(name, "") for name in out_fieldnames}
        out_row[category_column] = row.get("_resolved") or ""
        out_rows.append(out_row)
    return out_fieldnames, out_rows, category_column


def cmd_run(args):
    if not os.path.isfile(args.input):
        print(f"file not found: {args.input}", file=sys.stderr)
        return 2

    fieldnames, rows = io_utils.read_rows(args.input)
    columns = io_utils.detect_columns(fieldnames)
    if not _columns_or_fail(args.input, columns):
        return 2

    engine = RuleEngine.from_file(args.rules)
    resolved, from_llm = _resolve_rows(rows, columns, engine, args)
    _print_proposals(rows, columns, from_llm)
    print(
        f"{len(resolved)} of {len(rows)} row(s) labeled "
        f"({len(rows) - len(resolved)} left untagged)"
    )

    out_fieldnames, out_rows, _category_column = _build_output_args(fieldnames, rows, columns)
    out_path = args.out or os.path.splitext(args.input)[0] + "_tagged.csv"

    with open(args.input, "r", encoding="utf-8-sig", newline="") as fh:
        old_text = fh.read()
    new_text = io_utils.rows_to_text(out_fieldnames, out_rows)
    diff_lines = diffmod.render_diff(old_text, new_text, args.input, out_path)

    print()
    print("Diff preview (dry run)")
    print("-" * 78)
    if diff_lines:
        sys.stdout.writelines(diff_lines)
        added, removed = diffmod.summarize_diff(diff_lines)
        print("-" * 72)
        print(f"{added} line(s) added, {removed} removed -> {out_path}")
    else:
        print("  no changes needed; file is already fully tagged")

    if args.learn:
        learnable = []
        for idx, category in sorted(resolved.items()):
            already_in_file = bool(
                (rows[idx].get(columns.get("category") or "Category", "") or "").strip()
            )
            if already_in_file:
                continue  # the file came with this one; nothing learned today
            description = (
                rows[idx].get(columns.get("description", ""), "") or ""
            ).strip()
            if description and category:
                learnable.append((description, category))
        learnable = sorted(set(learnable))
        if learnable:
            engine.learn(learnable)
            print(f"learned {len(learnable)} new rule(s) -> {args.rules}")
        engine.to_file(args.rules)

    allowed, message = diffmod.ensure_apply_allowed(args.apply, getattr(args, "yes", False), sys.stdin.isatty())
    if not allowed:
        if message:
            print(message)
        return 0

    if diff_lines:
        if not getattr(args, "yes", False) and sys.stdin.isatty():
            answer = input(f"write tagged file to {out_path}? [y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("cancelled; nothing written")
                return 0
        io_utils.write_rows(out_path, out_fieldnames, out_rows)
        print(f"wrote {out_path}")
    else:
        print("nothing to write")
    return 0


def cmd_summary(args):
    if not os.path.isfile(args.input):
        print(f"file not found: {args.input}", file=sys.stderr)
        return 2
    fieldnames, rows = io_utils.read_rows(args.input)
    columns = io_utils.detect_columns(fieldnames)
    if not _columns_or_fail(args.input, columns):
        return 2
    category_column = columns.get("category")
    if category_column:
        # Fill blanks in memory so the monthly view is never half-empty.
        engine = RuleEngine.from_file(args.rules)
        for row in rows:
            existing = (row.get(category_column, "") or "").strip()
            if not existing:
                row[category_column] = engine.match(row.get(columns.get("description", ""), "")) or ""
    else:
        engine = RuleEngine.from_file(args.rules)
        category_column = "Category"
        for row in rows:
            row[category_column] = engine.match(row.get(columns.get("description", ""), "")) or ""
        columns = dict(columns, category=category_column)
    print(summarymod.format_monthly_totals(rows, columns))
    return 0


def cmd_categories():
    for category in CATEGORY_ORDER:
        print(category)
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "summary":
        return cmd_summary(args)
    if args.command == "categories":
        return cmd_categories()
    parser.error("unknown command")


if __name__ == "__main__":
    sys.exit(main())
