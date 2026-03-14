#!/usr/bin/env python3
"""
FastAPI server for Accessibility Auditor
Provides REST API and serves web frontend
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from pathlib import Path
import asyncio
import logging
from typing import Optional

from auditor import audit_website
from storage import AuditStorage
from report_generator import ReportGenerator

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize
app = FastAPI(title="Accessibility Auditor API")
storage = AuditStorage()
report_gen = ReportGenerator()

# Serve static files if they exist
web_dir = Path("web")
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


class AuditRequest(BaseModel):
    """Request model for audit endpoint"""
    url: str


class AuditResponse(BaseModel):
    """Response model for audit endpoint"""
    audit_id: str
    message: str


@app.post("/api/audit")
async def create_audit(request: AuditRequest, background_tasks: BackgroundTasks) -> AuditResponse:
    """
    Start a new accessibility audit
    Returns audit ID immediately (processing happens in background)
    """
    if not request.url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    # Normalize URL
    url = request.url
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # Run audit and save immediately (synchronous for web requests)
    try:
        report = await audit_website(url)
        audit_id = storage.save_audit(report)
        
        return AuditResponse(
            audit_id=audit_id,
            message=f"Audit completed. View results at /audits/{audit_id}"
        )
    except Exception as e:
        logger.error(f"Audit failed for {url}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")


@app.get("/audits/{audit_id}")
async def get_audit_html(audit_id: str) -> HTMLResponse:
    """
    Get audit report as beautiful HTML
    """
    report = storage.get_audit(audit_id)
    
    if not report:
        raise HTTPException(status_code=404, detail="Audit not found")
    
    html = report_gen.generate_html(report)
    return HTMLResponse(content=html)


@app.get("/")
async def serve_root() -> HTMLResponse:
    """
    Serve the main web interface
    """
    web_index = Path("web/index.html")
    
    if web_index.exists():
        return FileResponse(str(web_index), media_type="text/html")
    
    # Fallback if index.html doesn't exist yet
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Accessibility Auditor</title>
    </head>
    <body>
        <h1>Accessibility Auditor</h1>
        <p>Loading...</p>
    </body>
    </html>
    """)


@app.get("/api/audits")
async def list_audits(limit: int = 10):
    """
    List recent audits
    """
    return storage.list_audits(limit)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
