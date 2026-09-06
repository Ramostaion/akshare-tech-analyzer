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

UI scripts are manual checks requiring a service or report. Run `tests\ui_quant_check.py` after changing quant panels, Plotly replacement, auto-refresh, or responsive behavior.

## Coding Style & Naming Conventions

Target Python 3.11+, use four-space indentation, type annotations, and concise docstrings for public algorithms. Use `snake_case` for functions/modules, `PascalCase` for classes, and uppercase constants. Ruff enforces a 100-character line limit with `E`, `F`, `I`, `UP`, `B`, and `SIM`. Keep user-facing text and README content in Simplified Chinese.

## Testing Guidelines

Name pytest files `test_*.py` and tests `test_<behavior>`. Automated tests must not use live market networks; mock AKShare with deterministic DataFrames. Cover indicator boundaries/no-future behavior, normalization, stable API errors, and offline reports. Provider changes must test applicable markets (`cn_stock`, `cn_etf`, `us_stock`, `us_index`, `global_future`), including mapping, capabilities, units, timezones, snapshots, and caching. Run manual Playwright checks for UI changes and report upstream failures separately.

## Multi-Market Compatibility

Preserve legacy `auto|stock|etf` request behavior. Never guess US provider prefixes; resolve naked tickers through the AKShare code table. Never describe a global-futures continuous reference series as a specific contract. Reject unsupported periods or adjustments with stable, readable errors. Missing volume must remain neutral in scoring. Preserve China red-up/green-down and overseas green-up/red-down chart conventions.

## Signal & Chart Presentation

Treat Setup, close-confirmed Trigger, next-bar execution, and completed TradeRecord as separate events. Yellow buy markers belong on the Trigger confirmation bar, must exclude exit signals, and must not be described as executed prices. If repeated Trigger bars are deduplicated or given a cooldown, document the policy and add no-future tests. Plot only the Top-1 wave candidate on the K-line chart, connect confirmed pivots, and label unfinished waves without presenting an unconfirmed endpoint as final. Wave continuation and invalidation paths are scenarios, not time forecasts; their horizontal span must remain explicitly illustrative. Gann overlays must use right-confirmed anchors and an explicit normalized price/time scale; never describe screen angles, cycle windows, or projected intersections as exact future prices or dates. Algorithm-layer toggles must hide the complete matching trace/shape/annotation group without resetting zoom or user drawings. Auto-refresh must preserve a manually zoomed Plotly view only when symbol, market, period, date range, and chart context are unchanged; a manual analysis or changed context may reset the view. Keep Factor Snapshot available for audit but collapsed by default in the workbench.

Wave analysis must maintain competing upward and downward counts, assign stable lifecycle identifiers, and retire hard-invalidated candidates from the main view. Searches may skip at most two minor confirmed pivots inside a bounded recent window and must penalize that complexity. Developing wave stages must never promote an unconfirmed endpoint to a numbered pivot. Cross-scale agreement is supporting evidence only; ambiguity must remain neutral. Historical replay must deduplicate candidate lifecycles, end an old lifecycle when a new same-group count supersedes it, and scale its observation horizon to the structure span. Wave context may support or conflict with a strict Trigger but must never create an order by itself.

Wyckoff analysis must keep accumulation and distribution as competing candidates, use causal frozen trading ranges, and enforce event-order prerequisites. Distinguish close-confirmed events from later follow-through confirmation. Historical validation must deduplicate each frozen-range lifecycle and report structure confirmation separately from post-confirmation target outcomes.

Gann analysis must keep upward and downward anchors as competing right-confirmed candidates. Freeze the current anchor between confirmations, but promote a newer same-direction ATR-significant pivot once its right-side confirmation completes; retain older valid anchors only as long-horizon references. Derive every fan point from the promoted anchor with a fixed normalized unit and never rebase a fan on the latest close. Treat angle events and time-price resonance as supporting or conflicting evidence only, never as standalone orders or exact forecasts. Historical validation must end the prior lifecycle at promotion, deduplicate anchor lifecycles, and report confirmation, angle-touch behavior, and outcomes separately.

## Commit & Pull Request Guidelines

No Git history is present in this snapshot. Use concise imperative commits and keep unrelated changes separate. Pull requests should describe behavior, tests, cache/configuration effects, and upstream limitations. Include screenshots for UI changes and link relevant issues.

## Security & Configuration

Never commit `.env`, credentials, proxy settings, reports, databases, or logs. Add settings to `.env.example`. Return stable API errors without stack traces and write diagnostics to `logs/app.log`.
