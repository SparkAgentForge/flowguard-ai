from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from flowguard_api.core.storage import FileStorage
from flowguard_api.infrastructure.database import get_session
from flowguard_api.infrastructure.storage.factory import get_file_storage
from flowguard_api.models import Report, WorkOrder
from flowguard_api.schemas import ReportRead, ReportSummary
from flowguard_api.services.reporting import ReportNotReady, get_or_create_report

router = APIRouter(prefix="/reports", tags=["reports"])
SessionDependency = Annotated[Session, Depends(get_session)]
StorageDependency = Annotated[FileStorage, Depends(get_file_storage)]


def _report_read(session: Session, report: Report) -> ReportRead:
    work_order = session.get(WorkOrder, report.work_order_id)
    if work_order is None:
        raise HTTPException(status_code=409, detail="报告关联工作单不存在")
    return ReportRead.model_validate({**report.__dict__, "work_order_code": work_order.code})


@router.get("", response_model=list[ReportSummary])
def list_reports(session: SessionDependency) -> list[ReportSummary]:
    reports = session.scalars(select(Report).order_by(Report.archived_at.desc())).all()
    result = []
    for report in reports:
        work_order = session.get(WorkOrder, report.work_order_id)
        if work_order is None:
            continue
        result.append(
            ReportSummary.model_validate(
                {
                    **report.__dict__,
                    "work_order_code": work_order.code,
                    "product_code": work_order.product_code,
                    "work_order_status": work_order.status,
                    "outcome": report.content["outcome"],
                }
            )
        )
    return result


@router.get("/{work_order_id}", response_model=ReportRead)
def read_report(
    work_order_id: str,
    session: SessionDependency,
    storage: StorageDependency,
) -> ReportRead:
    work_order = session.get(WorkOrder, work_order_id)
    if work_order is None:
        raise HTTPException(status_code=404, detail="工作单不存在")
    try:
        report = get_or_create_report(session, storage, work_order)
    except ReportNotReady as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _report_read(session, report)


@router.get("/{work_order_id}/pdf")
def download_report_pdf(
    work_order_id: str,
    session: SessionDependency,
    storage: StorageDependency,
) -> Response:
    work_order = session.get(WorkOrder, work_order_id)
    if work_order is None:
        raise HTTPException(status_code=404, detail="工作单不存在")
    try:
        report = get_or_create_report(session, storage, work_order)
    except ReportNotReady as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return Response(
        content=storage.get(report.pdf_storage_key),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="flowguard-{work_order.code}-v{report.version}.pdf"'
            ),
            "ETag": report.pdf_sha256,
        },
    )
