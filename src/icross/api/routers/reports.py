"""Local reports generation & management API (Phase 8)."""

import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse

from icross.core.storage.ozon_data import ReportStorage
from icross.services.task_queue import create_and_run_task

router = APIRouter(prefix="/reports", tags=["reports"])
_logger = logging.getLogger(__name__)


class GenerateReportRequest(BaseModel):
    shop_id: str = Field(..., min_length=1)
    report_type: str = Field(..., pattern=r"^(products|orders|finance|stocks|analytics)$")
    date_from: str = ""
    date_to: str = ""
    params: dict = Field(default_factory=dict)


# ── Generate ─────────────────────────────────────────────────────────────

@router.post("/generate")
async def generate_report(req: GenerateReportRequest):
    """Trigger async report generation via task queue."""
    store = ReportStorage()
    report = await store.create_report(
        shop_id=req.shop_id,
        report_type=req.report_type,
        params={"date_from": req.date_from, "date_to": req.date_to, **req.params},
    )
    report_id = report["id"]
    task_type = f"report_{req.report_type}"

    # Merge request params for the task handler
    task_params = {
        "shop_id": req.shop_id,
        "report_id": report_id,
        "date_from": req.date_from,
        "date_to": req.date_to,
        **req.params,
    }

    try:
        task = await create_and_run_task(task_type=task_type, params=task_params)
        return {"success": True, "report": report, "task": task}
    except Exception as e:
        _logger.exception(f"Failed to start report task: {e}")
        await store.update_report(report_id, status="failed", error=str(e))
        return {"success": False, "report": report, "error": str(e)}


# ── List ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_reports(
    shop_id: str | None = Query(default=None),
    report_type: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List generated reports."""
    store = ReportStorage()
    return await store.list_reports(
        shop_id=shop_id,
        report_type=report_type,
        limit=limit,
        offset=offset,
    )


# ── Get ──────────────────────────────────────────────────────────────────

@router.get("/{report_id}")
async def get_report(report_id: str):
    """Get report details and status."""
    store = ReportStorage()
    report = await store.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


# ── Download ─────────────────────────────────────────────────────────────

@router.get("/{report_id}/download")
async def download_report(report_id: str):
    """Download generated Excel report file."""
    store = ReportStorage()
    report = await store.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report["status"] != "completed" or not report.get("file_path"):
        raise HTTPException(status_code=400, detail="Report not ready yet")
    file_path = report["file_path"]
    filename = f"{report['type']}_{report_id}.xlsx"
    return FileResponse(file_path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ── Delete ───────────────────────────────────────────────────────────────

@router.delete("/{report_id}")
async def delete_report(report_id: str):
    """Delete a report record and its file."""
    store = ReportStorage()
    if await store.delete_report(report_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Report not found")
