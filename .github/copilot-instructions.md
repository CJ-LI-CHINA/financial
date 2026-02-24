## Quick Orientation

- **Purpose:** This repo is an A‑share quantitative data collection and analysis tool. Core flows: fetch daily market data -> compute indicators -> persist to PostgreSQL -> run simple analyzers.
- **Primary entrypoint:** `main.py` (CLI flags: `--update`, `--analyze <code>`, `--check`, `--retry`, `--corporate-actions`, `--clean`).
- **Date format:** use `YYYYMMDD` strings (e.g. `20240101`) across CLI and data functions.

## High-level architecture

- `data/` : data ingestion and pre-processing. Key file: `data/collector.py`. Uses `akshare` to fetch daily (前复权) data, computes indicators via `data/indicators.py`, and writes to DB through `database/postgres.py`.
- `analysis/` : stock signal logic. `analysis/strategies.py` reads prepared DataFrames from the DB and applies KDJ/MAs etc.
- `database/` : `postgres.py` is the DB adapter (psycopg2). It exposes: `create_tables()`, `get_latest_dates()`, `insert_stock_data(data)`, `get_stock_data(code,start,end)`, `check_stocks_in_db()` and `delete_delisted_stocks()`.
- `config/` : single source of runtime constants in `config/settings.py` (`DB_PARAMS`, `DATA_CONFIG`, `LOG_CONFIG`).
- `utils/` : helper utilities (e.g. `is_trading_day`, `determine_end_date`) used by collectors.

## Important project-specific conventions

- Stock codes are strings and treated as 6-digit A‑share codes (e.g. `600737`). When calling `akshare` the code is prefixed: `sh` for codes starting with `6`, otherwise `sz`.
- Date ranges and CLI flags expect `YYYYMMDD` strings. DB queries embed these directly in SQL (see `PostgresDB.get_stock_data`).
- The code excludes Beijing Stock Exchange symbols by filtering codes that start with `8`, `43`, or `92` in `DataCollector.get_stock_list()`.
- Indicators are computed in `data/indicators.py` and attached as DataFrame columns: `ma5`, `ma10`, `ma20`, `macd`, `macd_signal`, `macd_hist`, `kdj_k`, `kdj_d`, `kdj_j` — analyzers expect these names.
- Failed update attempts are written to `failed_stocks.csv` with columns `code,error` and re-tried when `DataCollector.update_all_stocks_data(retry_failed=True)` is used.

## Integration points and external dependencies

- Data sources: `akshare` (primary), `pytdx` present in `requirements.txt` for alternate collectors (see `data/collector_tdx.py`).
- Database: PostgreSQL via `psycopg2`. Configure connection in `config/settings.py` `DB_PARAMS` before running.
- Required packages (see `requirements.txt`): `numpy`, `pandas`, `akshare`, `pytdx`, `psycopg2`.

## Development & run workflows (concrete commands)

1. create and activate a Python environment (Windows PowerShell examples):

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Ensure PostgreSQL is running and `config/settings.py` DB_PARAMS point to a valid DB. Create the `stock_data` table or call `PostgresDB.create_tables()` from a short script/REPL.

3. Typical run to update all data (respecting `DATA_CONFIG`):

```
python main.py --update
```

4. Analyze a specific stock (example):

```
python main.py --analyze 600737 --start 20240101 --end 20241231
```

5. Retry failed stocks previously recorded to `failed_stocks.csv`:

```
python main.py --retry
```

Notes: there is no test runner configured. `test/test1.py` is an ad-hoc script, not a pytest suite.

## Coding guidance for AI agents (concrete, repo-specific)

- Respect existing column names and types when modifying `data/indicators.py` or consumers in `analysis/` and `database/`.
- Avoid changing the `date`/`code` composite primary key in `postgres.py` unless you update every insert/query path.
- Use `DATA_CONFIG["retry_interval"]` to throttle calls to `akshare`. Do not hardcode sleeps.
- When instantiating DB objects, ensure `close()` is called. The code often creates `PostgresDB()` instances inside modules and scripts — follow this pattern and close them explicitly.
- Keep date formatting as `YYYYMMDD` strings for APIs that expect strings; convert to `date` objects only at DB boundaries or in helpers.
- When adding new CLI flags in `main.py`, follow the existing pattern (add to argparse, act on args, re-use `DataCollector`/`PostgresDB` objects where appropriate).

## Files to inspect when changing behavior

- `main.py` — CLI orchestration and common usage patterns.
- `data/collector.py` — the main ingestion loop and retry/failure handling.
- `data/collector_tdx.py` and `data/collector_akshare.py` — alternative data collectors and how they differ.
- `data/indicators.py` — indicator names and calculation details.
- `database/postgres.py` — SQL and schema conventions.
- `config/settings.py` — all environment/config values (DB + data throttling + file names).

## Safety notes and gotchas discovered in repo

- SQL queries in `PostgresDB.get_stock_data` are built by string interpolation; avoid introducing untrusted inputs. Prefer parameterized queries if refactoring.
- Multiple `PostgresDB()` instances are created across code — long-lived connections may be opened; callers generally call `close()` but review changes to prevent connection leaks.
- `is_trading_day` is simplified (weekend-only). Do not assume holiday awareness unless you add that logic.

---
If any of these sections are unclear or you want more examples (e.g., sample DataFrame shapes, sample SQL rows, or a small walkthrough of `update_all_stocks_data`), tell me which part to expand and I will iterate.
