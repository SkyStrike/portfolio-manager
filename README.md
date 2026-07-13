# Self-Hosted Portfolio Manager

A self-hosted, lightweight investment portfolio manager built with a Python (FastAPI + SQLite) backend and a modern HTML5 + Vanilla CSS + JS frontend.

### 🎯 Project Origins & Intention
This tracker originally started as a simple tool to monitor cash flows and dividend distributions, focusing on custom asset groupings for **thematic plays** or for consolidated tracking of **stocks with multiple tickers** (e.g. mapping single-stock YieldMax ETFs alongside their actual underlying equities and/or ADRs in a single view).

Over time, the project evolved into a full-featured dashboard. The codebase heavily favors **Interactive Brokers (IBKR)** integration because it is my primary brokerage account and supports easy API connectivity using the `ib_insync` library. The system also supports manual entries and CSV sheets for other brokers like **Moomoo**, though full API automation is not implemented for them due to limitations with their official SDKs.

---

## 🔒 Environment & Security Context

This project is architected strictly for a **private, single-user local network environment**. It is **not** designed or audited to be exposed to the public internet or hosted in a multi-tenant environment. 

To maintain lightweight development and simple administrative operations, certain functionalities are intentionally permissive:
* **Dynamic Database Patching**: The patching module dynamically imports and executes Python scripts directly from the `patching/` directory based on local JSON manifest instructions.
* **Database Hot-Restores**: The system allows SQLite hot-backups, downloads, deletes, and restorations on-the-fly without built-in credentials.

No authentication, CSRF validation, or multi-user access controls are implemented. If you expose this application to a public network, you do so at your own risk. It is highly recommended to run this container locally or strictly behind a secure private VPN (e.g. Tailscale, WireGuard).

> [!WARNING]
> **Financial & Valuation Disclaimer**: This repository is provided **AS-IS** without any warranties of any kind. The author(s) and contributor(s) are not responsible or liable for any financial loss, transaction accounting discrepancies, incorrect portfolio valuations, trading errors, or damages resulting from bugs or errors in this project. Use at your own risk.

---

## 🛠️ Getting Started

### Method 1: Using Docker Compose (Recommended)

1. Build and start the container in the background:
   ```bash
   docker compose up -d --build
   ```
2. Open your browser and navigate to `http://127.0.0.1:8080`.
3. To stop the container:
   ```bash
   docker compose down
   ```
*Note: SQLite database files are persistently stored in the `./data` directory on the host.*

### Method 2: Running Locally (Without Docker)

1. Create a Python virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Initialize the SQLite database schema:
   ```bash
   python3 core/database.py
   ```
3. Start the Uvicorn development server:
   ```bash
   uvicorn app:main_app --host 127.0.0.1 --port 8080 --reload
   ```
4. Open your browser and navigate to `http://127.0.0.1:8080`.
 

---

## 🚀 Key Features

* **Multi-Portfolio & Combined Net Worth**: Consolidated overview ("My Net Worth") alongside individual broker/portfolio segments with customizable sorting priorities.
* **Interactive Transaction & Dividend Ledger**: A dynamic management interface (`trades.html`) for editing, deleting, or manually inputting historical stock transactions and dividend distributions.
* **FIFO Financial Calculation Engine**: Calculates FIFO cost basis, capital gains (realized P&L), and rolls transaction data into 12-month charts and net/gross dividend aggregates in SGD.
* **Interactive Dividend Calendar**: Grid/List monthly visualization (`dividend_calendar.html`) with calendar views, monthly totals, search filters, and Interactive Brokers (IBKR) statement synchronization.
* **IBKR Statement Reconciliation**: Automatically compares database positions against uploaded IBKR statement positions (`ib_data.json`) to display mismatch warnings and sync badges.
* **Options & Stress-Testing Dashboards**: Integrates with external options trackers to visualize active contracts, risk exposure metrics, expiration profiles, and cash stress tests.
* **Dynamic Database Backups & Patching**: Admin tools for managing, downloading, and hot-restoring database backups on-the-fly, alongside custom patching manifests for data migrations.
* **Smart Yahoo Finance Batch Ingestion**: Fetches prices in single batches using `yfinance` with intelligent UTC/GMT cache checks, avoiding redundant API calls for closed markets.
* **Transaction Visualizer (TX Visualizer)**: View per-ticker historical stock price candlestick charts (7d, 1m, 3m, 6m, YTD, 1y, 5y, all, and custom date range) overlaying your historical buy/sell trade executions directly on the price curve, with interactive tooltips showing trades and 3-decimal OHLC data.

---

## ⚙️ Configuration & Environment Variables

The application can be configured using environment variables (e.g., in `docker-compose.yml`) or via settings inside `config/config.json` (defaults) or `data/config.json` (user overrides).

### Configuration Overrides Priority
To support dynamic configurations and user-specific customizations:
1. **Database settings table overrides**: Custom configurations stored in the SQLite database (e.g., `sorting.classification_priority`, `external_services.options_tracker_url`, `external_services.backtester_url`) take the highest priority. These can be easily updated via the **Settings** editor tab in the Admin Dashboard.
2. **`data/config.json`** overrides (falls back to `config/config.json` default templates).

If you want to customize your setup, simply place/upload your custom files into `data/`. For a complete catalog, purpose description, and schema details of all configuration, cache, and input files, see the [JSON Data Files Reference](docs/data_files.md).

### Environment Variables
* `BASE_PATH`: Set this (e.g. `/portfolio`) to host the application under a custom prefix path. All internal endpoints, client-side fetch commands, header links, and script references will adapt dynamically.
* `PORTFOLIO_DB_FILE`: File path for the SQLite database.
* `exchange_rates_file`: File path for exchange rate caches.

### Dynamic Upload Configuration (`config/config.json`)
The types of files allowed for upload are stored dynamically in [config/config.json](config/config.json). You can add or modify allowed targets on the fly without restarting or rebuilding the container. Note that file uploads for configurations are written directly to `data/` so they remain untracked:

```json
  "allowed_documents": {
    "stock-options": "data/stock-options.json",
    "ib-data": "data/ib_data.json"
  }
```

---

## 🔌 External Services Integration

The application integrates with external services configured under the `"external_services"` key in `config/config.json` (or `data/config.json` overrides):

```json
  "external_services": {
    "options_tracker_url": "http://yui.home/options-tracker",
    "backtester_url": "http://yui.home/backtester/"
  }
```

### 1. Options Tracker Service (`options_tracker_url`)
* **Repository**: https://github.com/SkyStrike/options-tracker
* **Purpose**: Fetches active options contracts, strategy legs, assignment risk, and premium metrics.
* **Configured Behavior**:
  * The dashboard builder requests live options positions from this endpoint.
  * Displays the **Active Open Options** table.
  * Calculates and renders the **Risk & Liquidity Analysis** sections (Options Exposure & Risk, Cash Stress Test, Portfolio Stress Test, Expiration Profile).
  * Appends option P/L data to the main card header (**"Daily Performance & Options Unrealized"**).
  * **Fallback**: If the endpoint is offline or times out, the backend falls back to the local `data/stock-options.json` file cache (if available).
* **Unconfigured/Empty Behavior**:
  * Setting this URL to `""` or omitting it completely disables options tracking.
  * All options tables, exposure/risk metrics cards, and stress tests are completely hidden from the user interface.
  * The header card fallback behaves cleanly, displaying only **"Daily Performance"**.

### 2. Backtesting Service (`backtester_url`)
* **Repository**: https://github.com/SkyStrike/backtester
* **Purpose**: Links underlying assets from the dashboard to a historical backtesting engine.
* **Configured Behavior**:
  * Renders a direct backtest link (🔗) next to the header of each underlying asset group.
  * Clicking the link redirects to the backtest service with tickers and date boundaries pre-populated in the query parameters:
    `http://yui.home/backtester/?tickers=QQCL.TO,HYLD-U.TO&startDate=2025-01-01&endDate=2026-06-20`
  * The tickers are automatically converted to their respective `yfinance` formats.
  * The `startDate` defaults to the earliest transaction date recorded for the underlying group.
* **Unconfigured/Empty Behavior**:
  * Setting this URL to `""` or omitting it disables the backtester links. No link icons are shown next to the underlying assets.

---

## 🖩 Interactive Utilities

### 1. Position Calculator Widget
The application includes a comparative multi-ticker **Position Calculator** that floats at the bottom-right of the dashboard:
* **Side-by-Side Comparison**: Open multiple ticker columns at once to simulate price and transaction size variations.
* **Capital Flow Direction**: Color-coded and signed transacted amounts (outflows/buys are negative red, inflows/sells are positive green).
* **Denominator Adjustment**: Automatically adjusts the total portfolio market value denominator by the sum of all transacted values for true projected weightage.
* **Within-Stock Trimming %**: Computes and displays the change percentage within the individual asset to visualize trim ratios (e.g. `-25%` trim).
* **Enforced Lot Guidances**: Enforces a minimum lot size of `100` for Singapore/Canadian listings, and `1` for standard US stocks.
* **Max Populate Shortkey**: Click the `Max: -[qty]` link next to the lot guide to instantly populate the simulated shares input field for full liquidations.

---

## 📂 Project Structure

The project has been refactored into a modern, modular architecture:

* [app.py](app.py): Entrypoint file serving the FastAPI REST API, registering modular sub-routers, and scheduling background loops.
* **`core/`**: Core databases, calculations, cache layers, and schemas.
  - [core/database.py](core/database.py): SQLite database schema definition, settings table, and migrations (no default portfolios are seeded; the database starts completely clean).
  - [core/calculations.py](core/calculations.py): FIFO cost-basis matching calculations, realized P&L, and currency conversions.
  - [core/models.py](core/models.py): Object representations for portfolios, positions, and trades.
  - [core/cache.py](core/cache.py): Handles in-memory dashboard rendering caches.
  - [core/dashboard_builder.py](core/dashboard_builder.py): Base metrics aggregator for dashboard compilation.
  - [core/performance_calculator.py](core/performance_calculator.py): Performance metrics and cash assets daily calculator.
  - [core/schemas.py](core/schemas.py): Pydantic validation schemas for API endpoints.
* **`services/`**: Command-line tools, background integrations, and rendering pipelines.
  - [services/rebuild_dashboard.py](services/rebuild_dashboard.py): Dashboard builder orchestration. Renders HTML outputs statically.
  - [services/price_service.py](services/price_service.py): Manages Yahoo Finance updates.
  - [services/fetch_exchange_rates.py](services/fetch_exchange_rates.py): Central bank exchange rates pull services.
  - [services/report_renderer.py](services/report_renderer.py): Compiles Jinja2 dashboard pages.
  - [services/dividend_service.py](services/dividend_service.py): Syncs upcoming dividend ex-dates and estimates distributions.
  - [services/generate_dividend_calendar.py](services/generate_dividend_calendar.py): Formats schedules and compiles static dividend calendar JSON.
* **`ingestion/`**: Data parsing and intake pipelines.
  - [ingestion/importer.py](ingestion/importer.py): Parses Holdings and Transactions CSV exports.
* **`routers/`**: Decoupled, modular controller endpoints (views, uploads, CRUD API, patches, reports).

---

## 🗃️ Supplementary Data Files

The system relies on supplemental data files (typically placed in the `/data` or `/config` directory) to enrich calculations and coordinate settings.

| File Path | Description / Purpose | Usage & Behavior | If Missing / Default |
| :--- | :--- | :--- | :--- |
| **`data/config.json`** | Application parameters (conversion rates, color schemes, allowed uploads). | Loaded on startup and UI render. Primary config. | Falls back to **`config/config.json`**. |
| **`data/ib_data.json`** | Broker position report containing actual holdings size, cost basis, and balances (NetLiquidation, GrossPositionValue, TotalCashValue) for IBKR. | Used for stock reconciliation (`IB Sync` badge / `IB Mismatch` warning) and cash reporting. | Reconciliation checks are skipped; cash reports default to database-only. |

---

## 📖 User Guides & Documentation

Additional step-by-step documentation guides are available in the [docs/](docs/) directory:

1. **[Data Migration Guide](docs/data_migration.md)**: Exporting portfolios from Snowball Analytics and importing them.
2. **[IBKR Dividend & Verification Guide](docs/ibkr_dividend_import.md)**: Accruals integration, XML flex imports, position reconciliation, and custom API requests.
3. **[Metadata Configuration Guide](docs/metadata_config.md)**: Setting custom classifications and brokers.
4. **[File Upload API Guide](docs/file_uploads.md)**: Uploading stock-options, ib-data, and ibkr-dividends data files with upload verification details.
5. **[Position Calculator Guide](docs/position_calculator.md)**: Simulating transactions, lot-size restrictions, cashflows, and dynamic weightage calculations.
6. **[Daily Weekday Metrics Job Guide](docs/daily_metrics_job.md)**: Background daily updates, 6 AM SGT cron scheduling, cache pre-warming, and manual overrides.
7. **[IBKR Data File Guide](docs/ib_data_guide.md)**: Information regarding formatting, uploading, and external cron ingestion setups for `ib_data.json`.
8. **[System Maintenance & Patching Guide](docs/patching.md)**: Exposing database backups, hot-restores, manifest parameter configuration schema, and writing custom Python patch modules.
9. **[Broker Capital CSV Guide](docs/capital_csv.md)**: Managing and importing capital records for returns tracking.
10. **[JSON Data Files Reference](docs/data_files.md)**: Catalog and structural JSON schemas for system configurations and IBKR inventory caches.
11. **[Advanced Scripting & API Guide](docs/advanced_scripting.md)**: Custom automation scripts, programmatic database pre-warming triggers, RESTful schema lookups, and interactive Swagger UI configurations.

---

## 📄 License

This project is open-source and licensed under the [MIT License](LICENSE).
