"""Optional local LLM labeling via an OpenAI-compatible chat endpoint.

Works with Ollama (http://localhost:11434/v1), llamafile, LM Studio,
llama.cpp server, or anything else that speaks the OpenAI chat format with
no API key. Only rows the deterministic rules could not resolve reach the
model, and a failure never stops the run.
"""

import json
import urllib.error
import urllib.request

DEFAULT_TIMEOUT_SECONDS = 30
MAX_PROMPTED_ROWS = 50


def build_prompt(descriptions):
    """Ask for one plain-English category per description, JSON only."""
    allowed = (
        "groceries; dining out; gas & fuel; utilities; rent & mortgage; "
        "phone & internet; insurance; healthcare & pharmacy; shopping; "
        "subscriptions; entertainment; travel; fees & charges; "
        "income & deposits; transfers & payments; other"
    )
    listing = "\n".join(f"  - {d}" for d in descriptions)
    return (
        "You are labeling bank transactions for a small ledger.\n"
        "Pick the single best category for each description.\n"
        f"Allowed categories: {allowed}\n"
        "Reply with JSON only: {\"items\":[{\"description\":\"<exact text>\","
        "\"category\":\"<from the list>\"}]}\n"
        "Descriptions:\n" + listing
    )


def call_llm(base_url, model, prompt, timeout=DEFAULT_TIMEOUT_SECONDS):
    """POST /chat/completions on an OpenAI-compatible local server.

    Returns the message content string, or raises RuntimeError with a
    friendly message. urllib only; no dependencies, no API key headers.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise RuntimeError(f"could not reach LLM at {url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"non-JSON response from {url}") from exc
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"unexpected response shape from {url}") from exc


def parse_labels(content):
    """Extract {description: category} from the model's reply.

    Handles plain JSON, fenced ```json blocks, and the JSON first thing in
    a chatty reply. Unknown categories become None and are dropped.
    """
    from .categories import CATEGORY_SET

    text = (content or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    items = data.get("items") if isinstance(data, dict) else None
    labels = {}
    if not isinstance(items, list):
        return {}
    for item in items:
        if not isinstance(item, dict):
            continue
        description = str(item.get("description", "")).strip()
        category = str(item.get("category", "")).strip().lower()
        if description and category in CATEGORY_SET:
            labels[description] = category
    return labels


def propose_unresolved(rows, columns, base_url, model):
    """Ask the local model to label only the rows with no category yet.

    Returns {index: category} keyed by row index. Never raises: an
    unreachable endpoint or unusable reply yields an empty result.
    """
    pending = [
        (idx, rows[idx].get(columns.get("description", ""), ""))
        for idx in range(len(rows))
        if not rows[idx].get(columns.get("category", ""), "").strip()
        and rows[idx].get(columns.get("description", ""), "").strip()
    ]
    if not pending:
        return {}
    pending = pending[:MAX_PROMPTED_ROWS]
    try:
        content = call_llm(base_url, model, build_prompt([d for _, d in pending]))
        labels = parse_labels(content)
    except RuntimeError:
        return {}
    by_description = {normalize_key(desc): category for desc, category in labels.items()}
    proposed = {}
    for idx, description in pending:
        category = by_description.get(normalize_key(description))
        if category:
            proposed[idx] = category
    return proposed


def normalize_key(description):
    """Stable key so the model's copy of a description can be matched back."""
    return " ".join(description.split()).casefold().strip()
