"""Run Bangla MedQA: one LLM call per document → six task answers (optional CoT)."""

from __future__ import annotations

from typing import Optional

from tqdm import tqdm

from bangla_medqa.config import GENERATION_MODEL, MAX_TOKENS, MULTITASK_MAX_TOKENS
from bangla_medqa.llm_client import (
    chat_complete,
    parse_json_response,
    parse_six_task_output,
)
from bangla_medqa.prompt_loader import format_document_message, load_prompt_file
from bangla_medqa.schemas import (
    InputBatch,
    OutputBatch,
    OutputDocument,
    OutputMeta,
    PromptStrategy,
)
from bangla_medqa.tasks import format_questions_block


def _split_system_user(md: str) -> tuple[str, str]:
    if "---SYSTEM" in md and "---USER" in md:
        parts = md.split("---SYSTEM", 1)[1]
        sys_part, user_part = parts.split("---USER", 1)
        return sys_part.strip(), user_part.strip()
    return (
        "You are a medical AI assistant. Follow the user message exactly.",
        md.strip(),
    )


def run_batch(
    batch: InputBatch,
    *,
    model: Optional[str] = None,
    prompt_strategy: Optional[PromptStrategy] = None,
) -> OutputBatch:
    strat = prompt_strategy or batch.meta.prompt_strategy
    md = load_prompt_file(strat.value)
    system, user_template = _split_system_user(md)
    mdl = model or batch.meta.model or GENERATION_MODEL
    cot = strat == PromptStrategy.few_shot_cot
    use_tokens = max(MULTITASK_MAX_TOKENS, MAX_TOKENS)

    results: list[OutputDocument] = []
    for doc in tqdm(
        batch.documents,
        desc="Bangla MedQA generate",
        unit="doc",
    ):
        q_block = format_questions_block(doc.questions)
        user = format_document_message(
            user_template,
            context=doc.context or "",
            questions_block=q_block,
            doc_id=(doc.id or "").strip(),
        )
        try:
            raw = chat_complete(system=system, user=user, model=mdl, max_tokens=use_tokens)
            obj = parse_json_response(raw)
            preds, preds_cot = parse_six_task_output(obj, cot=cot)
            results.append(
                OutputDocument(
                    id=doc.id,
                    context=doc.context or None,
                    questions=doc.questions,
                    gold_answers=doc.gold_answers,
                    predictions=preds,
                    predictions_cot=preds_cot,
                    raw_model_output=raw,
                )
            )
        except Exception as e:
            results.append(
                OutputDocument(
                    id=doc.id,
                    context=doc.context or None,
                    questions=doc.questions,
                    gold_answers=doc.gold_answers,
                    raw_model_output="",
                    error=str(e),
                )
            )

    meta = OutputMeta(
        prompt_strategy=strat.value,
        model=mdl,
        input_source=batch.meta.source_file,
        n_documents=len(results),
    )
    return OutputBatch(meta=meta, results=results)
