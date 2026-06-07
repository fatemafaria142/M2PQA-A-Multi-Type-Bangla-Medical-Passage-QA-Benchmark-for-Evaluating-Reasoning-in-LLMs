"""OpenAI-compatible chat completion with retries."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from openai import OpenAI

from bangla_medqa.config import (
    GEN_RATE_LIMIT_SECONDS,
    GENERATION_MODEL,
    MAX_API_RETRIES,
    MAX_TOKENS,
    OPENAI_API_KEY,
    RETRY_BACKOFF_SECONDS,
    TEMPERATURE,
    TOP_P,
)


def get_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")
    return OpenAI(api_key=OPENAI_API_KEY)


def chat_complete(
    *,
    system: str,
    user: str,
    model: Optional[str] = None,
    temperature: float = TEMPERATURE,
    max_tokens: int = MAX_TOKENS,
) -> str:
    client = get_client()
    m = model or GENERATION_MODEL
    last_err: Exception | None = None
    for attempt in range(MAX_API_RETRIES):
        try:
            time.sleep(GEN_RATE_LIMIT_SECONDS)
            resp = client.chat.completions.create(
                model=m,
                temperature=temperature,
                top_p=TOP_P,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            choice = resp.choices[0]
            content = choice.message.content
            if content is None:
                return ""
            return content.strip()
        except Exception as e:
            last_err = e
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise RuntimeError(f"LLM failed after {MAX_API_RETRIES} retries: {last_err}")


def extract_first_json_object(text: str) -> dict[str, Any]:
    """Find first balanced `{...}` and parse as JSON (handles nested objects)."""
    s = text.strip()
    start = s.find("{")
    if start < 0:
        return {}
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunk = s[start : i + 1]
                try:
                    obj = json.loads(chunk)
                    return obj if isinstance(obj, dict) else {}
                except json.JSONDecodeError:
                    return {}
    return {}


def parse_json_response(text: str) -> dict[str, Any]:
    """Extract JSON object from model output; tolerant of markdown fences and trailing text."""
    t = text.strip()
    fence = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", t, re.DOTALL | re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    return extract_first_json_object(t)


def parse_six_task_output(
    obj: dict[str, Any],
    *,
    cot: bool,
) -> tuple[dict[str, str], Optional[dict[str, dict[str, str]]]]:
    """
    Parse model JSON for all six MedQA tasks.

    Supported shapes:

    * **MedQA exported keys**: ``Generated_Factoid_Response``, … optional
      ``Generated_Factoid_Chain_of_Thought``, … when ``cot``.
    * **Legacy flat**: ``factoid`` … ``unanswerable`` → strings.
    * **Legacy CoT**: each task → ``{"chain_of_thought": "...", "answer": "..."}``.
    """
    from bangla_medqa.tasks import (
        GENERATED_CHAIN_KEYS,
        GENERATED_RESPONSE_KEYS,
        TASK_KEYS,
        normalize_chain_text,
        uses_generated_medqa_keys,
    )

    flat: dict[str, str] = {k: "" for k in TASK_KEYS}
    nested: dict[str, dict[str, str]] | None = None

    def fill_from_generated() -> None:
        nonlocal nested
        if cot:
            nested = {}
        for k in TASK_KEYS:
            rk = GENERATED_RESPONSE_KEYS[k]
            v = obj.get(rk)
            flat[k] = str(v).strip() if v is not None else ""
            if cot and nested is not None:
                ck = GENERATED_CHAIN_KEYS[k]
                raw_thought = obj.get(ck)
                thought = normalize_chain_text(raw_thought)
                nested[k] = {"chain_of_thought": thought, "answer": flat[k]}

    if uses_generated_medqa_keys(obj):
        fill_from_generated()
        return flat, nested

    if cot:
        nested = {}
        for k in TASK_KEYS:
            block = obj.get(k)
            if isinstance(block, dict):
                thought_raw = (
                    block.get("chain_of_thought")
                    or block.get("thinking")
                    or block.get("reasoning_steps")
                    or block.get("reasoning")
                )
                thought = normalize_chain_text(thought_raw)
                ans = str(block.get("answer") or block.get("উত্তর") or "")
                nested[k] = {"chain_of_thought": thought, "answer": ans.strip()}
                flat[k] = ans.strip()
            elif block is not None:
                flat[k] = str(block).strip()
                nested[k] = {"chain_of_thought": "", "answer": flat[k]}
        return flat, nested

    for k in TASK_KEYS:
        v = obj.get(k)
        flat[k] = str(v).strip() if v is not None else ""
    return flat, None


def split_answer_and_cot(obj: dict[str, Any], raw: str, *, cot: bool) -> tuple[str, Optional[str]]:
    if cot:
        ans = str(
            obj.get("answer")
            or obj.get("final_answer")
            or obj.get("উত্তর")
            or ""
        ).strip()
        thought = obj.get("chain_of_thought") or obj.get("thinking") or obj.get("reasoning")
        if isinstance(thought, str):
            return ans, thought.strip() or None
        return ans, None
    ans = str(obj.get("answer") or obj.get("উত্তর") or "").strip()
    if ans:
        return ans, None
    return raw, None
