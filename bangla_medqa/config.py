"""Paths and defaults for Bangla MedQA (project root = Code-Medi)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "gpt-4o-mini")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.6"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1000"))
# One LLM call returns six task answers (and optional CoT); needs a larger completion budget.
MULTITASK_MAX_TOKENS = int(os.getenv("MULTITASK_MAX_TOKENS", "4096"))
TOP_P = float(os.getenv("TOP_P", "0.9"))

DATASET_DIR = Path(os.getenv("DATASET_DIR", PROJECT_ROOT / "dataset"))
PROMPT_DIR = Path(os.getenv("PROMPT_DIR", PROJECT_ROOT / "prompt"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", PROJECT_ROOT / "output"))
EVALUATION_DIR = PROJECT_ROOT / "evaluation"

GEN_RATE_LIMIT_SECONDS = float(os.getenv("GEN_RATE_LIMIT_SECONDS", "0.5"))
MAX_API_RETRIES = int(os.getenv("MAX_API_RETRIES", "5"))
RETRY_BACKOFF_SECONDS = float(os.getenv("RETRY_BACKOFF_SECONDS", "3.0"))

for d in (OUTPUT_DIR, PROMPT_DIR, DATASET_DIR, EVALUATION_DIR):
    d.mkdir(parents=True, exist_ok=True)
