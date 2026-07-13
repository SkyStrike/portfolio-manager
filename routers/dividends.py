import logging
import os
import json
from datetime import datetime
from collections import defaultdict
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, UploadFile, File
from core.database import get_connection
from core.schemas import DividendCreate
from core.cache import rebuild_dashboard_sync, clear_dashboard_cache
from services.fetch_exchange_rates import get_historical_exchange_rate

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/dividends")
def list_dividends(portfolio_id: int | None = None):
    logger.info("GET /api/dividends (portfolio_id=%s)", portfolio_id)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT d.id, d.portfolio_id, d.ticker_id, d.date, d.amount, d.currency, d.tax, d.notes, d.qty,
                   tk.symbol, tk.friendly_name, p.name as portfolio_name
            FROM dividends d
            JOIN tickers tk ON d.ticker_id = tk.id
            JOIN portfolios p ON d.portfolio_id = p.id
        """
        params = []
        if portfolio_id is not None:
            query += " WHERE d.portfolio_id = ?"
            params.append(portfolio_id)
        query += " ORDER BY d.date DESC, d.id DESC"
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

@router.post("/api/dividends")
def create_dividend(div: DividendCreate):
    logger.info("POST /api/dividends - ticker=%s, date=%s, amount=%s", div.ticker, div.date, div.amount)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        symbol = div.ticker.strip().upper()
        cursor.execute("SELECT id, tax_rate FROM tickers WHERE symbol = ?", (symbol,))
        ticker_row = cursor.fetchone()
        if not ticker_row:
            raise HTTPException(status_code=404, detail="Ticker not found. Add the transaction first.")
        
        ticker_id = ticker_row['id']
        tax_rate = ticker_row['tax_rate']
        
        tax_amount = div.tax
        if tax_amount is None:
            tax_amount = div.amount * tax_rate
            
        clean_date = div.date.strip().split()[0].split('T')[0][:10] if div.date else ""
        get_historical_exchange_rate(clean_date, div.currency, conn)
        
        qty = div.qty
        if qty is None or qty <= 0:
            from core.calculations import get_shares_on_date
            qty = get_shares_on_date(div.portfolio_id, ticker_id, clean_date, conn)
        
        cursor.execute("""
            INSERT INTO dividends (portfolio_id, ticker_id, date, amount, currency, tax, notes, qty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (div.portfolio_id, ticker_id, clean_date, div.amount, div.currency, tax_amount, div.notes, qty))
        conn.commit()
        rebuild_dashboard_sync(conn)
        return {"status": "success", "id": cursor.lastrowid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()
 
@router.put("/api/dividends/{id}")
def update_dividend(id: int, div: DividendCreate):
    logger.info("PUT /api/dividends/%d - ticker=%s, date=%s, amount=%s", id, div.ticker, div.date, div.amount)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        symbol = div.ticker.strip().upper()
        cursor.execute("SELECT id FROM tickers WHERE symbol = ?", (symbol,))
        ticker_row = cursor.fetchone()
        if not ticker_row:
            raise HTTPException(status_code=404, detail="Ticker not found.")
        ticker_id = ticker_row['id']
        
        tax_amount = div.tax
        if tax_amount is None:
            cursor.execute("SELECT tax_rate FROM tickers WHERE id = ?", (ticker_id,))
            tax_amount = div.amount * cursor.fetchone()['tax_rate']
            
        clean_date = div.date.strip().split()[0].split('T')[0][:10] if div.date else ""
        get_historical_exchange_rate(clean_date, div.currency, conn)
        
        qty = div.qty
        if qty is None or qty <= 0:
            from core.calculations import get_shares_on_date
            qty = get_shares_on_date(div.portfolio_id, ticker_id, clean_date, conn)
        
        cursor.execute("""
            UPDATE dividends
            SET portfolio_id = ?, ticker_id = ?, date = ?, amount = ?, currency = ?, tax = ?, notes = ?, qty = ?
            WHERE id = ?
        """, (div.portfolio_id, ticker_id, clean_date, div.amount, div.currency, tax_amount, div.notes, qty, id))
        conn.commit()
        rebuild_dashboard_sync(conn)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.delete("/api/dividends/{id}")
def delete_dividend(id: int):
    logger.info("DELETE /api/dividends/%d", id)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM dividends WHERE id = ?", (id,))
        conn.commit()
        rebuild_dashboard_sync(conn)
        return {"status": "success"}
    finally:
        conn.close()

# IBKR Dividend Import
@router.post("/api/dividends/import-ibkr")
async def import_ibkr_dividends(
    request: Request,
    start_date: str,
    end_date: str,
    portfolio: str = "income factory",
    file: UploadFile = File(None),
):
    """
    Import IBKR dividend records from XML or JSON file upload (in-memory).
    """
    logger.info("POST /api/dividends/import-ibkr (start=%s, end=%s, portfolio=%s)", start_date, end_date, portfolio)
    def normalize_symbol(s: str) -> str:
        """Convert IBKR dot-notation tickers to hyphen (e.g. HYLD.U -> HYLD-U)."""
        return s.replace(".", "-").upper()

    records = None

    logger.info("File uploaded: %s", file is not None)

    # 1. Check if multipart file is uploaded
    if file is not None:
        try:
            file_bytes = await file.read()
            filename = file.filename.lower() if file.filename else ""
            
            # Check if it's XML
            if filename.endswith(".xml") or file_bytes.startswith(b"<?xml") or b"<CashTransactions" in file_bytes:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(file_bytes)
                cash_transactions = root.findall(".//CashTransaction")
                records = []
                for idx, ct in enumerate(cash_transactions):
                    attrib = dict(ct.attrib)
                    
                    # Validate required keys
                    required_keys = ["symbol", "currency", "settleDate", "amount", "type"]
                    for k in required_keys:
                        if k not in attrib:
                            raise ValueError(f"CashTransaction element at index {idx} is missing attribute '{k}'.")
                    
                    sd = attrib["settleDate"]
                    if not (isinstance(sd, str) and len(sd) == 8 and sd.isdigit()):
                        raise ValueError(f"CashTransaction element at index {idx} has invalid settleDate '{sd}' (expected YYYYMMDD).")
                    try:
                        float(attrib["amount"])
                    except ValueError:
                        raise ValueError(f"CashTransaction element at index {idx} has non-numeric amount: '{attrib['amount']}'.")
                    
                    records.append(attrib)
                logger.info("Direct XML upload parsed in-memory: %d CashTransaction records", len(records))
            else:
                # Assume JSON
                records = json.loads(file_bytes.decode("utf-8"))
                if not isinstance(records, list):
                    raise ValueError("JSON data must be an array of records.")
                logger.info("Direct JSON upload parsed in-memory: %d records", len(records))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse uploaded file: {str(e)}")

    # 3. Check if both are empty
    if records is None:
        raise HTTPException(
            status_code=400,
            detail="No source data provided. You must upload an XML/JSON file."
        )

    conn = get_connection()
    try:
        # 1. Resolve fallback portfolio_id
        fallback_row = conn.execute(
            "SELECT id FROM portfolios WHERE lower(name) = ?",
            (portfolio.lower().strip(),)
        ).fetchone()
        if not fallback_row:
            raise HTTPException(status_code=404, detail=f"Fallback portfolio '{portfolio}' not found.")
        fallback_portfolio_id = fallback_row["id"]

        # 2. Build symbol -> portfolio_id map from transactions in IBKR-broker portfolios.
        ibkr_tx_rows = conn.execute("""
            SELECT tk.symbol, t.portfolio_id
            FROM transactions t
            JOIN tickers tk ON t.ticker_id = tk.id
            JOIN portfolios p ON t.portfolio_id = p.id
            WHERE lower(p.broker) = 'ibkr'
            ORDER BY t.date DESC
        """).fetchall()

        symbol_to_portfolio: dict[str, int] = {}
        for row in ibkr_tx_rows:
            sym = row["symbol"]
            if sym not in symbol_to_portfolio:
                symbol_to_portfolio[sym] = row["portfolio_id"]

        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt   = datetime.strptime(end_date,   "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="start_date and end_date must be YYYY-MM-DD.")

        filtered = []
        for r in records:
            try:
                settle = datetime.strptime(r["settleDate"], "%Y%m%d").date()
            except (ValueError, KeyError):
                continue
            if start_dt <= settle <= end_dt:
                r["_settle_iso"] = settle.isoformat()
                r["_symbol_norm"] = normalize_symbol(r.get("symbol", ""))
                filtered.append(r)

        # 4. Consolidate by (normalised symbol, date, currency)
        groups = defaultdict(lambda: {"gross": 0.0, "tax": 0.0, "currency": ""})
        for r in filtered:
            key = (r["_symbol_norm"], r["_settle_iso"], r["currency"])
            t   = r.get("type", "")
            amt = float(r.get("amount", 0))
            if t in ("Dividends", "Payment In Lieu Of Dividends"):
                groups[key]["gross"] += amt
            elif t == "Withholding Tax":
                groups[key]["tax"] += amt
            groups[key]["currency"] = r["currency"]

        # 5. Upsert each consolidated record
        inserted = updated = skipped = 0
        errors = []

        for (symbol, date_iso, currency), vals in groups.items():
            gross = round(vals["gross"], 6)
            tax   = round(abs(vals["tax"]), 6)

            if gross == 0 and tax == 0:
                skipped += 1
                continue

            try:
                ticker_row = conn.execute(
                    "SELECT id FROM tickers WHERE symbol = ?", (symbol,)
                ).fetchone()
                if not ticker_row:
                    cur = conn.execute(
                        "INSERT INTO tickers (symbol, name, currency) VALUES (?, ?, ?)",
                        (symbol, symbol, currency)
                    )
                    ticker_id = cur.lastrowid
                    conn.commit()
                else:
                    ticker_id = ticker_row["id"]

                resolved_portfolio_id = symbol_to_portfolio.get(symbol, fallback_portfolio_id)

                existing = conn.execute(
                    "SELECT id, amount, tax FROM dividends "
                    "WHERE portfolio_id = ? AND ticker_id = ? AND date(date) = ?",
                    (resolved_portfolio_id, ticker_id, date_iso)
                ).fetchone()

                from core.calculations import get_shares_on_date
                qty = get_shares_on_date(resolved_portfolio_id, ticker_id, date_iso, conn)

                if not existing:
                    conn.execute(
                        "INSERT INTO dividends "
                        "(portfolio_id, ticker_id, date, amount, currency, tax, notes, qty) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (resolved_portfolio_id, ticker_id, date_iso, gross, currency, tax,
                         "Imported from IBKR", qty)
                    )
                    conn.commit()
                    inserted += 1
                elif round(existing["amount"], 6) == gross and round(existing["tax"], 6) == tax:
                    skipped += 1
                else:
                    conn.execute(
                        "UPDATE dividends SET amount = ?, tax = ?, currency = ?, notes = ?, qty = ? "
                        "WHERE id = ?",
                        (gross, tax, currency, "Imported from IBKR (updated)", qty, existing["id"])
                    )
                    conn.commit()
                    updated += 1

            except Exception as e:
                errors.append({"symbol": symbol, "date": date_iso, "error": str(e)})

        logger.info("IBKR dividend import complete: inserted=%d, updated=%d, skipped=%d, errors=%d",
                    inserted, updated, skipped, len(errors))
        
        if inserted > 0 or updated > 0:
            logger.info("Import success - clearing cache and rebuilding views...")
            from core.cache import clear_dashboard_cache
            from services.rebuild_dashboard import rebuild_all_views
            clear_dashboard_cache()
            rebuild_all_views(conn, price_mode="intraday")
            rebuild_all_views(conn, price_mode="closing")

        return {
            "status": "success",
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "range": {"start": start_date, "end": end_date},
            "fallback_portfolio": portfolio,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


def do_sync_and_rebuild(force: bool):
    logger.info("[do_sync_and_rebuild] Syncing upcoming dividends (force=%s)...", force)
    conn = get_connection()
    try:
        from services.dividend_service import sync_upcoming_dividends
        sync_upcoming_dividends(conn, force=force)
        # Clear memory cache
        logger.info("[do_sync_and_rebuild] Rebuilding dashboard (intraday + closing)...")
        clear_dashboard_cache()
        # Build views statically
        from services.rebuild_dashboard import rebuild_all_views
        rebuild_all_views(conn, price_mode="intraday")
        rebuild_all_views(conn, price_mode="closing")
        logger.info("[do_sync_and_rebuild] Done.")
    finally:
        conn.close()


@router.post("/api/dividends/sync-upcoming")
def sync_upcoming(background_tasks: BackgroundTasks, force: bool = False, sync: bool = False):
    logger.info("POST /api/dividends/sync-upcoming (force=%s, sync=%s)", force, sync)
    if sync:
        try:
            do_sync_and_rebuild(force=force)
            return {"status": "success", "message": "Dividends synced and dashboard rebuilt successfully."}
        except Exception as e:
            logger.error("Dividend sync failed: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
    else:
        logger.info("Dividend sync queued as background task.")
        background_tasks.add_task(do_sync_and_rebuild, force=force)
        return {"status": "success", "message": "Dividend sync task started in the background."}
