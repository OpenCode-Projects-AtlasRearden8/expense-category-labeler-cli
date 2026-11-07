# expense-tagger

Tag bank-export CSVs into **plain-English categories** for a personal or
tiny-business ledger.

Deterministic rules handle your repeat merchants first. Anything still
unresolved can optionally be labeled by a **local** OpenAI-compatible endpoint
(Ollama included — no API keys, no cloud, no guessing about who sees your
statements). Every run shows a **dry-run diff before anything is written**, and
you get a **monthly totals summary** for free.

Built the plain-English way, by [Asdale Dynamics, LLC](https://dylanasdale.github.io) —
AI and small-business tools explained like a friend would.

---

## Why this exists

Most expense tools either want your bank login or make you learn a schema.
This one takes the CSV your bank already gives you, keeps every byte on your
machine, and fills in a `Category` column using words like `groceries`,
`dining out`, and `fees & charges`.

## Quick start

```bash
# install (Python 3.9+; nothing else is required)
pip install -e .

# try it: this is ALWAYS a dry run, nothing is written
expense-tagger run bank_statement.csv

# you've seen the diff and you like it — write the tagged copy
expense-tagger run bank_statement.csv --apply          # asks [y/N] first
expense-tagger run bank_statement.csv --apply -y       # for scripts

# teach tools your bookkeeping and remember repeat merchants
expense-tagger run bank_statement.csv --learn          # saves expense_rules.json

# monthly totals by category
expense-tagger summary bank_statement.csv

# list the category names
expense-tagger categories
```

Columns are detected automatically from common bank-export headers:
`Date`/`Posted Date`, `Description`/`Payee`/`Merchant`/`Details`,
`Amount` **or** separate `Debit` and `Credit` columns. Output defaults to
`<input>_tagged.csv` (use `--out` to choose another name).

## How labeling works (in order)

1. **Your file's own `Category` column** is respected and never overwritten.
2. **Rules for repeat merchants** — substring matches on the description,
   case/spacing forgiving (`WAL*MART SUPERCTR 2244` → `groceries`). User rules
   from `expense_rules.json` win over the built-in list, and `--learn` turns
   this run's labels into rules for next time.
3. **Optional local LLM** — for rows the rules can't resolve, ask your own
   server. Example with Ollama (no keys, data never leaves your machine):

   ```bash
   ollama serve &                                  # if it isn't running
   ollama pull llama3.2                            # any small instruct model
   expense-tagger run bank_statement.csv --llm http://localhost:11434/v1 --model llama3.2
   ```

   Works with anything OpenAI-compatible on localhost: Ollama, LM Studio,
   llama.cpp's server, etc. If the model is down or answers nonsense, the run
   continues — those rows just stay untagged.

## Safety first: dry-run-with-diff, always

Every `run` prints proposed labels plus a unified diff of exactly what writing
would change. Writing requires `--apply`, and even then:

- interactive session → `--apply` asks `[y/N]` after showing the diff;
- scripts/pipes → `--apply` without `-y` **refuses to write**;
- there is no in-place mode by default; output is a new `_tagged.csv` file
  (your original is never modified).

## Rules file

`expense_rules.json` (created by `--learn`, or hand-edit freely):

```json
{
  "rules": [
    {"pattern": "KROGER #2217", "category": "groceries"},
    {"pattern": "=HASH HOUSE LLC", "category": "other"}
  ]
}
```

Patterns are case-insensitive substrings; a `=` prefix means "this exact payee
only". Categories must be one of `expense-tagger categories`.

## Monthly summary

`expense-tagger summary bank_statement.csv` prints per-month, per-category
totals (spends stay negative, deposits positive) and buckets anything still
untagged under `untagged`, so nothing silently disappears from your books.

## Privacy

- All parsing, matching, and writing happens locally in standard Python.
- The optional LLM call goes only to the URL you pass with `--llm` — use a
  localhost endpoint and your statements never touch the internet.
- No accounts, no telemetry, no secrets. Sample data in `tests/` is synthetic.

## Specifying columns

Standard headers are auto-detected; if your export uses unusual names
(`Transaction Date`? `Memo`?), the tool matches hints like `date`,
`description`, `payee`, `merchant`, `amount`, `debit`, `credit`. Amounts can
carry `$`, commas, or `(parentheses)` for negatives.

## Development

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
# or via pytest, if you have it: pytest tests
```

Tests cover rule matching (built-ins, user rules, learning, exact `=` payees)
and diff safety (dry runs write nothing; non-interactive `--apply` without
`-y` refuses; `--apply -y` writes exactly the diff you saw).

## Status

Early beta. See `STATUS.md` for what works, verification results, and known
gaps.

## Related tools

- **cashflow-simple-ledger** — a manual ledger, if you want simple
  record-keeping instead of auto-categorizing an export.
- **csv-cleanup-companion-cli** — generic CSV cleaning (dedupe, repair,
  restructure) rather than ledger-specific categorization.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Asdale Dynamics, LLC.
