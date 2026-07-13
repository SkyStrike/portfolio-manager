# IBKR Data File Guide (ib_data.json)

This guide documents the purpose, structure, ingestion methods, and usage of the `data/ib_data.json` file in the Portfolio Manager.

---

## 1. Overview & Purpose

The `ib_data.json` file acts as the primary data exchange bridge between Interactive Brokers (IBKR) and the Portfolio Manager. It is used to:
1. **Reconcile Stock Quantities**: Compare SQLite-calculated transaction shares with actual IBKR broker holdings to display status badges (`IB Sync` or `IB Mismatch` warnings).
2. **Track Cash Balances**: Record Net Liquidation Value, Gross Position Value (Stock Value), and Cash on Hand to build the historical Combined Net Worth performance graphs.

---

## 2. Expected JSON Schema

The file expects the following JSON structure:

```json
{
  "balances": {
    "NetLiquidation": 450000.0,
    "GrossPositionValue": 415000.0,
    "TotalCashValue": 35000.0
  },
  "portfolio": [
    {
      "symbol": "AAPL",
      "position": 100.0,
      "cost_basis": 15000.0,
      "current_price": 180.0,
      "market_value": 18000.0,
      "unrealized_profits": 3000.0,
      "currency": "USD"
    }
  ]
}
```

### Schema Parameters:
* **`balances`**:
  * `NetLiquidation`: Total liquidation value of the account.
  * `GrossPositionValue`: Total market value of all open long/short stock positions.
  * `TotalCashValue`: Total cash available.
* **`portfolio`** (array):
  * `symbol`: Asset ticker symbol.
  * `position`: Number of shares currently held.
  * `cost_basis`: Average total cost basis.
  * `current_price`: Last traded price.
  * `market_value`: Current market valuation.
  * `unrealized_profits`: Unrealized profit/loss.
  * `currency`: Currency code (e.g. `"USD"`, `"SGD"`).

---

## 3. Ingestion & Cron Setup

While the system supports manual uploads, **the current implementation mostly relies on an external cron job to fetch this data from IBKR and write it directly to the `data/ib_data.json` file path.**

Once the file is written to `data/ib_data.json`:
* The daily weekday cron job running at 6:00 AM SGT reads this file to ingest the cash metrics under `balances` into the database.
* The application reads the `portfolio` array on-demand when rendering the dashboard to compute reconciliation sync badges.

---

## 4. Manual Upload Method

If you need to upload `ib_data.json` manually without waiting for the automated script, use the generic document upload API:

### `POST /api/upload`
* **Form Parameters**:
  * `document_type`: `ib-data`
  * `file`: The local `ib_data.json` file stream.
* **Example `curl` Request**:
  ```bash
  curl -X POST http://localhost:8080/api/upload \
    -F "document_type=ib-data" \
    -F "file=@/path/to/ib_data.json"
  ```
Uploading the file directly via this API will automatically update both the stock reconciliation state and the daily cash metrics database entry for that day, followed by an immediate dashboard rebuild.
