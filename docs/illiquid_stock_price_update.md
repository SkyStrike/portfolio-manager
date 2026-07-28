# Illiquid Stock & Manual Price History Management

This guide documents how the system manages prices for illiquid stocks, non-trading calendar dates, missing bar data, and manual price history overrides.

---

## 1. Overview & Architecture

Most portfolio positions automatically sync daily OHLC bars and current prices via `yfinance`. However, certain illiquid stocks, suspended tickers, OTC assets, or newly listed securities may experience missing price bars or delayed market data.

To resolve missing data gaps without disabling automated market syncs, the system uses **Date-Level Manual Overrides** in `ticker_price_history`.

---

## 2. P&L Calculation Behavior

The system calculates Daily P&L using two distinct price modes:

### A. Intraday Mode (`price_mode = intraday`)
- **Current Price (`intraday_current`)**: Reflects live streaming/intraday quotes during market hours.
- **Previous Close (`intraday_prev_close`)**: Previous completed session close.
- **Holiday & Untraded Session Handling**: If the market is open on a stock's exchange but the stock has zero volume/trades for today, `intraday_prev_close` is set equal to `intraday_current`, preventing false P&L fluctuations.

### B. Closing Mode (`price_mode = closing`)
- **Closing Price (`daily_close`)**: The latest completed daily close (`series.iloc[-1]` when market is closed, or `series.iloc[-2]` when market session is currently in progress).
- **Previous Session Close (`daily_prev_close`)**: The preceding completed daily close (`series.iloc[-2]` when market is closed, or `series.iloc[-3]` when market session is in progress).
- **Dynamic Change Evaluation**: Daily P&L change % evaluates the actual price delta between consecutive historical trading dates (e.g., comparing Jul 27 close at 12.16 vs Jul 24 close at 12.19 = -0.25%).
- **Timezone Isolation**: Session evaluation is scoped strictly to each exchange's local timezone (SGX in SGT, NYSE/NASDAQ in EDT/EST, TSX in EDT/EST), preventing cross-exchange date mismatches.

---

## 3. Managing Price History Gaps via UI

Users can manage price history entries directly from the dashboard:

1. Click on the **Daily Change %** cell or open the **Price History & Gap-Fill Manager** for any holding.
2. The modal displays the **Price History Log** sorted by date descending, highlighting manual entries with a `[Manual]` tag.
3. **Quick Add / Override Price**:
   - Select the target date (e.g. `2026-07-24`).
   - Enter the closing price (e.g. `12.19`).
   - Click **Save Entry**. The entry is inserted into `ticker_price_history` with `is_manual = 1` and the dashboard view automatically updates.
4. **Delete Manual Override**:
   - Click the **Delete** button next to any manual row.
   - The manual entry is removed, restoring standard automated market sync for that date.

---

## 4. API Reference

### `GET /api/prices/history-log/{symbol}`
Retrieves historical price bars from `ticker_price_history` for the given symbol, including the `is_manual` flag and computed daily percentage changes.

### `POST /api/prices/manual-history`
Inserts or updates a manual price history bar for a specific date:
```json
{
  "symbol": "ADEA",
  "date": "2026-07-24",
  "price": 12.19
}
```

### `DELETE /api/prices/manual-history/{symbol}/{date}`
Deletes a manual entry for the given symbol and date from `ticker_price_history` and resynchronizes the ticker snapshot.

---

## 5. Maintenance & Patching

If historical prices need to be patched in bulk for an illiquid security, prepare a maintenance patch script under `patching/{4 digit running number}`:

```python
# patching/0002_patch_illiquid_prices.py

def patch(params: dict = None):
    from core.database import get_connection
    from routers.prices import _sync_ticker_prices_from_history
    
    conn = get_connection()
    cursor = conn.cursor()
    
    symbol = "ILLIQ"
    dates_and_prices = [
        ("2026-07-24", 12.19),
        ("2026-07-27", 12.16)
    ]
    
    for d_str, px in dates_and_prices:
        cursor.execute("""
            INSERT OR REPLACE INTO ticker_price_history 
            (symbol, date, interval, open, high, low, close, adj_close, is_manual)
            VALUES (?, ?, '1d', ?, ?, ?, ?, ?, 1)
        """, (symbol, d_str, px, px, px, px, px))
        
    cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
    row = cursor.fetchone()
    if row:
        _sync_ticker_prices_from_history(conn, symbol, row["id"])
        
    conn.commit()
    conn.close()
```
