# Daily Weekday Metrics Job

This guide documents the behavior, schedule, and execution flow of the automated **Daily Weekday Metrics Job** configured within the Portfolio Manager.

---

## 1. Overview & Purpose

The automated daily metrics job is a background worker task that runs daily (Tuesday through Saturday mornings SGT). These metrics are tracked daily to compute portfolio Mark-to-Market (MTM) and Year-to-Date (YTD) performances. Specifically, the job performs the following tasks:
1. **Fetch & Update End-of-Day Prices**: Query Yahoo Finance for the latest daily closing prices for all active tickers.
2. **Update Upcoming Dividends**: Sync the upcoming ex-dividend dates and payout amounts.
3. **Seed Cash Balances (IBKR)**: Ingest the latest cash balances (Net Liquidation Value, Gross Position Value, and Total Cash Value) from `data/ib_data.json` into the `daily_cash_report` database table.
4. **Pre-warm View Caches**: Regenerate both the `intraday` and `closing` static HTML/JSON views to ensure instant load times for users.

---

## 2. Schedule & Timing

### Tuesday to Saturday at 6:00 AM SGT (GMT+8)
* **Rationale**: The New York Stock Exchange (NYSE) closes at 4:00 PM EST (standard time) / EDT (daylight saving time). This corresponds to 4:00 AM / 5:00 AM SGT the following morning.
* **Weekday Check**: Running on **Tuesday through Saturday mornings** ensures we capture the closing data for **Monday through Friday NYSE trading days**.
* **Timezone Parity**: While run triggers align with SGT, all update timestamps in the database are stored as **GMT/UTC** to maintain consistency across different development and production host machines.
* **Configuration**: The target run hour can be configured dynamically in `config/config.json` (or overridden in `data/config.json`):
  ```json
  "cron": {
    "metrics_run_hour": 6
  }
  ```

---

## 3. Ingestion & Override Behavior

To allow seamless coordination between automated scripts and manual updates, the ingestion of cash balances follows a strict control path:

### 3.1 Cash Metric Ingestion (IBKR)
* **Triggered Only During Specific Events**: The ingestion of cash report metrics from `data/ib_data.json` to the database is restricted to:
  1. The automated **6:00 AM SGT Daily metrics job**.
  2. A direct file upload of a new `ib_data.json` file using `/api/upload`.
* **Standard Rebuilds Don't Overwrite**: Any subsequent dashboard cache rebuilds (triggered by manual transaction entries, navigation, page refreshes, or hourly price updates) do **not** re-ingest the file balances.

### 3.2 Manual Overrides
* **Override Anytime**: You can manually update or override the cash metrics for any broker (including IBKR) using the **Settings UI** or the dedicated HTTP POST API:
  `POST /api/settings/cash-metrics/upload?broker=IBKR`
* **Protection of Override Data**: Once overwritten via the UI/API, the manual values are safe from being replaced during the day by subsequent intraday price updates or page renders.

### 3.3 Behavior When ib_data.json is Missing
If the `ib_data.json` file is not present in the `data/` directory during the scheduled 6:00 AM SGT job run:
* **The Job Continues**: The daily metrics job will skip the cash balance database ingestion step cleanly without throwing errors or halting.
* **No Database Record Formed**: No new cash metrics record is created in the database for that day.
* **Pricing & Views Still Run**: The price sync, upcoming dividends update, and HTML cache pre-warming procedures will still execute normally.
* **Manual Workaround Available**: The user can still record the metrics manually for that day via the **Control Center -> Settings** panel in the GUI.

---

## 4. Manual / On-Demand Execution

If you need to trigger the end-of-day price update and dividend sync manually outside the automated cron schedule, you can call the following endpoint:

### `POST /api/prices/refresh`
* **Action**: Triggers a full Yahoo Finance price refresh (using the `force=true` query parameter) and initiates a dashboard rebuild task.
* **Request Header**: `Content-Type: application/json`
* **Example `curl` Request**:
  ```bash
  curl -X POST "http://localhost:8080/api/prices/refresh?force=true"
  ```
