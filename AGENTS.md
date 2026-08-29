# Repository Guidelines

## Project Structure & Module Organization

Source lives in `app/`. Keep AKShare and upstream HTTP access behind `data_provider.py`. `models.py` defines requests and market metadata; `service.py` orchestrates the workflow. Calculations, scoring, levels, charts, and export belong in their matching modules. Persistence and logging use `cache.py` and `logging_config.py`. UI files are in `templates/` and `static/`; tests are in `tests/`. Do not commit runtime output from `cache/`, `reports/`, or `logs/`.

## Build, Test, and Development Commands

Use the project virtual environment on Windows:

```powershell
.\启动平台.bat                 # validate dependencies, start the server, open the browser
.\启动平台.bat --check         # validate the environment without starting
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tests\ui_layout_check.py --url http://127.0.0.1:8000
.\.venv\Scripts\python.exe tests\ui_undo_check.py reports\example.html
docker compose up -d --build   # containerized local/NAS deployment
```

UI scripts are manual checks requiring a service or report.

## Coding Style & Naming Conventions

Target Python 3.11+, use four-space indentation, type annotations, and concise docstrings for public algorithms. Use `snake_case` for functions/modules, `PascalCase` for classes, and uppercase constants. Ruff enforces a 100-character line limit with `E`, `F`, `I`, `UP`, `B`, and `SIM`. Keep user-facing text and README content in Simplified Chinese.

## Testing Guidelines

Name pytest files `test_*.py` and tests `test_<behavior>`. Automated tests must not use live market networks; mock AKShare with deterministic DataFrames. Cover indicator boundaries/no-future behavior, normalization, stable API errors, and offline reports. Provider changes must test applicable markets (`cn_stock`, `cn_etf`, `us_stock`, `us_index`, `global_future`), including mapping, capabilities, units, timezones, snapshots, and caching. Run manual Playwright checks for UI changes and report upstream failures separately.

## Multi-Market Compatibility

Preserve legacy `auto|stock|etf` request behavior. Never guess US provider prefixes; resolve naked tickers through the AKShare code table. Never describe a global-futures continuous reference series as a specific contract. Reject unsupported periods or adjustments with stable, readable errors. Missing volume must remain neutral in scoring. Preserve China red-up/green-down and overseas green-up/red-down chart conventions.

## Commit & Pull Request Guidelines

No Git history is present in this snapshot. Use concise imperative commits and keep unrelated changes separate. Pull requests should describe behavior, tests, cache/configuration effects, and upstream limitations. Include screenshots for UI changes and link relevant issues.

## Security & Configuration

Never commit `.env`, credentials, proxy settings, reports, databases, or logs. Add settings to `.env.example`. Return stable API errors without stack traces and write diagnostics to `logs/app.log`.
