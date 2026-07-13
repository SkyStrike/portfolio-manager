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

## 3. Custom Scripting & Ingestion Setup

> [!IMPORTANT]
> The expected `ib_data.json` file format **is not natively available as an export from Interactive Brokers**. It requires writing a custom client-side script to connect to the IB Gateway/TWS API, extract values, format them, and write them to this path.
>
> In the project architecture, this is implemented via a companion service (**`services/ib-worker`**) which connects to the IB Gateway using the popular **`ib_insync`** Python library.

> [!CAUTION]
> **Why `ib-worker` is Private & Safety Notice**: The companion `ib-worker` service is kept private and is not available in the public repository. Connecting code directly to an active brokerage account/portfolio carries extreme risks. If unauthorized parties gain access to the broker API port or if unverified script configurations downloaded from the internet are executed, it can lead to severe security breaches, unintended market transactions, and substantial monetary losses. For security and safety, users must write and audit their own custom integration scripts.

### How to Build Your Own Extraction Script
To construct your own extraction script, you can run a Python program that connects to IB Gateway using `ib_insync`. The script should query and parse the following key API objects and attributes:

#### A. Fetching Account Balances
Query **`ib.accountValues()`** to retrieve general account parameters. Loop through the returned objects and filter by `.tag`, converting the string `.value` to a float:
* `NetLiquidation`: Total liquidation value of the account.
* `GrossPositionValue`: Total market value of all open long/short stock positions.
* `TotalCashValue`: Total cash available.

*Example code block:*
```python
balances = {}
for val in ib.accountValues():
    if val.tag in ["NetLiquidation", "GrossPositionValue", "TotalCashValue"]:
        balances[val.tag] = float(val.value)
```

#### B. Fetching Portfolio Positions
Query **`ib.portfolio()`** to retrieve open positions. Each item yields transaction records and contract metadata:
* **Contract Details** (`item.contract`):
  * `item.contract.symbol`: The ticker symbol (e.g. `AAPL`).
  * `item.contract.localSymbol`: The local identifier/description.
  * `item.contract.secType`: The security type (e.g. `STK`, `OPT`).
  * `item.contract.primaryExchange`: Exchange where the asset trades.
  * `item.contract.currency`: The trading currency (e.g. `USD`, `SGD`).
* **Position Details** (`item`):
  * `item.position`: Number of shares currently held.
  * `item.averageCost`: Average cost per share (used as cost basis).
  * `item.marketPrice`: Latest market price.
  * `item.marketValue`: Current market value.
  * `item.unrealizedPNL`: Unrealized profit/loss.
  * `item.realizedPNL`: Realized profit/loss.

*Example code block:*
```python
portfolio = []
for item in ib.portfolio():
    contract = item.contract
    portfolio.append({
        "symbol": contract.symbol,
        "description": contract.localSymbol,
        "type": contract.secType,
        "exchange": contract.primaryExchange,
        "position": item.position,
        "cost_basis": item.averageCost,
        "current_price": item.marketPrice,
        "market_value": item.marketValue,
        "unrealized_profits": item.unrealizedPNL,
        "realized_profits": item.realizedPNL,
        "currency": contract.currency
    })
```

Combine these elements into a single JSON object containing `balances` and `portfolio` structures and save it as `ib_data.json`.

---

## 4. Ingestion Options

Once the `ib_data.json` file is generated, you have two options to import it into the Portfolio Manager:

### Option A: Background Filesystem Watcher (Cron)
If running locally, place the generated file directly at `data/ib_data.json`. The daily weekday cron job running at 6:00 AM SGT reads this file to ingest cash metrics under `balances` into the database, and the dashboard reads it on-demand for position reconciliation.

### Option B: Upload via REST API (`POST /api/upload`)
You can programmatically post the file using `curl` or a python request to the document upload endpoint to trigger immediate database reconciliation:
```bash
curl -X POST http://localhost:8080/api/upload \
  -F "document_type=ib-data" \
  -F "file=@/path/to/ib_data.json"
```

---

## 5. What is Missing if `ib_data.json` is Not Provided?

If you choose not to supply the `ib_data.json` file, the Portfolio Manager will continue to function but with the following limitations:

1. **No Position Reconciliation Badges**: The dashboard will not display the `IB Sync` (green check) or `IB Mismatch` (red warn) badges next to your holdings, as the engine cannot verify database records against actual broker holdings.
2. **Missing Cash Balances in Net Worth**: Since `balances` parameters (like `NetLiquidation` and `TotalCashValue`) are not provided, your historical net worth calculations will only include stock positions, and the Net Worth chart under **Charts** will lack historical broker-cash trends.
3. **Daily Cash Metrics Ignored**: The daily scheduled metrics job will skip cash-history ingestion for IBKR portfolios.

> [!NOTE]
> Even if `ib_data.json` is missing or not configured, you can still manually record or upload historical cash balances (including Net Liquidation, Gross Position Value, and Cash on Hand) for any date and broker (including IBKR) directly via the **Control Center -> Settings** manual override panels in the GUI.


