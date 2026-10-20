# Local Agentic AI — Proton Mail Trash Review

A local-first agentic AI prototype that reviews selected conversations in Proton Mail's Trash and identifies messages that may deserve a second look.

The project explores how to combine a locally hosted language model, browser automation, structured outputs, deterministic business rules, and automated tests in a practical application.

> **Status:** Experimental portfolio project. The live workflow currently runs from a Jupyter notebook and depends on Proton Mail's web interface.

## The problem

Trash folders can contain routine notifications alongside messages that are unusual in context or contain a future meeting, event, or deadline. This prototype uses an LLM to interpret message meaning and Python rules to decide which findings are supported by the available evidence.

It is designed to assist a user with review, not to make decisions on their behalf.

## Features

- **Local language model:** Ollama with `qwen3:4b-instruct`, connected through PydanticAI's OpenAI-compatible model interface.
- **Browser automation:** Playwright navigates Proton Mail and inspects Trash conversations.
- **Structured output:** Pydantic models represent candidate selections, message purposes, evidence, and review findings.
- **Validated candidate selection:** Python rejects invalid, duplicate, or out-of-scope conversation indexes.
- **Context-aware review:** A message's purpose is compared with the purposes identified in surrounding Trash conversations.
- **Explicit date validation:** A future-event finding requires a supported, specific date strictly later than the analysis date.
- **Evidence validation:** Findings are rejected when evidence is empty or unsupported by the inspected message.
- **Automated tests:** Unit tests cover selection, review decisions, date and evidence validation, execution budgets, and guarded browser actions.

The workflow currently limits the number of conversations inspected per run to five.

## How the review works

1. **Collect Trash context.** Playwright gathers information about recent Trash conversations.
2. **Select candidates.** The model proposes conversation indexes. Python validates them against the allowed selection.
3. **Inspect conversations.** The workflow opens selected messages, collects their content and surrounding context, then returns to Trash.
4. **Assess purpose.** The model returns structured classifications and evidence for each inspected message and its context.
5. **Apply deterministic rules.** Python checks context completeness, majority purpose, explicit dates, and evidence support.
6. **Validate the report.** Unsupported evidence, invalid dates, and findings that fail the rules are rejected.

Findings are classified as `unusual`, `future_event`, or `both`.

### Why combine an LLM with deterministic Python rules?

An LLM can interpret message meaning, but it can also misclassify messages, return inconsistent dates, or provide unsupported evidence.

The model therefore proposes structured assessments. Python applies explicit rules for candidate indexes, context completeness, majority decisions, date parsing, and evidence validation. This makes those parts of the workflow predictable and testable even when model output varies.

## Technology

- Python 3.13+
- Ollama
- Qwen 3 4B Instruct (`qwen3:4b-instruct`)
- Pydantic and PydanticAI
- Playwright
- pytest and pytest-asyncio
- Jupyter notebooks

Dependencies are defined in `agentic-ai/pyproject.toml`.

## Requirements

- Python 3.13 or newer
- [Ollama](https://ollama.com/) installed locally
- Chromium installed through Playwright
- A Proton Mail account for the live browser workflow
- VS Code with Python and Jupyter support, or a compatible Jupyter environment

The model is configured to use the local Ollama endpoint at `http://localhost:11434/v1`. The configured inference workflow does not require a paid LLM API.

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/TheoSoft-0/agentic_AI_project.git
cd agentic_AI_project
```

### 2. Create and activate a Conda environment

```bash
conda create -n agentic-ai python=3.13
conda activate agentic-ai
```

### 3. Install the project

Run these commands from the `agentic-ai` directory:

```bash
cd agentic-ai
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

### 4. Download the local model

Ensure Ollama is installed and running, then execute:

```bash
ollama pull qwen3:4b-instruct
ollama list
```

Confirm the model appears in the list and that Ollama is available locally on port `11434`.

## Run the live Trash review

The complete workflow currently has no standalone command-line entry point. It is launched from `agentic-ai/09_trash_review.ipynb`.

1. Open the repository in VS Code.
2. Open `agentic-ai/09_trash_review.ipynb`.
3. Select the `agentic-ai` Conda environment as the notebook kernel.
4. Execute the notebook's setup cells in order.
5. Sign in to Proton Mail manually in the browser if prompted.
6. Run the review and check the findings against the original messages.

The browser session is stored in a local profile to support persistent authentication. Do not commit browser profiles, credentials, or saved notebook outputs.

The review workflow is intended to inspect and report findings rather than modify email. Write-capable functionality uses a default-disabled `allow_writes` guard. Do not enable write operations without reviewing their implementation and consequences.

## Run the tests

From the `agentic-ai` directory:

```bash
python -m pytest -v
```

Check Python syntax with:

```bash
python -m compileall -q src/agentic_ai scripts tests
```

The suite covers candidate validation, inspection and tool-call budgets, evidence validation, explicit date parsing, deterministic review decisions, and guarded browser actions.

Some validation tests intentionally generate runtime warnings to confirm that unsupported findings are discarded.

## Project structure

```text
agentic_AI_project/
├── README.md
├── .gitignore
└── agentic-ai/
    ├── pyproject.toml
    ├── 01_first_agent.ipynb
    ├── ...
    ├── 09_trash_review.ipynb
    ├── src/agentic_ai/
    │   ├── agent.py
    │   ├── browser.py
    │   ├── candidate_selection.py
    │   ├── models.py
    │   ├── proton.py
    │   ├── review_decision.py
    │   ├── review_validation.py
    │   └── workflow.py
    ├── scripts/
    │   └── evaluate_trash_review.py
    ├── sample_repository/
    └── tests/
```

### Main modules

| Module                   | Responsibility                                                           |
| ------------------------ | ------------------------------------------------------------------------ |
| `agent.py`               | Configures the local model, agents, dependencies, and execution budgets. |
| `browser.py`             | Starts and manages the Playwright browser context.                       |
| `proton.py`              | Implements Proton Mail navigation, inspection, and guarded mail actions. |
| `candidate_selection.py` | Validates candidate indexes returned by the model.                       |
| `models.py`              | Defines structured data models used throughout the workflow.             |
| `review_decision.py`     | Converts assessments into findings using deterministic rules.            |
| `review_validation.py`   | Validates evidence and explicit event dates.                             |
| `workflow.py`            | Orchestrates the Trash review.                                           |

## Privacy and safety

- Email content provided to the model is sent to the configured local Ollama endpoint for inference.
- Browser authentication is stored in a local browser profile. Never commit session files, credentials, or environment files.
- Notebook outputs can contain real subjects, message excerpts, and review results. Clear outputs before committing notebook changes.
- Findings should be checked against the original email before taking action.
- The project does not claim that LLM classifications are always correct or that local processing alone guarantees security.

## Limitations and future improvements

- Browser automation depends on Proton Mail's web interface and may need maintenance when that interface changes.
- The local model can misclassify purposes or event dates.
- Date detection is deliberately conservative and depends on supported, explicit dates rather than vague date references.
- Only a limited number of conversations are inspected per run.
- The complete workflow currently runs from a notebook rather than a packaged command-line interface.
- This is an experimental learning project, not a production email service.

Potential next steps include a documented command-line entry point, more edge-case tests, clearer report presentation, and broader evaluation with synthetic scenarios.

## Learning goals

This project explores:

- Tool-using agents and browser automation.
- Structured LLM output and Pydantic models.
- Deterministic validation around probabilistic model results.
- Safe handling of side-effecting tools.
- Testable application architecture and error handling.
- Local model deployment and reproducible development workflows.
