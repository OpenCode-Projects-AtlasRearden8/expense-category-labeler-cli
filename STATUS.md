# STATUS — expense-tagger

## What was built

`expense-tagger`, a local-first Python CLI that tags bank-export CSVs into
plain-English categories for a personal or tiny-business ledger. Built by
**Asdale Dynamics, LLC** — plain English, step by step, all data local.

- **Deterministic rules first**: ~90 built-in merchant rules (groceries,
  subscriptions, gas, pharmacy, utilities, fees, insurance, income, travel,
  rent/mortgage) plus user rules in hand-editable `expense_rules.json`.
  Matching is case-, spacing-, and punctuation-forgiving
  (`WAL*MART SUPERCTR 2244` → `groceries`). Rules respect any `Category`
  column the export already carries and never overwrite it.
- **`--learn`**: turns this run's confirmed labels into rules for repeat
  merchants (normalized patterns in `expense_rules.json`), so run 2 is fully
  deterministic. Idempotent across repeated runs.
- **Optional local LLM**: `--llm http://localhost:11434/v1 --model llama3.2`
  (any OpenAI-compatible endpoint, no API keys — Ollama, LM Studio,
  llama.cpp, etc.). **Only unresolved rows** are sent, as one batched prompt,
  capped at 50 rows. Reply parsing handles plain JSON, fenced blocks, and
  chatty preambles; an unreachable or confused model never stops the run.
- **Dry-run-with-diff, always**: every `run` prints proposed labels (with
  source: rule vs LLM vs existing) plus a unified diff of exactly what
  writing would change. Writing requires `--apply`; interactive `--apply`
  prompts `[y/N]`; non-interactive `--apply` without `-y` *refuses* to write.
  Default output is a new `<input>_tagged.csv` — the original file is never
  modified in place.
- **`summary`**: monthly totals by category (spends negative, deposits
  positive), auto-tags untagged rows with rules in memory first, buckets
  anything still unknown under `untagged`. Handles ISO and US dates, `$`/
  commas/parenthesized negatives, and single `Amount` or split
  `Debit`/`Credit` columns.
- **Zero dependencies**: Python 3.9+ standard library only. No network
  except the `--llm` URL you choose (localhost by habit).

Files: `expense_tagger/` (cli, rules, llm, diff, summary, io_utils,
categories), `tests/` (56 unittest/pytest-compatible tests), `pyproject.toml`
(console script `expense-tagger`), `README.md`, `LICENSE` (MIT,
`Copyright (c) 2026 Asdale Dynamics, LLC`), `STATUS.md`.

## How to run it

```bash
pip install -e .                        # or: python -m expense_tagger.cli

expense-tagger run bank_statement.csv              # dry run, never writes
expense-tagger run bank_statement.csv --apply      # diff, then [y/N]
expense-tagger run bank_statement.csv --apply -y   # scripts
expense-tagger run bank_statement.csv --learn      # save rules for next time
expense-tagger run bank_statement.csv --llm http://localhost:11434/v1 --model llama3.2
expense-tagger summary bank_statement.csv          # monthly totals
expense-tagger categories                          # list category names
```

## Verification results (Nov 7, 2026)

- `python3 -m unittest discover -s tests` → **56 tests, OK**; `pytest tests` →
  **56 passed** (same suite via unittest run in repo root).
- `pip install -e .` in a clean venv → installs; `expense-tagger --version`
  → `expense-tagger 0.1.0`.
- Manual smoke tests:
  - dry run writes **nothing** (verified by directory diff); `--yes` without
    `--apply` also writes nothing.
  - `--apply` with piped (non-tty) stdin **refuses without `-y`**;
    `--apply -y` writes `bank_tagged.csv` matching the diff shown.
  - learnt rules: `KROGER #2217` learned on run 1 resolved run 2.
  - split Debit/`"1,900.50"` Credit + US dates + `(4.00)` negatives all
    parsed; monthly summary matched hand-computed totals.
  - fake local OpenAI-compatible server: only the unresolved row was
    prompted, `LLM` source shown, fenced/chatty reply parsed.
  - unreachable LLM (`--llm http://127.0.0.1:9/v1`): clean exit, no labels
    added, no crash.
- `py_compile` on all sources: clean. (No linter config in repo yet.)

## Known gaps

- Deterministic coverage is label-list driven: genuinely odd payees stay
  untagged until you `--learn`, hand-add a rule, or enable the local LLM.
  "untagged" is always visible in the summary, though.
- Multi-line CSV descriptions would be collapsed by the LLM round-trip key
  normalization (rare in bank exports).
- Rules stored normalized ("WAL MART SUPERCTR 2244"), not the raw payee
  string — friendlier matching, less pretty file.
- `--map-amount-to-category` style analytics (spend trends, top merchants)
  not yet built; `summary` covers only monthly totals.
- No timezone/date parsing beyond ISO and common US formats.
- Ollama model name is a CLI flag only; no auto-detection of installed
  models (`/api/tags`).
- Interactive tests mock stdin/tty; real terminal prompt behavior verified
  only for the decline path via mock.
