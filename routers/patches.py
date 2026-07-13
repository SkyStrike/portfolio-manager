import os
import sys
import io
import json
import sqlite3
import traceback
import importlib.util
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
import re
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from core.database import DB_FILE

router = APIRouter(prefix="/api")

PATCHES_DIR = "patching"
DATA_DIR = os.path.dirname(DB_FILE) or "data"

class ExecutePatchRequest(BaseModel):
    patch_id: str = Field(..., pattern=r'^[a-zA-Z0-9_\-]+$')
    parameters: Dict[str, Any] = Field(default_factory=dict)

class BackupRequest(BaseModel):
    backup_name: str = Field(..., pattern=r'^[a-zA-Z0-9_\-]+\.db$')

class RestoreRequest(BaseModel):
    backup_name: str = Field(..., pattern=r'^[a-zA-Z0-9_\-]+\.db$')
    target_name: str = Field(default_factory=lambda: os.path.basename(DB_FILE), pattern=r'^[a-zA-Z0-9_\-]+\.db$')

def clean_filename(filename: str) -> str:
    """Removes path traversal attempts and returns a clean basename."""
    return os.path.basename(filename)

def trigger_cache_rebuild():
    """Background task helper to rebuild dashboard cache after restore."""
    try:
        from services.dashboard import rebuild_dashboard
        rebuild_dashboard()
    except Exception as e:
        print(f"Failed to automatically rebuild dashboard cache: {e}")

@router.get("/patches", response_model=List[Dict[str, Any]])
def list_patches():
    """Scans patching/ directory for patch manifests and metadata."""
    patches = []
    if not os.path.exists(PATCHES_DIR):
        return patches
        
    for item in sorted(os.listdir(PATCHES_DIR)):
        item_path = os.path.join(PATCHES_DIR, item)
        if os.path.isdir(item_path):
            manifest_path = os.path.join(item_path, "patch_manifest.json")
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "r") as f:
                        manifest = json.load(f)
                    # Force sync folder name and manifest id
                    manifest["id"] = item
                    patches.append(manifest)
                except Exception as e:
                    # Log error but don't crash
                    print(f"Error parsing manifest in {item_path}: {e}")
    return patches

@router.post("/patches/execute")
def execute_patch(req: ExecutePatchRequest):
    """Dynamically loads and runs the patch script patch(params) function, capturing stdout logs."""
    patch_id = clean_filename(req.patch_id)
    manifest_path = os.path.join(PATCHES_DIR, patch_id, "patch_manifest.json")
    
    if not os.path.exists(manifest_path):
        raise HTTPException(status_code=404, detail="Patch manifest not found.")
        
    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read manifest: {str(e)}")
        
    script_name = manifest.get("script")
    if not script_name or not re.match(r'^[a-zA-Z0-9_\-]+\.py$', script_name):
        raise HTTPException(status_code=400, detail="Manifest does not specify a valid python script file.")
        
    script_path = os.path.join(PATCHES_DIR, patch_id, script_name)
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail=f"Script file {script_name} not found.")

    # Redirect stdout and stderr to capture log output
    log_stream = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = log_stream
    sys.stderr = log_stream
    
    success = True
    try:
        # Load script dynamically as a python module
        module_name = f"patching_run_{patch_id}"
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        if hasattr(module, "patch"):
            # Call patch function with params dictionary
            module.patch(req.parameters)
        else:
            print("Error: The python script does not define a 'patch(params: dict)' function.")
            success = False
    except Exception as e:
        traceback.print_exc()
        success = False
    finally:
        # Restore normal stdout/stderr
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    logs = log_stream.getvalue()
    return {
        "success": success,
        "logs": logs
    }

@router.get("/database/backups", response_model=List[str])
def list_backups():
    """Lists available backup database files in the data directory."""
    backups = []
    if not os.path.exists(DATA_DIR):
        return backups
        
    active_filename = os.path.basename(DB_FILE)
    for filename in sorted(os.listdir(DATA_DIR)):
        if filename.endswith(".db") and filename != active_filename:
            backups.append(filename)
    return backups

@router.post("/database/backup")
def create_backup(req: BackupRequest):
    """Creates a hot-copy backup of the active SQLite database using sqlite3 page backup."""
    backup_name = clean_filename(req.backup_name)
    if not backup_name.endswith(".db"):
        raise HTTPException(status_code=400, detail="Backup filename must end with '.db'")
        
    active_name = os.path.basename(DB_FILE)
    if backup_name == active_name:
        raise HTTPException(status_code=400, detail="Backup name cannot match the active database filename.")
        
    os.makedirs(DATA_DIR, exist_ok=True)
    backup_path = os.path.join(DATA_DIR, backup_name)
    
    try:
        src_conn = sqlite3.connect(DB_FILE)
        dst_conn = sqlite3.connect(backup_path)
        with dst_conn:
            src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()
        return {"message": f"Successfully backed up active database to {backup_name}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")

@router.post("/database/restore")
def restore_backup(req: RestoreRequest, background_tasks: BackgroundTasks):
    """Safely restores a SQLite backup file over the target database (hot-swap)."""
    backup_name = clean_filename(req.backup_name)
    target_name = clean_filename(req.target_name)
    
    backup_path = os.path.join(DATA_DIR, backup_name)
    target_path = os.path.join(DATA_DIR, target_name)
    
    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail=f"Backup file {backup_name} not found.")
        
    if not target_name.endswith(".db"):
        raise HTTPException(status_code=400, detail="Target database filename must end with '.db'")
        
    try:
        src_conn = sqlite3.connect(backup_path)
        dst_conn = sqlite3.connect(target_path)
        with dst_conn:
            src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()
        
        # Trigger cache rebuild in background if restoring the active database
        if target_name == os.path.basename(DB_FILE):
            background_tasks.add_task(trigger_cache_rebuild)
            
        return {"message": f"Successfully restored {backup_name} database to {target_name}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")

@router.get("/database/download/{filename}")
def download_backup(filename: str):
    """Downloads a backup database file."""
    if not re.match(r'^[a-zA-Z0-9_\-]+\.db$', filename):
        raise HTTPException(status_code=400, detail="Invalid backup filename format.")
        
    clean_name = clean_filename(filename)
    backup_path = os.path.join(DATA_DIR, clean_name)
    
    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail="Backup file not found.")
        
    return FileResponse(
        path=backup_path,
        filename=clean_name,
        media_type="application/octet-stream"
    )

@router.delete("/database/delete/{filename}")
def delete_backup(filename: str):
    """Deletes a backup database file from disk."""
    if not re.match(r'^[a-zA-Z0-9_\-]+\.db$', filename):
        raise HTTPException(status_code=400, detail="Invalid backup filename format.")
        
    clean_name = clean_filename(filename)
    active_name = os.path.basename(DB_FILE)
    
    if clean_name == active_name:
        raise HTTPException(status_code=400, detail="Cannot delete the active database file.")
        
    backup_path = os.path.join(DATA_DIR, clean_name)
    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail="Backup file not found.")
        
    try:
        os.remove(backup_path)
        return {"message": f"Successfully deleted backup file {clean_name}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")
