from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.common.deps import require_role
from app.auth.models import Role, Profile
from app.reports import service
from app.reports.excel_export import build_attendance_xlsx
from app.reports.pdf_export import build_attendance_pdf

router = APIRouter(prefix="/reports", tags=["reports"])

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/attendance.xlsx")
def attendance_excel(
    session_id: int,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_role(Role.lecturer, Role.admin)),
):
    session = service.get_session_for_report(db, session_id, user)
    rows = service.get_attendance_rows(db, session_id)
    content = build_attendance_xlsx(service.report_title(session), rows)
    return Response(
        content=content,
        media_type=XLSX_TYPE,
        headers={"Content-Disposition": f'attachment; filename="attendance_session_{session_id}.xlsx"'},
    )


@router.get("/attendance.pdf")
def attendance_pdf(
    session_id: int,
    db: Session = Depends(get_db),
    user: Profile = Depends(require_role(Role.lecturer, Role.admin)),
):
    session = service.get_session_for_report(db, session_id, user)
    rows = service.get_attendance_rows(db, session_id)
    content = build_attendance_pdf(service.report_title(session), rows)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="attendance_session_{session_id}.pdf"'},
    )