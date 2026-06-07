"""
Automatic evaluation for Bangla MedQA prediction JSON — **one self-contained script**.

+----------------+------------------+
| Question type  | Metric           |
+================+==================+
| Factoid        | Exact Match      |
| Confirmation   | Accuracy         |
| List           | ROUGE-L          |
| Casual         | BERTScore        |
| Temporal       | Exact Match      |
| Unanswerable   | Accuracy         |
+----------------+------------------+

*Accuracy* = normalized exact-match rate (Bangla-normalized strings).

Prediction files: top-level JSON **array** of MedQA rows, or legacy ``{"records": [...]}`` / ``{"results": [...]}``.

Usage::

  1. Set ``MEDQA_PREDICTIONS_JSON`` below (file name inside ``output/``).
  2. Run::

       python -m evaluation.automated_scoring

  The report is written to
  ``output/automated_evaluation_output/medqa_automated_<strategy>_output.json``,
  where ``<strategy>`` is taken from the predictions file, e.g.
  ``bangla_medqa_zero_shot.json`` → ``medqa_automated_zero_shot_output.json``.

  Optional CLI overrides::

     python -m evaluation.automated_scoring --predictions path/to.json --report path/to/report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Iterator, Union

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# =============================================================================
# User configuration
# =============================================================================
# Name of the predictions JSON **inside** the ``output/`` folder (same level as
# ``bangla_medqa_zero_shot.json``). Change this to match the run you want scored.
MEDQA_PREDICTIONS_JSON = "bangla_medqa_zero_shot.json"

# Directory (under ``output/``) where automated evaluation JSON is stored.
AUTOMATED_EVALUATION_OUTPUT = "automated_evaluation_output"

# Predictions live here:
OUTPUT_FOLDER = _ROOT / "output"

from tqdm import tqdm

from bangla_medqa.tasks import (
    GENERATED_RESPONSE_KEYS,
    TASK_KEYS,
    TASK_QUESTION_FIELDS,
)

TASK_METRIC: dict[str, str] = {
    "factoid": "Exact Match",
    "confirmation": "Accuracy",
    "list": "ROUGE-L",
    "casual": "BERTScore",
    "temporal": "Exact Match",
    "unanswerable": "Accuracy",
}

_WS = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    if not s:
        return ""
    t = unicodedata.normalize("NFKC", s)
    return _WS.sub(" ", t).strip().lower()


def exact_match(pred: str, gold: str) -> bool:
    return normalize_text(pred) == normalize_text(gold)


_rl_scorer: Any = None


def _rl() -> Any:
    global _rl_scorer
    if _rl_scorer is None:
        try:
            from rouge_score import rouge_scorer as _rs
        except ImportError as e:
            raise ImportError("Install rouge-score: pip install rouge-score") from e
        _rl_scorer = _rs.RougeScorer(["rougeL"], use_stemmer=False)
    return _rl_scorer


def rouge_l_fmeasure(pred: str, gold: str) -> float:
    p_raw, g_raw = pred.strip(), gold.strip()
    if not p_raw and not g_raw:
        return 1.0
    if not p_raw or not g_raw:
        return 0.0
    s = _rl().score(g_raw, p_raw)
    return float(s["rougeL"].fmeasure)


def batch_bertscore_f1(candidates: list[str], references: list[str]) -> list[float]:
    if not candidates:
        return []
    if len(candidates) != len(references):
        raise ValueError("candidates and references length mismatch.")

    try:
        import torch
        from bert_score import score as bert_score_score
    except ImportError as e:
        raise ImportError(
            "BERTScore needs bert-score and torch: pip install bert-score torch"
        ) from e

    device = "cuda" if torch.cuda.is_available() else "cpu"
    c_safe = [(c or "").strip() or "[EMPTY]" for c in candidates]
    r_safe = [(r or "").strip() or "[EMPTY]" for r in references]
    _p, _r, f1 = bert_score_score(
        c_safe,
        r_safe,
        model_type="bert-base-multilingual-cased",
        verbose=False,
        rescale_with_baseline=False,
        device=device,
    )
    return [float(x) for x in f1]


def iter_medqa_eval_rows(
    data: Union[dict[str, Any], list[Any]],
) -> Iterator[tuple[Any, str, str, str, str, str]]:
    """
    Yield ``(doc_id, context, task, question, gold_answer, predicted_answer)``.
    Skips gold-empty pairs.
    """
    if isinstance(data, list):
        yield from _from_medqa_records(data)
        return
    records = data.get("records") if isinstance(data, dict) else None
    if isinstance(records, list) and records:
        yield from _from_medqa_records(records)
        return
    if isinstance(data, dict):
        yield from _from_legacy_results(data.get("results") or [])


def _from_medqa_records(records: list[Any]) -> Iterator[tuple[Any, str, str, str, str, str]]:
    for r in records:
        if not isinstance(r, dict):
            continue
        doc_id = r.get("id")
        ctx = str(r.get("Bangla_Context") or "")
        for task in TASK_KEYS:
            fq, fg = TASK_QUESTION_FIELDS[task]
            q = str(r.get(fq) or "")
            raw_gold = r.get(fg)
            gold = "" if raw_gold is None else str(raw_gold).strip()
            if not gold:
                continue
            gk = GENERATED_RESPONSE_KEYS[task]
            pred = str(r.get(gk) or "").strip()
            yield doc_id, ctx, task, q, gold, pred


def _from_legacy_results(
    results: Iterable[Any],
) -> Iterator[tuple[Any, str, str, str, str, str]]:
    for r in results:
        if not isinstance(r, dict):
            continue
        golds = r.get("gold_answers") or {}
        preds = r.get("predictions") or {}
        qs = r.get("questions") or {}
        ctx = str(r.get("context") or "")
        doc_id = r.get("id")
        for task in TASK_KEYS:
            raw_gold = golds.get(task)
            gold = "" if raw_gold is None else str(raw_gold).strip()
            if not gold:
                continue
            q = str(qs.get(task) or "")
            pred = str(preds.get(task) or "").strip()
            yield doc_id, ctx, task, q, gold, pred


def _scalar_for_task(task: str, pred: str, gold: str) -> float | None:
    p, g = pred.strip(), gold.strip()
    if task == "casual":
        return None
    if task == "list":
        return rouge_l_fmeasure(p, g)
    if task in ("factoid", "temporal", "confirmation", "unanswerable"):
        return 1.0 if exact_match(p, g) else 0.0
    return 1.0 if exact_match(p, g) else 0.0


def evaluate_file(predictions_path: Path) -> dict[str, Any]:
    raw = json.loads(predictions_path.read_text(encoding="utf-8"))
    pairs = list(iter_medqa_eval_rows(raw))

    rows: list[dict[str, Any]] = []
    casual_rows: list[tuple[int, str, str]] = []

    for doc_id, _ctx, task, _q, gold, pred in tqdm(pairs, desc="Automatic metrics", unit="pair"):
        p, g = pred.strip(), gold.strip()
        metric = TASK_METRIC[task]
        sc = _scalar_for_task(task, p, g)
        idx = len(rows)
        rows.append(
            {
                "doc_id": doc_id,
                "task": task,
                "metric": metric,
                "score": round(sc, 4) if isinstance(sc, (int, float)) else None,
            }
        )
        if task == "casual":
            casual_rows.append((idx, p, g))

    if casual_rows:
        f1s = batch_bertscore_f1([t[1] for t in casual_rows], [t[2] for t in casual_rows])
        for (i, _, _), f1 in zip(casual_rows, f1s):
            rows[i]["score"] = round(float(f1), 4)

    by_type: dict[str, dict[str, Any]] = {}
    for t in TASK_KEYS:
        vals = [float(r["score"]) for r in rows if r["task"] == t and r["score"] is not None]
        by_type[t] = {
            "metric": TASK_METRIC[t],
            "score": round(mean(vals), 4) if vals else None,
            "n": len(vals),
        }

    return {
        "summary": {
            "n_evaluable_pairs": len(rows),
            "by_question_type": by_type,
        },
        "per_pair": rows,
        "source_predictions": str(predictions_path),
    }


def _strategy_slug_from_predictions(pred_path: Path) -> str:
    """
    ``bangla_medqa_zero_shot.json`` → ``zero_shot``;
    ``bangla_medqa_few_shot_cot.json`` → ``few_shot_cot``.
    """
    stem = pred_path.stem
    prefix = "bangla_medqa_"
    if stem.startswith(prefix):
        return stem[len(prefix) :] or "run"
    return stem or "run"


def default_predictions_path() -> Path:
    """Configured MedQA predictions file under ``output/``."""
    return OUTPUT_FOLDER / MEDQA_PREDICTIONS_JSON


def default_report_path(pred_path: Path) -> Path:
    """``output/automated_evaluation_output/medqa_automated_<strategy>_output.json``."""
    slug = _strategy_slug_from_predictions(pred_path)
    return OUTPUT_FOLDER / AUTOMATED_EVALUATION_OUTPUT / f"medqa_automated_{slug}_output.json"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Bangla MedQA automatic metrics (per question type). "
        "Defaults use MEDQA_PREDICTIONS_JSON and AUTOMATED_EVALUATION_OUTPUT in this file."
    )
    ap.add_argument(
        "--predictions",
        default=None,
        metavar="PATH",
        help=(
            f"Predictions JSON (default: output/{MEDQA_PREDICTIONS_JSON} "
            "from MEDQA_PREDICTIONS_JSON in automated_scoring.py)"
        ),
    )
    ap.add_argument(
        "--report",
        default=None,
        metavar="PATH",
        help=(
            "Report JSON path (default: "
            f"output/{AUTOMATED_EVALUATION_OUTPUT}/medqa_automated_<strategy>_output.json)"
        ),
    )
    args = ap.parse_args()

    pred = Path(args.predictions) if args.predictions else default_predictions_path()
    if not pred.is_file():
        raise SystemExit(f"Predictions file not found: {pred}")

    report = evaluate_file(pred)
    out = Path(args.report) if args.report else default_report_path(pred)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
