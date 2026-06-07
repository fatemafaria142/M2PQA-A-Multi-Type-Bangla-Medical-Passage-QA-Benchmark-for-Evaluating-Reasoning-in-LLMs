"""MedQA task types: one shared context, six question styles."""

from __future__ import annotations

TASK_KEYS: tuple[str, ...] = (
    "factoid",
    "confirmation",
    "list",
    "casual",
    "temporal",
    "unanswerable",
)

# Labels used when formatting the six questions for the prompt (English headers).
TASK_LABELS_EN: dict[str, str] = {
    "factoid": "Factoid",
    "confirmation": "Confirmation (yes/no)",
    "list": "List",
    "casual": "Casual / definitional",
    "temporal": "Temporal",
    "unanswerable": "Unanswerable / not in passage",
}

# MedQA-style exported field names (model JSON + dataset rows).
TASK_QUESTION_FIELDS: dict[str, tuple[str, str]] = {
    "factoid": ("Factoid_Question", "Factoid_Answer"),
    "confirmation": ("Confirmation_Question", "Confirmation_Answer"),
    "list": ("List_Question", "List_Answer"),
    "casual": ("Casual_Question", "Casual_Answer"),
    "temporal": ("Temporal_Question", "Temporal_Answer"),
    "unanswerable": ("Unanswerable_Question", "Unanswerable_Answer"),
}

GENERATED_RESPONSE_KEYS: dict[str, str] = {
    "factoid": "Generated_Factoid_Response",
    "confirmation": "Generated_Confirmation_Response",
    "list": "Generated_List_Response",
    "casual": "Generated_Casual_Response",
    "temporal": "Generated_Temporal_Response",
    "unanswerable": "Generated_Unanswerable_Response",
}

GENERATED_CHAIN_KEYS: dict[str, str] = {
    "factoid": "Generated_Factoid_Chain_of_Thought",
    "confirmation": "Generated_Confirmation_Chain_of_Thought",
    "list": "Generated_List_Chain_of_Thought",
    "casual": "Generated_Casual_Chain_of_Thought",
    "temporal": "Generated_Temporal_Chain_of_Thought",
    "unanswerable": "Generated_Unanswerable_Chain_of_Thought",
}


def format_questions_block(questions: dict[str, str]) -> str:
    """Build a single user-readable block with all six Bangla questions."""
    parts: list[str] = []
    for key in TASK_KEYS:
        label = TASK_LABELS_EN.get(key, key)
        q = (questions.get(key) or "").strip()
        parts.append(f"**{label} ({key})**\n\n{q}\n")
    return "\n".join(parts).strip()


def ensure_question_keys(q: dict[str, str]) -> dict[str, str]:
    out = {k: (q.get(k) or "").strip() for k in TASK_KEYS}
    return out


def empty_predictions() -> dict[str, str]:
    return {k: "" for k in TASK_KEYS}


def uses_generated_medqa_keys(obj: dict[str, object]) -> bool:
    """True if model returned MedQA ``Generated_*_Response`` keys."""
    markers = tuple(GENERATED_RESPONSE_KEYS[t] for t in ("factoid", "confirmation"))
    return any(k in obj for k in markers)


def normalize_chain_text(value: object) -> str:
    """Turn model chain-of-thought field into a single Bangla string."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(str(x).strip() for x in value if str(x).strip())
    return str(value).strip()
