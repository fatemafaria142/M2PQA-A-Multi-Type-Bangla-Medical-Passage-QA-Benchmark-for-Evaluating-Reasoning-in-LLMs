# M2PQA: A Multi-Type Bangla Medical Passage QA Benchmark for Evaluating Reasoning in LLMs

This repository contains the **M2PQA** benchmark and the full experimental pipeline used to **generate model answers** and **evaluate LLM performance** on Bangla medical reading-comprehension questions.

Each benchmark item is a single Bangla medical passage paired with **six different question types** (factoid, confirmation, list, casual, temporal, and unanswerable). The pipeline sends one LLM call per passage and expects structured answers for all six tasks at once, then scores predictions with both **automatic metrics** and an **LLM-as-judge**.

---

## Table of Contents

1. [What This Project Does](#what-this-project-does)
2. [The Six Question Types](#the-six-question-types)
3. [Repository Structure](#repository-structure)
4. [Setup](#setup)
5. [Configuration (`.env`)](#configuration-env)
6. [Step 1 — Generate Model Answers](#step-1--generate-model-answers)
7. [Prompt Strategies](#prompt-strategies)
8. [Output Format](#output-format)
9. [Step 2 — Automated Evaluation](#step-2--automated-evaluation)
10. [Step 3 — LLM-as-Judge Evaluation](#step-3--llm-as-judge-evaluation)
11. [End-to-End Workflow for Collaborators](#end-to-end-workflow-for-collaborators)
12. [Design Notes](#design-notes)
13. [License](#license)

---

## What This Project Does

The project has three main stages:

| Stage | Script | Purpose |
|-------|--------|---------|
| **Generation** | `run_bangla_medqa.py` | Load Bangla passages from `dataset/MedQA.json`, prompt an LLM with one of three strategies, and write prediction JSON to `output/`. |
| **Automated scoring** | `python -m evaluation.automated_scoring` | Compare predictions to gold answers using task-specific metrics (Exact Match, Accuracy, ROUGE-L, BERTScore). |
| **LLM judge** | `python -m evaluation.llm_judge` | Score each answer on Correctness, Completeness, Relevance, and Clarity (1–5) using `prompt/judge_prompt.md`. |

**Key design choice:** For each document, the model receives **one shared Bangla context** and **six questions** in a single API call. This mirrors real multi-task reading comprehension and reduces cost compared to six separate calls per passage.

The benchmark currently contains **20 Bangla medical passages** in `dataset/MedQA.json`. Each row includes gold questions and answers for all six tasks.

---

## The Six Question Types

Every document in the dataset follows the same structure: one `Bangla_Context` passage and six task-specific Q/A pairs.

| Task | What it tests | Example question style |
|------|---------------|------------------------|
| **Factoid** | Extract a single fact from the passage | "ব্যাকটেরিয়া সংক্রমণের চিকিৎসা কি দিয়ে করা হয়?" |
| **Confirmation** | Verify whether a statement matches the text (yes/no) | "…এটি কি সঠিক?" |
| **List** | Enumerate all relevant items mentioned | "…লক্ষণগুলি কি কি?" |
| **Casual** | Definitional or explanatory answer | "…কি?" / "কাকে …?" |
| **Temporal** | Time-related facts from the passage | "…কত সালে …?" |
| **Unanswerable** | Questions whose answer is **not** in the passage | Model should indicate the answer is not available |

Gold answers for unanswerable items are typically `"উত্তর নাই"` (no answer).

---

## Repository Structure

```
.
├── bangla_medqa/              # Core generation package
│   ├── config.py              # Paths, .env loading, model defaults
│   ├── dataset_adapter.py     # MedQA.json → internal document format
│   ├── pipeline.py            # Main batch generation loop
│   ├── llm_client.py          # OpenAI API calls, JSON parsing, retries
│   ├── prompt_loader.py       # Loads markdown prompts from prompt/
│   ├── tasks.py               # Six task keys and field name mappings
│   ├── schemas.py             # Pydantic models for input/output JSON
│   └── io_utils.py            # Read/write JSON batches
├── dataset/
│   └── MedQA.json             # Benchmark data (20 documents)
├── prompt/
│   ├── zero_shot.md           # Zero-shot generation prompt
│   ├── few_shot.md            # Few-shot generation prompt
│   ├── few_shot_cot.md        # Few-shot + chain-of-thought prompt
│   └── judge_prompt.md        # LLM judge scoring prompt
├── evaluation/
│   ├── automated_scoring.py   # Exact Match, ROUGE-L, BERTScore, etc.
│   └── llm_judge.py           # Four-metric LLM judge (1–5 scores)
├── llm/
│   └── llm_config.py          # Legacy/shared LLM config (optional reference)
├── output/                    # Generated predictions (created at runtime, gitignored)
├── llm_judge_evaluation_output/  # Judge reports (gitignored)
├── run_bangla_medqa.py        # Main entry point for generation
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/fatemafaria142/M2PQA-A-Multi-Type-Bangla-Medical-Passage-QA-Benchmark-for-Evaluating-Reasoning-in-LLMs.git
cd M2PQA-A-Multi-Type-Bangla-Medical-Passage-QA-Benchmark-for-Evaluating-Reasoning-in-LLMs
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `bert-score` and `torch` are used for the Casual task metric. First run of automated scoring may download model weights.

### 4. Create your `.env` file

Copy the template below into a new file named `.env` in the project root (this file is **not** committed to Git):

```env
OPENAI_API_KEY=your_openai_api_key_here

GENERATION_MODEL=gpt-4o-mini
JUDGE_MODEL=gpt-4o-mini

TEMPERATURE=0.6
MAX_TOKENS=1000
MULTITASK_MAX_TOKENS=4096
TOP_P=0.9

DATASET_DIR=dataset
PROMPT_DIR=prompt
OUTPUT_DIR=output
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI API key |
| `GENERATION_MODEL` | `gpt-4o-mini` | Model used for answer generation |
| `JUDGE_MODEL` | `gpt-4o-mini` | Model used for LLM-as-judge evaluation |
| `TEMPERATURE` | `0.6` | Sampling temperature |
| `MAX_TOKENS` | `1000` | Base max tokens per completion |
| `MULTITASK_MAX_TOKENS` | `4096` | Max tokens for the six-task generation call |
| `TOP_P` | `0.9` | Nucleus sampling |
| `GEN_RATE_LIMIT_SECONDS` | `0.5` | Delay between generation API calls |
| `MAX_API_RETRIES` | `5` | Retries on API failure |

You can also edit defaults at the top of `run_bangla_medqa.py` (dataset path, default strategy, default sample size).

---

## Step 1 — Generate Model Answers

### Quick start (first 5 documents, default strategy)

```bash
python run_bangla_medqa.py
```

By default this uses:
- Dataset: `dataset/MedQA.json`
- Strategy: `few_shot_cot`
- Documents: first **5** (configurable via `DEFAULT_NUM_DOCUMENTS_WHEN_UNSPECIFIED` in `run_bangla_medqa.py`)

### Common commands

```bash
# Process all 20 documents with zero-shot prompting
python run_bangla_medqa.py --full --strategy zero_shot

# Process first 10 documents with few-shot prompting
python run_bangla_medqa.py --samples 10 --strategy few_shot

# Process all documents with chain-of-thought few-shot
python run_bangla_medqa.py --full --strategy few_shot_cot

# Override the model for one run
python run_bangla_medqa.py --samples 5 --strategy zero_shot --model gpt-4o

# Custom output path
python run_bangla_medqa.py --full --strategy few_shot --output output/my_run.json
```

Alternative module entry point:

```bash
python -m bangla_medqa generate --samples 5 --strategy zero_shot
```

### What happens during generation

1. Each row in `MedQA.json` is converted to one **document** (shared context + six questions + gold answers).
2. The chosen prompt file (`prompt/zero_shot.md`, `few_shot.md`, or `few_shot_cot.md`) is loaded.
3. For each document, **one OpenAI chat completion** is sent with the Bangla context and all six questions.
4. The model response is parsed as JSON and mapped to `Generated_*_Response` (and optionally `Generated_*_Chain_of_Thought`) fields.
5. Results are saved to `output/bangla_medqa_<strategy>.json`.

---

## Prompt Strategies

| Strategy | Prompt file | Chain-of-thought |
|----------|-------------|------------------|
| `zero_shot` | `prompt/zero_shot.md` | No |
| `few_shot` | `prompt/few_shot.md` | No |
| `few_shot_cot` | `prompt/few_shot_cot.md` | Yes — model returns reasoning + answer per task |

Prompts are plain Markdown with `---SYSTEM` and `---USER` sections. Few-shot examples are embedded **inside the prompt files**, not pulled from the dataset at runtime.

---

## Output Format

Generation writes a JSON **array** of MedQA-shaped objects. Each object contains:

| Field group | Examples |
|-------------|----------|
| Identifiers | `id`, `Bangla_Context` |
| Gold Q/A | `Factoid_Question`, `Factoid_Answer`, … (all six tasks) |
| Model output | `Generated_Factoid_Response`, `Generated_Confirmation_Response`, … |
| CoT (if used) | `Generated_Factoid_Chain_of_Thought`, … |

Example output filenames:
- `output/bangla_medqa_zero_shot.json`
- `output/bangla_medqa_few_shot.json`
- `output/bangla_medqa_few_shot_cot.json`

---

## Step 2 — Automated Evaluation

Automated scoring compares **gold answers** vs **generated responses** using a **different metric per task**:

| Task | Metric |
|------|--------|
| Factoid | Exact Match |
| Confirmation | Accuracy (normalized exact match) |
| List | ROUGE-L |
| Casual | BERTScore |
| Temporal | Exact Match |
| Unanswerable | Accuracy |

### Run

1. Open `evaluation/automated_scoring.py` and set:

   ```python
   MEDQA_PREDICTIONS_JSON = "bangla_medqa_zero_shot.json"
   ```

2. Run from the project root:

   ```bash
   python -m evaluation.automated_scoring
   ```

3. Report is written to:

   ```
   output/automated_evaluation_output/medqa_automated_<strategy>_output.json
   ```

CLI overrides:

```bash
python -m evaluation.automated_scoring \
  --predictions output/bangla_medqa_few_shot.json \
  --report output/automated_evaluation_output/my_report.json
```

---

## Step 3 — LLM-as-Judge Evaluation

The judge scores each predicted answer on four dimensions (1–5):

- **Correctness**
- **Completeness**
- **Relevance**
- **Clarity**

It uses `prompt/judge_prompt.md` and the model specified by `JUDGE_MODEL` in `.env`.

### Run

1. Open `evaluation/llm_judge.py` and set:

   ```python
   LLM_JUDGE_PREDICTIONS_JSON = "bangla_medqa_zero_shot.json"
   ```

2. Run from the project root:

   ```bash
   python -m evaluation.llm_judge
   ```

3. Output is written to:

   ```
   llm_judge_evaluation_output/medqa_llm_judge_<strategy>_output.json
   ```

Each document in the judge output contains `task1` … `task6` (matching factoid → unanswerable order), with question, gold answer, predicted answer, scores, and rationale.

Optional limit for a quick test:

```bash
python -m evaluation.llm_judge --limit 5
```

---

## End-to-End Workflow for Collaborators

Follow this order when reproducing or extending experiments:

```
1. Clone repo → create venv → pip install -r requirements.txt
2. Add .env with OPENAI_API_KEY
3. Generate predictions:
      python run_bangla_medqa.py --full --strategy zero_shot
      python run_bangla_medqa.py --full --strategy few_shot
      python run_bangla_medqa.py --full --strategy few_shot_cot
4. Run automated scoring for each output file (edit MEDQA_PREDICTIONS_JSON)
5. Run LLM judge for each output file (edit LLM_JUDGE_PREDICTIONS_JSON)
6. Compare metrics across strategies / models
```

**Suggested comparison table for a paper or report:**

| Strategy | Automated metrics (per task) | Judge scores (avg 1–5) |
|----------|---------------------------|-------------------------|
| zero_shot | from `medqa_automated_zero_shot_output.json` | from `medqa_llm_judge_zero_shot_output.json` |
| few_shot | … | … |
| few_shot_cot | … | … |

---

## Design Notes

- **One call, six tasks:** Each document uses a single multitask prompt so the model sees all questions in context together.
- **Bangla-first:** Context, questions, and expected answers are in Bangla; prompts instruct the model to ground answers in the passage only.
- **Unanswerable handling:** Questions are deliberately written so the passage does not contain the answer; models should respond accordingly (e.g. `"উত্তর নাই"`).
- **Prompts are version-controlled:** Edit files under `prompt/` to iterate on instructions; no database or external prompt store is required.
- **Errors are captured per document:** If one API call fails, the pipeline records an `error` field for that row and continues with the rest.

---

## License

This project is released under the [MIT License](LICENSE).

---

## Contact

**Repository:** [github.com/fatemafaria142/M2PQA-A-Multi-Type-Bangla-Medical-Passage-QA-Benchmark-for-Evaluating-Reasoning-in-LLMs](https://github.com/fatemafaria142/M2PQA-A-Multi-Type-Bangla-Medical-Passage-QA-Benchmark-for-Evaluating-Reasoning-in-LLMs)

For questions about the benchmark or pipeline, contact the repository maintainer.
