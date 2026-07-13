import logging
import os
import json
import shutil
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from core.database import get_connection
from core.calculations import calculate_holdings
from core.cache import rebuild_dashboard_sync
from ingestion.importer import import_portfolio_data
from services.price_service import update_prices
from services.rebuild_dashboard import load_config, rebuild_all_views

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/api/import")
def upload_csvs(
    portfolio_name: str = Form(...),
    holdings_file: UploadFile = File(...),
    transactions_file: UploadFile = File(...)
):
    logger.info("POST /api/import - Importing portfolio '%s'", portfolio_name)
    # Ensure tmp directory exists
    os.makedirs("tmp", exist_ok=True)
    holdings_temp = f"tmp/holdings_{portfolio_name}.csv"
    transactions_temp = f"tmp/transactions_{portfolio_name}.csv"
    
    try:
        with open(holdings_temp, "wb") as buffer:
            shutil.copyfileobj(holdings_file.file, buffer)
            
        with open(transactions_temp, "wb") as buffer:
            shutil.copyfileobj(transactions_file.file, buffer)
            
        conn = get_connection()
        try:
            logger.info("Running importer for portfolio '%s'...", portfolio_name)
            tx_count, div_count = import_portfolio_data(
                portfolio_name, 
                holdings_temp, 
                transactions_temp, 
                conn
            )
            logger.info("Import complete: %d transactions, %d dividends. Updating prices and rebuilding...", tx_count, div_count)
            # Re-evaluate all cost bases for the imported portfolio
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM portfolios WHERE name = ?", (portfolio_name,))
            pid = cursor.fetchone()['id']
            calculate_holdings(pid, conn)
            # Batch update stock prices from Yahoo Finance
            update_prices(conn, force=True)
            conn.commit()
            rebuild_dashboard_sync(conn)
            logger.info("Portfolio '%s' imported and dashboard rebuilt successfully.", portfolio_name)
            return {
                "status": "success", 
                "message": f"Successfully imported portfolio '{portfolio_name}' with {tx_count} transactions and {div_count} dividends."
            }
        finally:
            conn.close()
            
    except Exception as e:
        logger.error("Import failed for portfolio '%s': %s", portfolio_name, e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")
    finally:
        # Cleanup temp files
        if os.path.exists(holdings_temp):
            os.remove(holdings_temp)
        if os.path.exists(transactions_temp):
            os.remove(transactions_temp)

@router.post("/api/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    document_type: str = Form(...),
    file: UploadFile = File(...)
):
    logger.info("POST /api/upload - document_type='%s', filename='%s'", document_type, file.filename)
    config = load_config()
    allowed_docs = config.get("allowed_documents", {
        "stock-options": "data/stock-options.json",
        "ib-data": "data/ib_data.json"
    })

    if document_type not in allowed_docs:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type '{document_type}'. Allowed types: {list(allowed_docs.keys())}"
        )

    # Read file content
    file_bytes = await file.read()

    # Process generic JSON/file uploads mapping to disk paths
    target_path = allowed_docs[document_type]

    # Integrity Validation
    if target_path.endswith(".json"):
        try:
            parsed_json = json.loads(file_bytes.decode("utf-8"))
            pass
        except ValueError as err:
            raise HTTPException(
                status_code=400,
                detail=f"Schema Validation Failed: {str(err)}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid JSON content: {str(e)}"
            )

    # Ensure parent directory exists
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    # Save the file
    try:
        with open(target_path, "wb") as f:
            f.write(file_bytes)
        logger.info("Saved '%s' to '%s' (%d bytes).", document_type, target_path, len(file_bytes))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write file to disk: {str(e)}"
        )

    # Trigger async rebuild
    ingest_cash = (document_type == "ib-data")
    logger.info("Queuing background dashboard rebuild (ingest_ibkr_cash=%s)...", ingest_cash)
    background_tasks.add_task(rebuild_all_views, ingest_ibkr_cash=ingest_cash)

    return {
        "status": "success",
        "message": f"Successfully uploaded '{document_type}' to '{target_path}'. Dashboard rebuild triggered."
    }
