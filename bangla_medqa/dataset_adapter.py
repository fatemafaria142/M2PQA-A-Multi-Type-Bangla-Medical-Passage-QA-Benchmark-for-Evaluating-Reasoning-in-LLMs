"""Convert MedQA.json rows into InputDocument (one row = six questions, one context)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from bangla_medqa.schemas import InputDocument, InputMeta, InputBatch, PromptStrategy
from bangla_medqa.tasks import ensure_question_keys


def _get(record: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in record:
            return record[k]
    return None


def _bangla_context(record: dict[str, Any]) -> str:
    for k, v in record.items():
        if str(k).strip() == "Bangla_Context":
            return str(v) if v is not None else ""
    return ""


FIELD_MAP: list[tuple[str, str, str]] = [
    ("factoid", "Factoid_Question", "Factoid_Answer"),
    ("confirmation", "Confirmation_Question", "Confirmation_Answer"),
    ("list", "List_Question", "List_Answer"),
    ("casual", "Casual_Question", "Casual_Answer"),
    ("temporal", "Temporal_Question", "Temporal_Answer"),
    ("unanswerable", "Unanswerable_Question", "Unanswerable_Answer"),
]


def medqa_row_to_document(record: dict[str, Any], prefix_id: str) -> InputDocument:
    """
    One MedQA row → one ``InputDocument`` (shared Bangla context, six questions + gold).
    """
    ctx = _bangla_context(record)
    questions: dict[str, str] = {}
    gold: dict[str, str | None] = {}
    for tkey, qk, ak in FIELD_MAP:
        q = _get(record, qk)
        a = _get(record, ak)
        questions[tkey] = str(q).strip() if q else ""
        gold[tkey] = str(a).strip() if a is not None else None
    return InputDocument(
        id=prefix_id,
        context=ctx,
        questions=ensure_question_keys(questions),
        gold_answers=gold,
    )


def load_medqa_json(
    path: str | Path,
    *,
    limit: int | None = None,
    prompt_strategy: PromptStrategy = PromptStrategy.zero_shot,
) -> InputBatch:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("MedQA.json must be a JSON array")
    docs: list[InputDocument] = []
    for i, row in enumerate(raw):
        if limit is not None and i >= limit:
            break
        rec = row if isinstance(row, dict) else {}
        rid = rec.get("id")
        pid = str(rid) if rid is not None else f"doc_{i}"
        docs.append(medqa_row_to_document(rec, pid))
    return InputBatch(
        meta=InputMeta(
            source_file=str(path),
            prompt_strategy=prompt_strategy,
        ),
        documents=docs,
    )


def iter_medqa_items(path: str | Path, limit_docs: int | None = None) -> Iterator[InputDocument]:
    batch = load_medqa_json(path, limit=limit_docs)
    yield from batch.documents


def load_medqa_rows(path: str | Path) -> list[dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("MedQA file must be a JSON array of documents")
    return [r for r in raw if isinstance(r, dict)]


def documents_from_indices(rows: list[dict[str, Any]], doc_indices: list[int]) -> list[InputDocument]:
    out: list[InputDocument] = []
    for i in doc_indices:
        if i < 0 or i >= len(rows):
            continue
        row = rows[i]
        rid = row.get("id") if isinstance(row, dict) else None
        pid = str(rid) if rid is not None else f"doc_{i}"
        out.append(medqa_row_to_document(row, pid))
    return out


def eval_document_indices(
    n_rows: int,
    *,
    full: bool,
    num_eval_documents: int | None,
) -> list[int]:
    if full:
        return list(range(0, n_rows))
    if num_eval_documents is None or num_eval_documents <= 0:
        return []
    return list(range(0, min(num_eval_documents, n_rows)))
