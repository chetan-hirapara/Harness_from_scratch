# Customer Support Refund Agent

This project demonstrates an AI harness for a customer support refund workflow. Instead of letting a language model make the final money decision directly, the solution combines:

- an LLM for language understanding
- a deterministic tool pipeline for order lookup, policy checks, and refund calculations
- SQLite persistence for orders, refunds, and conversations
- a DAG-based orchestrator to coordinate tool execution
- trajectory logging for debugging and observability

The result is a safer, more testable refund agent that can handle multi-turn conversations while enforcing business rules.

## Solution overview

The workflow is built around a customer support scenario with real refund logic:

- extract the customer intent and relevant order ID
- look up the order in SQLite
- validate return-window and prior-refund rules
- assess condition and reason for the return
- calculate the refund amount using business rules
- prevent duplicate processing with idempotency keys
- persist the refund result and return a customer-friendly response

The project intentionally separates language-heavy steps from critical money and policy decisions so the system remains auditable and deterministic.

## Repository structure

- `support_agent_tools.py` — tool implementations
- `support_agent_spec.yaml` — declarative tool graph and dependencies
- `support_agent_orchestrator.py` — DAG execution engine
- `support_agent_main.py` — demo scenarios and multi-turn flows
- `setup_db.py` — database initialization and seed data
- `llm_client.py` — OpenAI-compatible LLM wrapper with fallback behavior
- `trajectories/` — execution logs for each scenario
- `docs/` — usage and architecture notes
- `customer_support.db` — SQLite database used by the app

## Prerequisites

- Python 3.10 or newer
- pip
- Optional: local Ollama instance for LLM-backed language understanding

If you want the LLM path enabled, make sure Ollama is running locally and serving an OpenAI-compatible endpoint at:

- `http://localhost:11434/v1`

The default model is `qwen3.8:latest`.

## Setup

1. Open a terminal in the project root.
2. Create and activate a virtual environment:

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Initialize the database:

```bash
python setup_db.py
```

5. Run the demo agent scenarios:

```bash
python support_agent_main.py
```

## Optional LLM configuration

The project supports environment overrides for the LLM client. For example:

```powershell
$env:LLM_ENABLED = "true"
$env:LLM_BASE_URL = "http://localhost:11434/v1"
$env:LLM_API_KEY = "ollama"
$env:LLM_MODEL = "qwen3.8:latest"
```

If the LLM is unavailable or fails, the code falls back to deterministic rule-based logic so the workflow continues.

## Useful commands

View the dependency graph:

```bash
python draw_dag.py
```

Inspect a recorded trajectory in the `trajectories/` folder after running the demo.

## Notes

- The refund calculation logic is intentionally deterministic.
- Duplicate refund requests are blocked by idempotency checks and database uniqueness constraints.
- The system logs execution traces so you can debug tool behavior and policy decisions.

## License

This project is intended for educational and demonstration purposes.
