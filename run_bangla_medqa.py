"""
Bangla MedQA — single script to run the pipeline.

What this script does
---------------------
1. Loads **documents** from ``dataset/MedQA.json`` (or a custom JSON with a ``documents`` array).
2. Chooses **which prompt** to use: ``prompt/zero_shot.md``, ``few_shot.md``, or ``few_shot_cot.md``.
3. For **each document**, makes **one** LLM call that must return answers for **all six** tasks
   (factoid, confirmation, list, casual, temporal, unanswerable) for the same Bangla context.
4. Writes one JSON **array** of MedQA-shaped objects (see ``examples/sample_output.json``): each row has
   ``id``, ``Bangla_Context``, six Q/A pairs, ``Generated_*_Chain_of_Thought`` (often empty for zero/few-shot),
   and ``Generated_*_Response``. Default filename is ``output/bangla_medqa_<strategy>.json`` (e.g. …_zero_shot.json).

Run examples
------------
  python run_bangla_medqa.py
        → same as ``generate`` (uses CONFIG defaults below).

  python run_bangla_medqa.py generate --strategy few_shot --samples 20
  python run_bangla_medqa.py --full --strategy few_shot_cot
        → ``generate`` is optional; flags may come first.

``python -m bangla_medqa`` also works (see ``bangla_medqa/__main__.py``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Make project root importable
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bangla_medqa.config import OUTPUT_DIR, PROJECT_ROOT
from bangla_medqa.dataset_adapter import (
    documents_from_indices,
    eval_document_indices,
    load_medqa_rows,
)
from bangla_medqa.io_utils import read_input_json, write_output_json
from bangla_medqa.pipeline import run_batch
from bangla_medqa.schemas import InputBatch, InputMeta, PromptStrategy

# =============================================================================
# Configuration — change these defaults for your usual setup.
# Anything you pass on the command line overrides the matching value here.
# =============================================================================

# MedQA JSON: array of documents (each expands into several QA items in code).
DEFAULT_DATASET = PROJECT_ROOT / "dataset" / "MedQA.json"

# Default file pattern when ``--output`` is omitted: ``output/bangla_medqa_<strategy>.json``
def default_output_path_for_strategy(strategy: str) -> Path:
    return OUTPUT_DIR / f"bangla_medqa_{strategy}.json"

# Which prompt markdown to use: zero_shot | few_shot | few_shot_cot
DEFAULT_STRATEGY = "few_shot_cot"

# Optional OpenAI model override (otherwise uses GENERATION_MODEL from .env / config).
DEFAULT_MODEL: str | None = None

# When you run ``generate`` without ``--full`` and without ``--samples``, how many
# **first** documents from the dataset to process. Set to ``None`` if you want to
# **require** an explicit ``--full`` or ``--samples N`` every time.
DEFAULT_NUM_DOCUMENTS_WHEN_UNSPECIFIED = 5

# =============================================================================


def main() -> None:
    args = _parse_args()
    if args.command != "generate":
        raise SystemExit("Only the 'generate' command is supported.")

    strategy = PromptStrategy(args.strategy)
    out_path = Path(args.output) if args.output else default_output_path_for_strategy(args.strategy)

    # Branch A: custom JSON list of items (--input).
    if args.input_path:
        _run_from_input_json(
            input_path=Path(args.input_path),
            strategy=strategy,
            model=_pick_model(args),
            output_path=out_path,
        )
        return

    # Branch B: MedQA file on disk (--dataset / --medqa).
    dataset_path = Path(args.medqa or args.dataset)
    if not dataset_path.is_file():
        raise SystemExit(f"Dataset not found: {dataset_path}")

    run_full_file, num_docs = _resolve_run_scope(
        full_flag=args.full,
        samples_flag=args.samples,
        fallback_num_documents=DEFAULT_NUM_DOCUMENTS_WHEN_UNSPECIFIED,
    )

    rows = load_medqa_rows(dataset_path)
    doc_indices = eval_document_indices(
        len(rows),
        full=run_full_file,
        num_eval_documents=num_docs,
    )
    if not doc_indices:
        raise SystemExit("Nothing to run: check dataset size and --full / --samples.")

    documents = documents_from_indices(rows, doc_indices)
    batch = InputBatch(
        meta=InputMeta(
            source_file=str(dataset_path.resolve()),
            prompt_strategy=strategy,
            model=_pick_model(args),
        ),
        documents=documents,
    )
    out = run_batch(batch)
    _save_and_print(out, out_path)


def _argv_with_default_generate(argv: list[str]) -> list[str]:
    """
    Allow ``python run_bangla_medqa.py`` with no subcommand: treat as ``generate``.

    Also allow ``python run_bangla_medqa.py --samples 5`` (flags before implicit generate).
    """
    if not argv:
        return ["generate"]
    first = argv[0]
    if first in ("-h", "--help"):
        return argv
    if first == "generate":
        return argv
    if first.startswith("-"):
        return ["generate", *argv]
    return argv


def _parse_args() -> Any:
    p = argparse.ArgumentParser(
        prog="run_bangla_medqa.py",
        description=(
            "Bangla MedQA runner. Prompts (and any few-shot examples) come only from "
            "the markdown files in prompt/ — not from the database."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Typical usage:
  %(prog)s
        → generate using defaults in the CONFIG section at the top of this file.

  %(prog)s --samples 10 --strategy few_shot
        → same as ``generate``; subcommand optional when first token is a flag.

  %(prog)s generate --full --strategy zero_shot
        → entire MedQA.json, zero-shot prompt
""",
    )
    sub = p.add_subparsers(dest="command", required=True)
    g = sub.add_parser("generate", help="Run the pipeline and write output JSON.")

    g.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET),
        metavar="PATH",
        help=f"Path to MedQA JSON (default: {DEFAULT_DATASET})",
    )
    g.add_argument(
        "--medqa",
        default=None,
        metavar="PATH",
        help="Alias for --dataset (wins over --dataset when both are given).",
    )

    scope = g.add_mutually_exclusive_group()
    scope.add_argument(
        "--full",
        action="store_true",
        help="Process every top-level document in the dataset.",
    )
    scope.add_argument(
        "--samples",
        type=int,
        default=None,
        metavar="N",
        help="Process only the first N top-level documents.",
    )

    g.add_argument(
        "--strategy",
        type=str,
        choices=[s.value for s in PromptStrategy],
        default=DEFAULT_STRATEGY,
        metavar="NAME",
        help=(
            "Prompt file to load: zero_shot → prompt/zero_shot.md, "
            "few_shot → few_shot.md, few_shot_cot → few_shot_cot.md "
            f"(default: {DEFAULT_STRATEGY})"
        ),
    )
    g.add_argument(
        "--input",
        dest="input_path",
        default=None,
        metavar="PATH",
        help="If set, load QA items from this JSON instead of building them from --dataset.",
    )
    g.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=(
            "Output JSON path (default: output/bangla_medqa_<strategy>.json, "
            "e.g. bangla_medqa_zero_shot.json, bangla_medqa_few_shot_cot.json)."
        ),
    )
    g.add_argument(
        "--model",
        default=None,
        metavar="NAME",
        help="Override LLM model for this run (default: CONFIG / .env).",
    )

    return p.parse_args(_argv_with_default_generate(sys.argv[1:]))


def _pick_model(args: Any) -> str | None:
    if args.model is not None:
        return args.model
    return DEFAULT_MODEL


def _resolve_run_scope(
    *,
    full_flag: bool,
    samples_flag: int | None,
    fallback_num_documents: int | None,
) -> tuple[bool, int | None]:
    """
    Returns (run_everything, first_n_documents).

    - ``--full`` → entire file.
    - ``--samples N`` → first N documents.
    - neither → use ``DEFAULT_NUM_DOCUMENTS_WHEN_UNSPECIFIED`` if set, else error.
    """
    if full_flag:
        return True, None
    if samples_flag is not None:
        if samples_flag <= 0:
            raise SystemExit("--samples must be a positive integer.")
        return False, samples_flag

    if fallback_num_documents is not None and fallback_num_documents > 0:
        return False, fallback_num_documents

    raise SystemExit(
        "Specify how much data to run: use --full, or --samples N, or set "
        "DEFAULT_NUM_DOCUMENTS_WHEN_UNSPECIFIED in this file to a positive integer "
        "(so `generate` with no scope flags still runs a bounded batch).",
    )


def _run_from_input_json(
    *,
    input_path: Path,
    strategy: PromptStrategy,
    model: str | None,
    output_path: Path,
) -> None:
    batch = read_input_json(input_path)
    batch.meta.prompt_strategy = strategy
    if model is not None:
        batch.meta.model = model
    out = run_batch(batch)
    _save_and_print(out, output_path)


def _save_and_print(out: Any, out_path: Path) -> None:
    write_output_json(out_path, out)
    print(f"Wrote {out.meta.n_documents} documents to {out_path}")
    print(f"  strategy={out.meta.prompt_strategy}, model={out.meta.model}, source={out.meta.input_source}")


if __name__ == "__main__":
    main()
