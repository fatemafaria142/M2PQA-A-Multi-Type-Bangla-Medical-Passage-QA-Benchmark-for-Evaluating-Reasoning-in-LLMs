"""Load and save JSON batches."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Union

from bangla_medqa.schemas import InputBatch, InputMeta, OutputBatch, OutputDocument
from bangla_medqa.tasks import (
    GENERATED_CHAIN_KEYS,
    GENERATED_RESPONSE_KEYS,
    TASK_KEYS,
    TASK_QUESTION_FIELDS,
)


def read_input_json(path: Union[str, Path]) -> InputBatch:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        raise ValueError(
            'Expected an object like {"meta": {...}, "documents": [...]}, not a top-level array. '
            "Each document must have context, questions (six keys), optional gold_answers."
        )
    if "documents" not in data:
        raise ValueError(
            'Input JSON must contain a "documents" array. Each item needs "context" and '
            '"questions" with keys: factoid, confirmation, list, casual, temporal, unanswerable.'
        )
    if "meta" not in data:
        data = {**dict(data), "meta": {}}
    return InputBatch.model_validate(data)


def normalize_output_document_id(doc_id: str | None) -> Any:
    """Use int ids when numeric (matches dataset `MedQA.json`)."""
    if doc_id is None or str(doc_id).strip() == "":
        return None
    s = str(doc_id).strip()
    if s.isdigit():
        return int(s)
    return s


def output_document_to_medqa_record(doc: OutputDocument) -> dict[str, Any]:
    """
    Flat MedQA-shaped row (same columns as ``examples/sample_output.json``):

    ``id``, ``Bangla_Context``, six question/answer pairs, six generated answers,
    and six optional chain-of-thought strings for CoT runs.
    """
    qa = doc.questions or {}
    gold = doc.gold_answers or {}

    row: dict[str, Any] = {
        "id": normalize_output_document_id(doc.id),
        "Bangla_Context": (doc.context or "").strip(),
    }

    preds = doc.predictions or {}
    cot = doc.predictions_cot or {}

    for task in TASK_KEYS:
        q_col, g_col = TASK_QUESTION_FIELDS[task]
        row[q_col] = (qa.get(task) or "").strip()
        gv = gold.get(task) if gold else None
        row[g_col] = (str(gv).strip() if gv is not None else "")
        ck = GENERATED_CHAIN_KEYS[task]
        gk = GENERATED_RESPONSE_KEYS[task]
        chain = ""
        if cot and task in cot:
            chain = str(cot[task].get("chain_of_thought") or "").strip()
        row[ck] = chain
        row[gk] = (preds.get(task) or "").strip()

    if doc.error:
        row["error"] = doc.error

    return row


def medqa_records_from_batch(batch: OutputBatch) -> list[dict[str, Any]]:
    """Flat MedQA rows only (no wrapper); one list entry per document."""
    return [output_document_to_medqa_record(r) for r in batch.results]


def write_output_json(path: Union[str, Path], batch: OutputBatch) -> None:
    """Write a JSON **array** of MedQA-shaped objects (see ``sample_output.json``). No ``meta`` envelope."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    records = medqa_records_from_batch(batch)
    p.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json_raw(path: Union[str, Path]) -> dict | list:
    return json.loads(Path(path).read_text(encoding="utf-8"))
