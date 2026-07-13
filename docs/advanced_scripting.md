# Advanced Custom Scripting & API Integration Guide

This guide describes how to customize, automate, or write custom integrations using the Portfolio Manager REST APIs, database hooks, and code scripting layers.

---

## 📡 1. Interactive OpenAPI Specification (Swagger / ReDoc)

FastAPI automatically generates interactive API specs from Pydantic models and routers. These are accessible in your browser on a running instance:

* **Interactive Swagger UI**: `http://localhost:8080/docs`
  * *Purpose*: Exposes a visual sandbox where you can construct and execute live API requests directly from your browser.
* **Static ReDoc UI**: `http://localhost:8080/redoc`
  * *Purpose*: Provides a structured, clean read-only outline of the entire API schema.

### Path Prefix (`BASE_PATH`) Dynamic Shifts
If the application is hosted under a custom URL prefix using the `BASE_PATH` environment variable (e.g. `BASE_PATH=/portfolio`), the documentation endpoints shift dynamically to respect the prefix:
* Swagger UI: `http://localhost:8080/portfolio/docs`
* ReDoc UI: `http://localhost:8080/portfolio/redoc`

---

## 🔌 2. RESTful CRUD API Reference

All database tables (Portfolios, Tickers, Transactions, and Dividends) expose REST endpoints. Request and response structures are validated by Pydantic models defined in [`core/schemas.py`](../core/schemas.py).

### A. Transactions CRUD
Manage historical stock or ETF purchase, sale, and split entries.
* **List Transactions**: `GET /api/transactions`
  * Parameters: `search` (filter ticker), `portfolio_id` (filter portfolio), `limit`, `offset`.
* **Create Transaction**: `POST /api/transactions`
  * *Schema* (`TransactionCreate`):
    ```json
    {
      "portfolio_id": 1,
      "ticker": "AAPL",
      "date": "2026-01-15 10:00:00",
      "action": "BUY",
      "price": 175.50,
      "quantity": 10.0,
      "currency": "USD",
      "commission": 1.00,
      "notes": "Initial purchase"
    }
    ```
* **Edit/Delete**: `PUT /api/transactions/{id}` and `DELETE /api/transactions/{id}`

### B. Dividends CRUD
Reconcile cash distributions and tax accruals.
* **List Dividends**: `GET /api/dividends`
* **Create Dividend**: `POST /api/dividends`
  * *Schema* (`DividendCreate`):
    ```json
    {
      "portfolio_id": 1,
      "ticker": "O",
      "date": "2026-02-15",
      "amount": 12.50,
      "currency": "USD",
      "tax": 3.75,
      "qty": 50.0,
      "notes": "Monthly payout"
    }
    ```
* **Edit/Delete**: `PUT /api/dividends/{id}` and `DELETE /api/dividends/{id}`

### C. Tickers Configuration
Update ticker attributes (tax rates, categories, classifications).
* **Update Ticker**: `PUT /api/tickers/{ticker_id}`
  * *Schema* (`TickerUpdate`):
    ```json
    {
      "friendly_name": "Apple Inc.",
      "tax_rate": 0.30,
      "category": "growth",
      "subclass": "technology",
      "notes": "Core position"
    }
    ```

---

## 💾 3. Data File Uploads & Reconciliation

You can programmatically feed external configuration caches, options positions, or statements to the manager:

* **Endpoint**: `POST /api/upload`
* **Content-Type**: `multipart/form-data`
* **Payload Fields**:
  * `document_type`: A valid document key matching the dictionary in `config/config.json` (e.g. `ib-data` or `stock-options`).
  * `file`: The target file binary.
* **Example Ingestion**:
  ```bash
  curl -X POST http://localhost:8080/api/upload \
    -F "document_type=ib-data" \
    -F "file=@/path/to/ib_data.json"
  ```

---

## 🖩 4. Cache Invalidation & Rebuilds

If you run cron jobs or python scripts that perform bulk writes directly to the SQLite database on disk (`data/portfolio.db`), the in-memory rendering cache will become stale. You must trigger a views rebuild to refresh the frontend:

* **Endpoint**: `POST /api/dashboard/rebuild`
* **Query Parameters**:
  * `sync` (boolean): Set to `true` to force a blocking synchronous execution (useful for waiting scripts). Defaults to `false`.
  * `ingest_ibkr_cash` (boolean): Set to `true` to ingest margin parameters and cash reports from `ib_data.json`.
* **Example Script Trigger**:
  ```bash
  curl -X POST "http://localhost:8080/api/dashboard/rebuild?sync=true"
  ```

---

## 🛠️ 5. DB Migration Patches Engine

The application includes a system to execute custom data repair or patching scripts without logging in to the docker containers natively:

1. **Write the Script**: Create a folder in `patching/` with a 4-digit number and description (e.g., `patching/0002_custom_broker_fix/patch.py`).
2. **Implement Hook**: The script must define a `patch` entry point:
   ```python
   # patching/0002_custom_broker_fix/patch.py
   def patch(params: dict = None):
       # Access DB connection, perform data manipulation, etc.
       print(f"Running custom patch with params: {params}")
   ```
3. **Execute**: Trigger execution from the Control Center GUI **Maintenance** panel or trigger it programmatically via `POST /api/patches/run`.
