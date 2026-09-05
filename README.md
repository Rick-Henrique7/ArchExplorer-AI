# ArchExplorer AI

> Desktop tool for analyzing, visualizing, and generating software
> architecture components — powered by a local LLM.

## Status

**Pre-alpha.** Active development.

- [x] Project skeleton (PySide6 + 3-panel layout) — [Change 001](./changes/001-pyside6-skeleton/)
- [ ] FileManager (planned)
- [ ] AIEngine + Ollama provider (planned)
- [ ] DiagramGenerator (planned)

## Quickstart

Requires **Python 3.10+** (3.13 tested) on Windows.

> **Important on Windows:** the `py` launcher is registered globally and
> ignores the active virtual environment. After activating the venv, use
> **`python`** (not `py`) to run the app. The `run.ps1` script wraps
> the activation so you don't have to remember.

### One-shot (recommended)

```powershell
.\run.ps1
```

The script activates `.venv` (creating it if missing), installs dev
dependencies, and launches the app.

### Step-by-step

```powershell
# 1. Create the venv (one-time)
py -m venv .venv

# 2. Activate it
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies (one-time per change)
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

# 4. Run the app
python -m app.main
```

After activation, your prompt is prefixed with `(.venv)` and `python`
resolves to `.venv\Scripts\python.exe` (where PySide6 lives).

A window titled `ArchExplorer AI` should open with three side-by-side
panels: **File Explorer** / **Editor** / **Visualizer**.

## Tests

```powershell
py -m pytest
```

Expected output: `3 passed`.

## Documentation

See [`docs/`](./docs/) for the full specification:

- [`docs/visão-geral.md`](./docs/vis%C3%A3o-geral.md) — overview
- [`docs/backend/backend.md`](./docs/backend/backend.md) — backend services
- [`docs/frontend/front.md`](./docs/frontend/front.md) — UI spec
- [`docs/guidelines/diretriz.md`](./docs/guidelines/diretriz.md) — SOLID guidelines
- [`docs/testing/testing-strategy.md`](./docs/testing/testing-strategy.md) — test strategy

## Workflow

This project follows a **Spec-Driven Development (SDD)** workflow on
top of **trunk-based development**. Each change is a folder under
[`changes/`](./changes/) containing four artifacts:

- `proposal.md` — why
- `spec.md` — what
- `design.md` — how
- `tasks.md` — checklist

Once shipped, the change folder is moved to `changes/archive/`.

## License

Apache-2.0. See [`LICENSE`](./LICENSE).
