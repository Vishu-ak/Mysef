# AGENTS.md

## Cursor Cloud specific instructions

This is a pure Python library/demo project with no external services or infrastructure.

### Services

| Service | How to run |
|---------|-----------|
| Demo (CLI) | `PYTHONPATH=. python examples/main.py` |
| Tests | `PYTHONPATH=. pytest` (or `PYTHONPATH=. pytest -v` for verbose) |
| Type check | `PYTHONPATH=. pyright coding_showcase/ examples/ tests/` |

### Key caveat

`PYTHONPATH=.` is required for both running the demo and tests because the project has no `setup.py`/`setup.cfg`/installable build system — the package is imported directly from the working directory. Always run commands from the repository root (`/workspace`).
