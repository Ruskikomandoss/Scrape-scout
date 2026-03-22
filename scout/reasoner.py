"""
Stage 4 — reasoner.py

Route selector-generation requests to one of four LLM backends:
  - Anthropic  (claude-*)
  - OpenAI     (gpt-*, o*)
  - Google     (gemini-*)
  - Ollama     (any local model via OpenAI-compatible API)

The raw model response is stored in `last_raw_response` for the UI.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import List

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Module-level variable exposed to main.py for the Reasoning Log tab
last_raw_response: str = ""

# ---------------------------------------------------------------------------
# Model registry
# Each entry: display_name -> (provider, model_id)
# ---------------------------------------------------------------------------
MODELS: dict[str, tuple[str, str]] = {
    # Anthropic
    "Claude Sonnet 4.6": ("anthropic", "claude-sonnet-4-6"),
    "Claude Opus 4.6":   ("anthropic", "claude-opus-4-6"),
    "Claude Haiku 4.5":  ("anthropic", "claude-haiku-4-5-20251001"),
    # OpenAI
    "GPT-4o":            ("openai", "gpt-4o"),
    "GPT-4o mini":       ("openai", "gpt-4o-mini"),
    "o3-mini":           ("openai", "o3-mini"),
    # Google
    "Gemini 2.0 Flash":  ("google", "gemini-2.0-flash"),
    "Gemini 1.5 Pro":    ("google", "gemini-1.5-pro"),
    "Gemini 1.5 Flash":  ("google", "gemini-1.5-flash"),
    # Ollama — model name supplied at runtime
    "Ollama (local)":    ("ollama", ""),
}

DEFAULT_MODEL = "Claude Sonnet 4.6"
_MAX_TOKENS = 4000

_SYSTEM_PROMPT = (
    "You are an expert web scraping engineer. "
    "Your response must be a single valid JSON array and nothing else. "
    "No explanation. No markdown. No prose before or after. "
    "Start your response with [ and end with ]. "
    "Each element corresponds to exactly one field from the provided catalog. "
    "Every element must have exactly these keys: "
    "field_name (string), found (boolean), css_selector (string), xpath (string), "
    "confidence (float 0.0-1.0), "
    'fragility (one of "low", "medium", "high"), '
    "fragility_reason (string), warning (string or null). "
    "If a field is not present on the page set found=false, css_selector='', xpath='', confidence=0.0. "
    "Output one object per catalog field — no more, no less. "
    "If you write anything other than a JSON array your response is invalid."
)

# Maximum number of blocks forwarded to the model.
# Sending too many causes the model to switch into explanation mode.
_MAX_BLOCKS = 25


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

def _build_user_prompt(blocks: List[dict], user_hint: str | None) -> str:
    from scout.fields import FIELD_CATALOG

    # Keep only the highest-signal blocks to stay well under token limits
    ranked = sorted(blocks, key=lambda b: b.get("type_score", 0.0), reverse=True)
    trimmed = ranked[:_MAX_BLOCKS]

    hint_line = (
        f"Focus especially on these fields or categories: {user_hint}"
        if user_hint else ""
    )
    block_data = [
        {
            "tag": b["tag"],
            "id": b["id"],
            "classes": b["classes"],
            "content_type": b["content_type"],
            "type_score": round(b["type_score"], 3),
            "entity_types": b["entity_types"],
            "text_sample": b["text_sample"],
            "candidate_selector": b["selector"],
            "candidate_xpath": b["xpath"],
        }
        for b in trimmed
    ]
    catalog_data = [
        {"field_name": f["field_name"], "description": f["description"], "category": f["category"]}
        for f in FIELD_CATALOG
    ]
    return (
        f"Return ONLY a JSON array with exactly one object per catalog field.\n"
        f"{hint_line}\n\n"
        f"Field catalog ({len(catalog_data)} fields — output one object for every field):\n"
        f"{json.dumps(catalog_data, indent=2)}\n\n"
        f"HTML blocks extracted from the page (use these to find page-specific selectors):\n"
        f"{json.dumps(block_data, indent=2)}\n\n"
        f"Rules:\n"
        f"- For standard HTML/head elements (title, meta, link) use your general knowledge of CSS selectors\n"
        f"- For content/ecommerce fields use the blocks above to find page-specific selectors\n"
        f"- Prefer semantic class names over positional selectors\n"
        f"- Flag any class that looks auto-generated (random chars, hash-like)\n"
        f"- If id exists, use it — ids are most stable\n"
        f"- If a field is not present on this page: found=false, css_selector='', xpath='', confidence=0.0\n"
    )


def _extract_json_array(text: str) -> str:
    """
    Extract the first JSON array from *text*.
    Works even when the model wraps the array in prose or markdown fences.
    Returns the extracted substring, or the original text if nothing matched.
    """
    # 1. Try to grab content inside ```...``` fences first
    fenced = re.search(r"```[a-zA-Z]*\s*(\[[\s\S]*?\])\s*```", text)
    if fenced:
        return fenced.group(1).strip()
    # 2. Find the outermost [...] span in the response
    start = text.find("[")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return text.strip()


# ---------------------------------------------------------------------------
# Provider backends
# ---------------------------------------------------------------------------

def _call_anthropic(model_id: str, user_prompt: str) -> str:
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set.")
    client = anthropic.Anthropic(api_key=api_key)
    # Prefill the assistant turn with "[" to force a JSON array response.
    message = client.messages.create(
        model=model_id,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": "["},
        ],
    )
    # Prepend the prefill character back since the model continues from it
    return "[" + "".join(b.text for b in message.content if hasattr(b, "text"))


def _call_openai(model_id: str, user_prompt: str) -> str:
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set.")
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model_id,
        max_tokens=_MAX_TOKENS,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""


def _call_google(model_id: str, user_prompt: str) -> str:
    import google.generativeai as genai
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not set.")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_id,
        system_instruction=_SYSTEM_PROMPT,
    )
    response = model.generate_content(user_prompt)
    return response.text or ""


def _call_ollama(model_id: str, user_prompt: str, base_url: str) -> str:
    from openai import OpenAI
    client = OpenAI(
        api_key="ollama",  # Ollama ignores the key but the client requires a non-empty value
        base_url=base_url,
    )
    response = client.chat.completions.create(
        model=model_id,
        max_tokens=_MAX_TOKENS,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(raw: str) -> List[dict]:
    cleaned = _extract_json_array(raw)
    try:
        selectors = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse model JSON response: %s\nRaw: %s", exc, raw)
        return []

    if not isinstance(selectors, list):
        logger.error("Model response was not a JSON array. Got: %r", type(selectors))
        return []

    normalised: List[dict] = []
    for item in selectors:
        if not isinstance(item, dict):
            continue
        normalised.append({
            "field_name":       item.get("field_name", "unknown"),
            "found":            bool(item.get("found", True)),
            "css_selector":     item.get("css_selector", ""),
            "xpath":            item.get("xpath", ""),
            "confidence":       float(item.get("confidence", 0.0)),
            "fragility":        item.get("fragility", "medium"),
            "fragility_reason": item.get("fragility_reason", ""),
            "warning":          item.get("warning") or None,
        })
    return normalised


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reason(
    blocks: List[dict],
    user_hint: str | None = None,
    model_key: str = DEFAULT_MODEL,
    ollama_model: str = "llama3.2",
    ollama_url: str = "http://localhost:11434/v1",
) -> List[dict]:
    """
    Generate selector definitions for *blocks* using the selected LLM.

    Parameters
    ----------
    blocks      : classified blocks from classifier.py
    user_hint   : optional free-text user instruction
    model_key   : key from MODELS dict (display name)
    ollama_model: Ollama model name, used only when model_key == "Ollama (local)"
    ollama_url  : Ollama API base URL
    """
    global last_raw_response
    last_raw_response = ""

    if not blocks:
        logger.warning("reasoner received empty block list — skipping LLM call.")
        return []

    if model_key not in MODELS:
        logger.error("Unknown model key: %r", model_key)
        last_raw_response = f"ERROR: Unknown model '{model_key}'."
        return []

    provider, model_id = MODELS[model_key]
    user_prompt = _build_user_prompt(blocks, user_hint)

    try:
        if provider == "anthropic":
            raw = _call_anthropic(model_id, user_prompt)
        elif provider == "openai":
            raw = _call_openai(model_id, user_prompt)
        elif provider == "google":
            raw = _call_google(model_id, user_prompt)
        elif provider == "ollama":
            effective_model = ollama_model.strip() or "llama3.2"
            raw = _call_ollama(effective_model, user_prompt, ollama_url.strip())
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    except Exception as exc:
        logger.error("LLM call failed (%s / %s): %s", provider, model_id or ollama_model, exc)
        last_raw_response = f"ERROR: LLM call failed — {exc}"
        return []

    last_raw_response = raw
    return _parse_response(raw)
