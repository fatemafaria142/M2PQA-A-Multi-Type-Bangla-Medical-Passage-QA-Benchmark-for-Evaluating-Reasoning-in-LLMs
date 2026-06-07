"""Typed JSON schemas: one MedQA document = one context + six task-specific Q/A."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from bangla_medqa.tasks import ensure_question_keys


class PromptStrategy(str, Enum):
    zero_shot = "zero_shot"
    few_shot = "few_shot"
    few_shot_cot = "few_shot_cot"


class InputDocument(BaseModel):
    """One passage (Bangla) and six task-specific questions (Bangla)."""

    id: Optional[str] = None
    context: str = Field(default="", description="Bangla_Context passage")
    questions: dict[str, str] = Field(
        default_factory=dict,
        description="Keys: factoid, confirmation, list, casual, temporal, unanswerable",
    )
    gold_answers: Optional[dict[str, Optional[str]]] = Field(
        default=None,
        description="Optional gold strings per task (for evaluation)",
    )

    @model_validator(mode="after")
    def _normalize_questions(self) -> InputDocument:
        self.questions = ensure_question_keys(self.questions)
        return self


class InputItem(BaseModel):
    """Legacy single-QA row (deprecated; kept for imports)."""

    id: Optional[str] = None
    context: str = ""
    question: str = ""
    question_type: Optional[str] = None
    gold_answer: Optional[str] = None

    model_config = {"extra": "ignore"}


class InputMeta(BaseModel):
    source_file: Optional[str] = None
    prompt_strategy: PromptStrategy = PromptStrategy.zero_shot
    model: Optional[str] = Field(default=None, description="Override generation model")


class InputBatch(BaseModel):
    """Generation input: list of documents (each = 6 tasks in one LLM call)."""

    meta: InputMeta = Field(default_factory=InputMeta)
    documents: list[InputDocument] = Field(default_factory=list)


class OutputMeta(BaseModel):
    prompt_strategy: str
    model: str
    input_source: Optional[str] = None
    n_documents: int = 0


class OutputDocument(BaseModel):
    """Predictions for all six tasks for one context."""

    id: Optional[str] = None
    context: Optional[str] = None
    questions: Optional[dict[str, str]] = None
    gold_answers: Optional[dict[str, Optional[str]]] = None
    predictions: dict[str, str] = Field(
        default_factory=dict,
        description="Six task keys → Bangla answer strings",
    )
    predictions_cot: Optional[dict[str, dict[str, str]]] = Field(
        default=None,
        description="few_shot_cot: task → {chain_of_thought, answer}",
    )
    raw_model_output: str = ""
    error: Optional[str] = None


class OutputBatch(BaseModel):
    meta: OutputMeta
    results: list[OutputDocument]


# Back-compat alias
OutputItem = OutputDocument
