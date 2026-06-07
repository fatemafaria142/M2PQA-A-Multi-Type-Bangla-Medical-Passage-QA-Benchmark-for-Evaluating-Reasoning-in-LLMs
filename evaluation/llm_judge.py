"""
LLM-as-judge: four QA metrics (1–5 each) — Correctness, Completeness, Relevance, Clarity.

Uses ``prompt/judge_prompt.md``.

Usage::

  1. Set ``LLM_JUDGE_PREDICTIONS_JSON`` below (filename inside ``output/``).
  2. From the **project root** (``Code-Medi``), run::

       python -m evaluation.llm_judge

     Or: ``python evaluation/llm_judge.py`` from the project root — not from inside
     ``evaluation/``, unless you only use absolute paths in ``.env``.

  Writes **one** JSON file:
  ``llm_judge_evaluation_output/medqa_llm_judge_<strategy>_output.json`` (e.g.
  ``medqa_llm_judge_zero_shot_output.json``). The JSON contains no file paths.
  Each document is ``{ "id": …, "task1": …, …, "task6": … }`` — ``task1``…``task6`` match
  MedQA order (factoid → confirmation → list → casual → temporal → unanswerable). Each
  task object includes ``task_type``, ``question``, ``gold_answer``, ``predicted_answer``,
  then the judge scores and ``rationale``.

  Optional::

     python -m evaluation.llm_judge --predictions path/to.json --limit 30

Requires OPENAI_API_KEY and JUDGE_MODEL (see ``.env`` / ``bangla_medqa.config``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from tqdm import tqdm

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bangla_medqa.config import JUDGE_MODEL, PROMPT_DIR
from bangla_medqa.llm_client import chat_complete, parse_json_response
from bangla_medqa.tasks import TASK_KEYS
from evaluation.automated_scoring import iter_medqa_eval_rows

# task1 = factoid, task2 = confirmation, …, task6 = unanswerable
_TASK_SLOT: dict[str, str] = {TASK_KEYS[i]: f"task{i + 1}" for i in range(len(TASK_KEYS))}

# =============================================================================
# User configuration
# =============================================================================
# Predictions JSON **filename** inside the ``output/`` folder (e.g. ``bangla_medqa_zero_shot.json``).
LLM_JUDGE_PREDICTIONS_JSON = "bangla_medqa_zero_shot.json"

# Judge output folder at **project root** (not under ``output/``): ``Code-Medi/llm_judge_evaluation_output/``.
LLM_JUDGE_EVALUATION_OUTPUT = "llm_judge_evaluation_output"

OUTPUT_FOLDER = _ROOT / "output"

JUDGE_METRICS = ("correctness", "completeness", "relevance", "clarity")


def _prompt_dir_resolved() -> Path:
    """
    ``PROMPT_DIR`` in ``.env`` is often relative (e.g. ``prompt``). Resolve it from
    project root so ``python evaluation/llm_judge.py`` works from any cwd.
    """
    p = Path(PROMPT_DIR)
    return p if p.is_absolute() else (_ROOT / p)


def _slug_from_predictions_path(pred_path: Path) -> str:
    stem = pred_path.stem
    prefix = "bangla_medqa_"
    if stem.startswith(prefix):
        return stem[len(prefix) :] or "run"
    return stem or "run"


def default_predictions_path() -> Path:
    return OUTPUT_FOLDER / LLM_JUDGE_PREDICTIONS_JSON


def default_judge_output_dir() -> Path:
    return _ROOT / LLM_JUDGE_EVALUATION_OUTPUT


def _sleep_between_calls() -> float:
    return float(os.getenv("JUDGE_RATE_LIMIT_SECONDS", "0.4"))


def _fill_judge_user(template: str, *, context: str, question: str, gold: str, predicted: str) -> str:
    return (
        template.replace("{{context}}", context.strip())
        .replace("{{question}}", question.strip())
        .replace("{{gold_answer}}", gold.strip())
        .replace("{{predicted_answer}}", predicted.strip())
        .replace("{{CONTEXT}}", context.strip())
        .replace("{{QUESTION}}", question.strip())
        .replace("{{GOLD}}", gold.strip())
        .replace("{{PRED}}", predicted.strip())
    )


def load_judge_prompt() -> tuple[str, str]:
    path = _prompt_dir_resolved() / "judge_prompt.md"
    if not path.is_file():
        raise FileNotFoundError(
            f"Judge prompt not found: {path} (project root={_ROOT}, PROMPT_DIR={PROMPT_DIR!r})"
        )
    text = path.read_text(encoding="utf-8")
    if "---SYSTEM" in text and "---USER" in text:
        parts = text.split("---SYSTEM", 1)[1]
        sys_part, user_part = parts.split("---USER", 1)
        return sys_part.strip(), user_part.strip()
    return (
        "You are a fair evaluator. Output only JSON.",
        text.strip(),
    )


def _clamp_int_1_5(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        i = int(round(float(v)))
        return max(1, min(5, i))
    return None


def parse_judge_scores(obj: dict[str, Any]) -> dict[str, Any]:
    """Normalize four 1–5 scores and rationale from model JSON."""
    scores: dict[str, Optional[int]] = {}
    for k in JUDGE_METRICS:
        raw = obj.get(k)
        if raw is None:
            raw = obj.get(k.capitalize()) or obj.get(k.upper())
        scores[k] = _clamp_int_1_5(raw)
    rationale = obj.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        rationale = str(rationale)
    numeric = [s for s in scores.values() if s is not None]
    mean_score = sum(numeric) / len(numeric) if numeric else None
    return {
        "scores": scores,
        "mean_of_four": mean_score,
        "rationale": rationale,
    }


def judge_one(
    *,
    context: str,
    question: str,
    gold: str,
    predicted: str,
    model: str,
) -> dict[str, Any]:
    system, user_t = load_judge_prompt()
    user = _fill_judge_user(
        user_t,
        context=context or "",
        question=question,
        gold=gold,
        predicted=predicted,
    )
    raw = chat_complete(system=system, user=user, model=model, temperature=0.2, max_tokens=800)
    obj = parse_json_response(raw)
    if not obj:
        return {
            "scores": {k: None for k in JUDGE_METRICS},
            "mean_of_four": None,
            "rationale": None,
            "error": "parse_failed",
            "raw": raw[:800],
        }
    parsed = parse_judge_scores(obj)
    parsed["raw"] = raw
    return parsed


def run_judge_file(
    predictions_path: Path,
    *,
    limit: Optional[int],
    model: str,
    out_dir: Path,
    sleep_s: Optional[float] = None,
) -> dict[str, Any]:
    data: Any = json.loads(predictions_path.read_text(encoding="utf-8"))
    sleep = _sleep_between_calls() if sleep_s is None else sleep_s

    by_id: dict[Any, dict[str, Any]] = {}
    all_means: list[float] = []
    n_done = 0

    out_dir.mkdir(parents=True, exist_ok=True)

    pbar = tqdm(desc="LLM judge", unit="task")
    try:
        for doc_id, ctx, task, q, gold, pred in iter_medqa_eval_rows(data):
            if limit is not None and n_done >= limit:
                break
            jr = judge_one(
                context=str(ctx or ""),
                question=q,
                gold=gold.strip(),
                predicted=pred.strip(),
                model=model,
            )
            slot = _TASK_SLOT[task]
            simple: dict[str, Any] = {
                "task_type": task,
                "question": q,
                "gold_answer": gold,
                "predicted_answer": pred,
                "correctness": jr["scores"]["correctness"],
                "completeness": jr["scores"]["completeness"],
                "relevance": jr["scores"]["relevance"],
                "clarity": jr["scores"]["clarity"],
                "mean_of_four": jr.get("mean_of_four"),
                "rationale": jr.get("rationale"),
            }
            err = jr.get("error")
            if err:
                simple["error"] = err
            by_id.setdefault(doc_id, {})[slot] = simple
            mf = jr.get("mean_of_four")
            if isinstance(mf, (int, float)):
                all_means.append(float(mf))
            n_done += 1
            pbar.update(1)
            time.sleep(sleep)
    finally:
        pbar.close()

    slug = _slug_from_predictions_path(predictions_path)
    mean_m = (sum(all_means) / len(all_means)) if all_means else None
    meta_json: dict[str, Any] = {
        "judge_model": model,
        "run_strategy": slug,
        "n_documents": len(by_id),
        "n_judged_tasks": n_done,
        "mean_score_mean_of_four": mean_m,
        "metrics": list(JUDGE_METRICS),
    }

    documents: list[dict[str, Any]] = []
    for doc_id, slots in sorted(
        by_id.items(),
        key=lambda it: (not isinstance(it[0], (int, float)), it[0] if isinstance(it[0], (int, float)) else str(it[0])),
    ):
        row: dict[str, Any] = {"id": doc_id}
        for i in range(len(TASK_KEYS)):
            sk = f"task{i + 1}"
            row[sk] = slots.get(sk)
        documents.append(row)

    out_path = out_dir / f"medqa_llm_judge_{slug}_output.json"
    payload = {"meta": meta_json, "documents": documents}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "meta": meta_json,
        "output_path": str(out_path),
        "n_documents": len(documents),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM-as-judge (4×1–5 metrics); writes one JSON under <project>/llm_judge_evaluation_output/"
    )
    parser.add_argument(
        "--predictions",
        type=str,
        default=None,
        help=f"Predictions JSON (default: output/{LLM_JUDGE_PREDICTIONS_JSON})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of (document, task) judgments",
    )
    parser.add_argument("--model", type=str, default=JUDGE_MODEL)
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help=f"Override output directory (default: <project root>/{LLM_JUDGE_EVALUATION_OUTPUT})",
    )
    args = parser.parse_args()

    pred = Path(args.predictions) if args.predictions else default_predictions_path()
    if not pred.is_file():
        raise SystemExit(f"Predictions file not found: {pred}")

    out_dir = Path(args.out_dir) if args.out_dir else default_judge_output_dir()

    report = run_judge_file(pred, limit=args.limit, model=args.model, out_dir=out_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
