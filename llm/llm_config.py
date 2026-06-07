import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Model Selection
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "gpt-4o-mini")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-4")

# Generation Settings
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.6"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1000"))
TOP_P = float(os.getenv("TOP_P", "0.9"))

# Dataset test mode toggle (choose one by comment/uncomment)
PROCESS_LIMIT = 5        # Use first 5 examples for testing
# PROCESS_LIMIT = None   # Use full dataset

# Reliability settings for long runs
RESUME_PROGRESS = True
GENERATION_OUTPUT_FILE = "responses_progress.csv"
JUDGE_OUTPUT_FILE = "evaluation_progress.csv"

# API rate limit + retry settings
GEN_RATE_LIMIT_SECONDS = float(os.getenv("GEN_RATE_LIMIT_SECONDS", "1.2"))
JUDGE_RATE_LIMIT_SECONDS = float(os.getenv("JUDGE_RATE_LIMIT_SECONDS", "1.2"))
MAX_API_RETRIES = int(os.getenv("MAX_API_RETRIES", "5"))
RETRY_BACKOFF_SECONDS = float(os.getenv("RETRY_BACKOFF_SECONDS", "3.0"))

# Directory Structure
DATASET_DIR = os.getenv("DATASET_DIR", "dataset")
PROMPT_DIR = os.getenv("PROMPT_DIR", "prompt")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
EVALUATION_DIR = os.getenv("EVALUATION_DIR", "evaluation")

# Pricing (per 1,000,000 tokens)
LLM_PRICING = {
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60
    },
    "gpt-4": {
        "input": 30.00,  # Estimated for GPT-4 (8k)
        "output": 60.00
    },
    "gpt-4o": {
        "input": 5.00,
        "output": 15.00
    }
}

# Ensure directories exist
for directory in [DATASET_DIR, PROMPT_DIR, OUTPUT_DIR, EVALUATION_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)


