"""Enterprise reports API endpoints."""

from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.exceptions import ok, APIError
from app.api.v1.deps import current_tenant
from app.services.report_engine import ReportQueryEngine, ReportDefinition
from app.services.export_service import ReportExporter, ExportManager, ExportFormat
from app.services.report_scheduler import ReportScheduler

router = APIRouter(prefix='/reports', tags=['Reports'])
export_manager = ExportManager()


REPORT_CATEGORIES = {
    "financial": ["profit_loss", "balance_sheet", "trial_balance", "general_ledger",
                  "receivables_aging", "payables_aging"],
    "gst": ["gst_summary", "hsn_summary"],
    "sales": ["sales_by_customer"],
}


@router.get('/')
def list_reports():
    """List all available reports grouped by category."""
    return ok({
        "categories": [
            {"id": "financial", "name": "Financial Reports", "reports": REPORT_CATEGORIES["financial"]},
            {"id": "gst", "name": "GST & Tax Reports", "reports": REPORT_CATEGORIES["gst"]},
            {"id": "sales", "name": "Sales Reports", "reports": REPORT_CATEGORIES["sales"]},
        ]
    })


@router.post('/run')
def run_report(
    report_type: str = Query(..., description="Report type identifier"),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    filters: str | None = Query(None, description="JSON filter object"),
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Run a report with filters and return results."""
    import json

    filter_dict = {}
    if filters:
        try:
            filter_dict = json.loads(filters)
        except json.JSONDecodeError:
            raise APIError('INVALID_FILTERS', 'Filters must be valid JSON', status_code=400)

    params = ReportDefinition(
        report_type=report_type,
        name=report_type,
        from_date=from_date,
        to_date=to_date,
        filters=filter_dict,
        page=page,
        page_size=page_size,
    )

    engine = ReportQueryEngine(db, tenant_id)
    result = engine.execute(params)
    return ok(result)


@router.post('/run/{report_type}')
def run_report_post(
    report_type: str,
    params: dict,
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Run a report with POST body for complex filters."""
    definition = ReportDefinition(
        report_type=report_type,
        name=params.get('name', report_type),
        from_date=params.get('from_date'),
        to_date=params.get('to_date'),
        filters=params.get('filters', {}),
        group_by=params.get('group_by', []),
        sort_by=params.get('sort_by', []),
        page=params.get('page', 1),
        page_size=params.get('page_size', 50),
    )

    engine = ReportQueryEngine(db, tenant_id)
    result = engine.execute(definition)
    return ok(result)


@router.get('/drill-down/{report_type}/{row_id}')
def drill_down(
    report_type: str,
    row_id: str,
    level: str = Query('details'),
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Drill down from a report row to underlying details."""
    engine = ReportQueryEngine(db, tenant_id)
    result = engine.drill_down(report_type, row_id, level)
    return ok(result)


@router.post('/export')
def export_report(
    payload: dict,
    tenant_id: str = Depends(current_tenant),
    db: Session = Depends(get_db),
):
    """Run a report and export to desired format."""
    report_type = payload.get('report_type', '')
    fmt = payload.get('format', ExportFormat.XLSX)

    if fmt not in (ExportFormat.XLSX, ExportFormat.CSV, ExportFormat.JSON):
        raise APIError('INVALID_FORMAT', f'Unsupported format: {fmt}', status_code=400)

    # Run the report first
    params = ReportDefinition(
        report_type=report_type,
        name=payload.get('name', report_type),
        from_date=payload.get('from_date'),
        to_date=payload.get('to_date'),
        filters=payload.get('filters', {}),
    )

    engine = ReportQueryEngine(db, tenant_id)
    result = engine.execute(params)

    # Export to file
    export_result = export_manager.create_export(result, result.get('report_name', report_type), fmt)
    return ok(export_result, f'Export generated: {export_result["filename"]}')


@router.get('/exports/{export_id}/download')
def download_export(export_id: str):
    """Download a generated export file."""
    import os
    from fastapi.responses import FileResponse

    for fname in os.listdir(export_manager.storage_path):
        if export_id in fname and fname.endswith(('.xlsx', '.csv', '.json')):
            filepath = os.path.join(export_manager.storage_path, fname)
            return FileResponse(filepath, filename=fname, media_type='application/octet-stream')

    raise APIError('EXPORT_NOT_FOUND', f'Export {export_id} not found or expired', status_code=404)


# ── Report Scheduling ─────────────────────────────────────────────

@router.post('/schedules')
def create_schedule(payload: dict, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Schedule a recurring report."""
    scheduler = ReportScheduler(db, tenant_id)
    result = scheduler.create_schedule(payload)
    return ok(result, 'Report scheduled successfully')


@router.get('/schedules')
def list_schedules(tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """List all scheduled reports."""
    scheduler = ReportScheduler(db, tenant_id)
    return ok(scheduler.list_schedules())


@router.delete('/schedules/{schedule_id}')
def delete_schedule(schedule_id: str, tenant_id: str = Depends(current_tenant), db: Session = Depends(get_db)):
    """Delete/disable a scheduled report."""
    scheduler = ReportScheduler(db, tenant_id)
    scheduler.delete_schedule(schedule_id)
    return ok(message='Schedule deleted')
