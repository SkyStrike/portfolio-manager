import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Body
import json
from typing import Any
from core.database import get_connection
from core.cache import rebuild_dashboard_sync
from core.schemas import (
    CashMetricCreate, 
    CashMetricItem, 
    CashMetricLastItem, 
    StatusResponse,
    CapitalEntryCreate,
    CapitalEntryItem,
    CashMetricsUploadPayload
)
from services.rebuild_dashboard import load_config, rebuild_all_views

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get(
    "/api/settings",
    response_model=dict[str, Any],
    summary="Get application settings",
    description="Returns current configuration settings loaded from config.json and merged database overrides.",
    tags=["Settings & Capital"]
)
def get_settings():
    logger.info("GET /api/settings")
    try:
        return load_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/api/settings",
    response_model=StatusResponse,
    summary="Update application settings",
    description="Updates key-value or dot-notated configuration settings in the database and triggers dashboard cache rebuild.",
    tags=["Settings & Capital"]
)
def update_settings(
    settings: dict[str, Any] = Body(
        ...,
        description="Key-value or dot-notated configuration settings dictionary to persist",
        openapi_examples={
            "default": {
                "summary": "Standard settings overrides",
                "value": {
                    "sorting.classification_priority": ["Core ETF", "Growth", "Income"],
                    "external_services.options_tracker_url": "http://yui.home/options-tracker/",
                    "cron.metrics_run_hour": 6
                }
            }
        }
    )
):
    logger.info("POST /api/settings - keys=%s", list(settings.keys()))
    conn = get_connection()
    try:
        cursor = conn.cursor()
        with conn:
            for key, val in settings.items():
                val_json = json.dumps(val)
                cursor.execute("""
                    INSERT INTO settings (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """, (key, val_json))
        rebuild_dashboard_sync(conn)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

# Broker Capital Entries API
@router.get(
    "/api/settings/capital",
    response_model=list[CapitalEntryItem],
    summary="Get all broker capital entries",
    description="Returns the history of recorded capital deposit and withdrawal entries across all brokers.",
    tags=["Settings & Capital"]
)
def get_capital_entries():
    logger.info("GET /api/settings/capital")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, broker, amount, remarks FROM broker_capital_entries ORDER BY date DESC, id DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post(
    "/api/settings/capital",
    response_model=StatusResponse,
    summary="Add broker capital entry",
    description="Records a new capital deposit (positive) or withdrawal (negative) for a broker and updates base capital.",
    tags=["Settings & Capital"]
)
def add_capital_entry(entry: CapitalEntryCreate):
    date = entry.date
    broker = entry.broker
    amount_val = entry.amount
    remarks = entry.remarks or ""
    logger.info("POST /api/settings/capital - broker=%s, date=%s, amount=%s", broker, date, amount_val)
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        with conn:
            cursor.execute("""
                INSERT INTO broker_capital_entries (date, broker, amount, remarks)
                VALUES (?, ?, ?, ?)
            """, (date, broker.strip().upper(), amount_val, remarks))
        rebuild_dashboard_sync(conn)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.delete(
    "/api/settings/capital/{entry_id}",
    response_model=StatusResponse,
    summary="Delete broker capital entry",
    description="Deletes a capital deposit or withdrawal record by ID.",
    tags=["Settings & Capital"]
)
def delete_capital_entry(entry_id: int):
    logger.info("DELETE /api/settings/capital/%d", entry_id)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        with conn:
            cursor.execute("DELETE FROM broker_capital_entries WHERE id = ?", (entry_id,))
        rebuild_dashboard_sync(conn)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.post("/api/settings/capital/import")
async def import_capital_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):
    logger.info("POST /api/settings/capital/import - filename='%s'", file.filename)
    try:
        file_bytes = await file.read()
        import csv
        from datetime import datetime
        
        lines = file_bytes.decode("utf-8").splitlines()
        reader = csv.reader(lines)
        header = next(reader, None)
        if not header or len(header) < 4:
            raise ValueError("CSV must have at least 4 columns (Broker, Date, Remarks, Amount)")

        entries = []
        for idx, row in enumerate(reader):
            if not row or len(row) < 4:
                continue
            broker = row[0].strip()
            raw_date = row[1].strip()
            remarks = row[2].strip()
            raw_amount = row[3].strip().replace(",", "")

            try:
                amount = float(raw_amount)
            except ValueError:
                logger.warning("broker-capital-csv upload: Line %d has invalid amount: %s", idx + 2, raw_amount)
                continue

            months_map = {
                "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"
            }

            date_str = None
            import re
            m = re.match(r"(\d{4})-(\w{3})\s+(\d{1,2})", raw_date)
            if m:
                year, mon_name, day = m.groups()
                mon = months_map.get(mon_name)
                if mon:
                    date_str = f"{year}-{mon}-{int(day):02d}"
            else:
                try:
                    parsed_dt = datetime.strptime(raw_date, "%Y-%m-%d")
                    date_str = parsed_dt.strftime("%Y-%m-%d")
                except:
                    pass

            if date_str and broker:
                entries.append((date_str, broker.upper(), amount, remarks))

        if entries:
            conn = get_connection()
            try:
                with conn:
                    conn.execute("DELETE FROM broker_capital_entries")
                    conn.executemany("""
                        INSERT OR IGNORE INTO broker_capital_entries (date, broker, amount, remarks)
                        VALUES (?, ?, ?, ?)
                    """, entries)
                logger.info("Successfully seeded %d broker capital entries in-memory.", len(entries))
            finally:
                conn.close()
        else:
            raise ValueError("No valid capital records found in CSV.")
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to process capital CSV in memory: {str(e)}"
        )

    # Trigger async rebuild
    background_tasks.add_task(rebuild_all_views, ingest_ibkr_cash=False)
    return {
        "status": "success",
        "message": "Successfully processed broker capital CSV in-memory. Dashboard rebuild triggered."
    }


# Daily Cash Metrics API
@router.get(
    "/api/settings/cash-metrics/history",
    response_model=list[CashMetricItem],
    summary="Get daily cash metrics history",
    description="Returns up to the last 180 recorded daily cash & liquidation metric snapshots across all brokers.",
    tags=["Settings & Capital"]
)
def get_cash_metrics_history():
    logger.info("GET /api/settings/cash-metrics/history")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, broker, liquidation_value, base_capital, total_stock_value, cash_on_hand
            FROM daily_cash_report
            ORDER BY date DESC, broker ASC
            LIMIT 180
        """)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get(
    "/api/settings/cash-metrics/last",
    response_model=CashMetricLastItem,
    summary="Get last recorded cash metric for broker",
    description="Returns the most recent daily cash and liquidation snapshot for a specific broker.",
    tags=["Settings & Capital"]
)
def get_last_cash_metric(broker: str):
    logger.info("GET /api/settings/cash-metrics/last (broker=%s)", broker)
    if not broker:
        raise HTTPException(status_code=400, detail="broker query parameter is required.")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT liquidation_value, total_stock_value, cash_on_hand, date
            FROM daily_cash_report
            WHERE broker = ?
            ORDER BY date DESC
            LIMIT 1
        """, (broker.strip().upper(),))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {"liquidation_value": 0.0, "total_stock_value": 0.0, "cash_on_hand": 0.0, "date": ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post(
    "/api/settings/cash-metrics",
    response_model=StatusResponse,
    summary="Record or update daily cash & liquidation metrics",
    description=(
        "Saves daily broker liquidity metrics (liquidation value, total stock value, and cash on hand in SGD). "
        "Calculates cumulative base capital automatically and updates the daily cash report via UPSERT."
    ),
    tags=["Settings & Capital"]
)
def save_cash_metric(metric: CashMetricCreate):
    date = metric.date
    broker = metric.broker
    liq_val = metric.liquidation_value
    stock_val = metric.total_stock_value
    cash_val = metric.cash_on_hand
    logger.info("POST /api/settings/cash-metrics - broker=%s, date=%s, liq_val=%s", broker, date, liq_val)
    
    from datetime import datetime, timezone, timedelta
    from zoneinfo import ZoneInfo
    from services.rebuild_dashboard import calculate_trading_date
    
    try:
        ny_tz = ZoneInfo("America/New_York")
    except Exception:
        ny_tz = timezone(timedelta(hours=-4))
        
    ny_now = datetime.now(timezone.utc).astimezone(ny_tz)
    today_ny = ny_now.strftime('%Y-%m-%d')
    
    if date >= today_ny:
        date = calculate_trading_date()
        logger.info("save_cash_metric: date adjusted to last trading day -> %s", date)
        
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Query base capital cumulative sum up to date for this broker
        cursor.execute("""
            SELECT SUM(amount) FROM broker_capital_entries 
            WHERE broker = ? AND date <= ?
        """, (broker.strip().upper(), date))
        base_capital = cursor.fetchone()[0] or 0.0
        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        
        with conn:
            cursor.execute("""
                INSERT INTO daily_cash_report (date, broker, liquidation_value, base_capital, total_stock_value, cash_on_hand, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, broker) DO UPDATE SET
                    liquidation_value=excluded.liquidation_value,
                    base_capital=excluded.base_capital,
                    total_stock_value=excluded.total_stock_value,
                    cash_on_hand=excluded.cash_on_hand,
                    updated_at=excluded.updated_at
            """, (date, broker.strip().upper(), liq_val, base_capital, stock_val, cash_val, updated_at))
            
        rebuild_dashboard_sync(conn)
        logger.info("Cash metric saved: broker=%s, date=%s, liq_val=%.2f", broker, date, liq_val)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.post(
    "/api/settings/cash-metrics/upload",
    response_model=StatusResponse,
    summary="Upload cash & position metrics for a broker",
    description="Accepts broker liquidity balances (standard or IBKR payload format) and updates the daily cash report for the current trading date.",
    tags=["Settings & Capital"]
)
def upload_cash_metrics(payload: CashMetricsUploadPayload, broker: str):
    logger.info("POST /api/settings/cash-metrics/upload (broker=%s)", broker)
    if not broker:
        raise HTTPException(status_code=400, detail="broker query parameter is required.")
        
    broker_name = broker.strip().upper()
    
    # Support flat or nested under "balances", standard or legacy IBKR keys
    balances = payload.balances if payload.balances is not None else payload.model_dump()
    
    liq_val = balances.get("liquidation_value")
    if liq_val is None:
        liq_val = balances.get("NetLiquidation")
        
    stock_val = balances.get("total_stock_value")
    if stock_val is None:
        stock_val = balances.get("GrossPositionValue")
        
    cash_val = balances.get("cash_on_hand")
    if cash_val is None:
        cash_val = balances.get("TotalCashValue")
        
    if liq_val is None or stock_val is None or cash_val is None:
        raise HTTPException(
            status_code=400, 
            detail="Could not find liquidation_value (NetLiquidation), total_stock_value (GrossPositionValue), and cash_on_hand (TotalCashValue) in the payload."
        )
        
    try:
        liq_val = float(liq_val)
        stock_val = float(stock_val)
        cash_val = float(cash_val)
    except ValueError:
        raise HTTPException(status_code=400, detail="Balances must be numeric.")
        
    from datetime import datetime, timezone
    from services.rebuild_dashboard import calculate_trading_date
    date = calculate_trading_date()
    logger.info("upload_cash_metrics: resolved trading date=%s, broker=%s, liq_val=%.2f", date, broker_name, liq_val)
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Query base capital cumulative sum up to date for this broker
        cursor.execute("""
            SELECT SUM(amount) FROM broker_capital_entries 
            WHERE broker = ? AND date <= ?
        """, (broker_name, date))
        base_capital = cursor.fetchone()[0] or 0.0
        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        
        with conn:
            cursor.execute("""
                INSERT INTO daily_cash_report (date, broker, liquidation_value, base_capital, total_stock_value, cash_on_hand, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, broker) DO UPDATE SET
                    liquidation_value=excluded.liquidation_value,
                    base_capital=excluded.base_capital,
                    total_stock_value=excluded.total_stock_value,
                    cash_on_hand=excluded.cash_on_hand,
                    updated_at=excluded.updated_at
            """, (date, broker_name, liq_val, base_capital, stock_val, cash_val, updated_at))
            
        rebuild_dashboard_sync(conn)
        logger.info("Cash metrics uploaded: broker=%s, date=%s, liq_val=%.2f", broker_name, date, liq_val)
        return {"status": "success", "date": date}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.post("/api/settings/cash-metrics/ingest-file")
def ingest_cash_metrics_from_file_endpoint(rebuild: bool = False):
    logger.info("POST /api/settings/cash-metrics/ingest-file - rebuild=%s", rebuild)
    conn = get_connection()
    try:
        from services.rebuild_dashboard import ingest_ibkr_cash_from_file
        success = ingest_ibkr_cash_from_file(conn)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to ingest cash metrics from file (file may not exist or balances missing).")
        
        if rebuild:
            logger.info("Triggering rebuild as requested after cash ingestion.")
            rebuild_dashboard_sync(conn)
            
        return {"status": "success"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
