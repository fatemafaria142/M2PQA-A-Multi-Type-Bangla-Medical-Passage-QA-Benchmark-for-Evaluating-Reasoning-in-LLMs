"""Load Markdown prompts from `prompt/` and fill placeholders."""

from __future__ import annotations

from pathlib import Path

from bangla_medqa.config import PROMPT_DIR


def load_prompt_file(name: str) -> str:
    """Load `prompt/{name}.md`. Name is without extension, e.g. `zero_shot`."""
    path = PROMPT_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Missing prompt file: {path}")
    return path.read_text(encoding="utf-8")


def format_user_message(
    template: str,
    *,
    context: str,
    question: str = "",
) -> str:
    """Legacy single-question placeholder (still replaces if present)."""
    t = (
        template.replace("{{context}}", context.strip())
        .replace("{{question}}", question.strip())
        .replace("{{CONTEXT}}", context.strip())
        .replace("{{QUESTION}}", question.strip())
    )
    return t


def format_document_message(
    template: str,
    *,
    context: str,
    questions_block: str,
    doc_id: str = "",
) -> str:
    """One MedQA document: id + context + block of all six Bangla questions."""
    did = doc_id.strip() if doc_id else ""
    return (
        template.replace("{{context}}", context.strip())
        .replace("{{questions_block}}", questions_block)
        .replace("{{id}}", did)
        .replace("{{CONTEXT}}", context.strip())
        .replace("{{QUESTIONS_BLOCK}}", questions_block)
        .replace("{{ID}}", did)
    )
