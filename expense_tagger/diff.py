"""Dry-run-with-diff safety helpers.

Writing a file always requires an explicit `--apply`, and even then the
unified diff is printed first. These helpers are tested so the "never touch
file unless asked" promise stays true.
"""

import difflib

DIFF_CONTEXT_LINES = 3


def render_diff(old_text, new_text, from_name, to_name):
    """Lines of a unified diff between old and new file contents."""
    return list(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=from_name,
            tofile=to_name,
            n=DIFF_CONTEXT_LINES,
        )
    )


def summarize_diff(diff_lines):
    """Return (added, removed) line counts, ignoring diff metadata lines."""
    added = 0
    removed = 0
    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def ensure_apply_allowed(apply_flag, assume_yes, stdin_is_tty):
    """Decide whether writing may proceed.

    Rules:
    - no --apply          -> never write (dry run)
    - --apply with -y     -> write
    - --apply + tty       -> ask the user after they have seen the diff
    - --apply, no tty,    -> refuse, refusing keeps scripts from nudging files
      without -y             they did not see a diff for
    """
    if not apply_flag:
        return (False, "dry-run: nothing written (add --apply to write)")
    if assume_yes:
        return (True, "")
    if stdin_is_tty:
        return (True, "")
    return (False, "--apply needs -y/--yes in non-interactive scripts")
