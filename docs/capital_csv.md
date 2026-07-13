# Broker Capital CSV Guide

This document details the purpose, schema format, and in-memory usage of the **Capital CSV** records which register capital inflow/outflow injections for performance tracking.

---

## 1. Purpose of Capital Records

To compute accurate time-weighted and money-weighted returns (realized/unrealized P&L percentages), the Portfolio Manager needs to know how much cash capital was deposited or withdrawn over time. 
* **Broker Isolation**: Capital is tracked per broker (e.g., `IBKR`, `MOOMOO`).
* **In-Memory Processing**: The uploaded CSV file is processed completely in-memory, updating database records directly without storing the file on disk.
* **Database Target**: Uploading this CSV synchronizes data into the **`broker_capital_entries`** SQLite table.
* **Aggregations**: Calculated net asset valuations (NAV) are compared against the active running total of base capital for any given date to chart returns.

---

## 2. CSV Format Specification

The ingestion engine expects a CSV structure with at least **4 columns** ordered as follows:

| Column Index | Header Field | Expected Value Type | Description / Notes |
| :--- | :--- | :--- | :--- |
| **0** | `Broker` | `TEXT` | Name of the broker (e.g. `IBKR`, `MOOMOO`). Case-insensitive (will be normalized to uppercase). |
| **1** | `Date` | `TEXT` | The date of the capital action. (Format: `YYYY-MM-DD` or `YYYY-Mon DD` e.g., `2024-Dec 01`). |
| **2** | `Remarks` | `TEXT` | Any descriptive remarks (e.g. `Initial Funding`, `Monthly Deposit`). |
| **3** | `Amount` | `REAL` | The numeric currency amount (e.g. `5000.00`). Positive values denote deposits; negative values denote withdrawals. |

### Example CSV Contents:
```csv
Broker,Date,Remarks,Amount
IBKR,2026-01-01,Initial Deposit,10000.00
IBKR,2026-Dec 01,Additional Funding,2500.00
MOOMOO,2026-02-01,Promo Deposit,5000.00
IBKR,2026-05-10,Partial Withdrawal,-1000.00
```

---

## 3. Uploading & Ingestion Methods

### Method A: UI Upload
1. Navigate to the **Control Center** tab of the Portfolio Manager.
2. Under the file uploads section, locate **Capital CSV File**.
3. Select your `.csv` file and click **Upload**.
4. The system will parse the file in memory, wipe the legacy entries in the `broker_capital_entries` database table, perform a clean re-seed, and rebuild the static dashboard views automatically. No file is written to disk.

### Method B: REST API Endpoint
You can post the file directly to the dedicated import endpoint:
```bash
curl -X POST "http://localhost:8080/api/settings/capital/import" \
  -F "file=@/path/to/my_capital.csv"
```
