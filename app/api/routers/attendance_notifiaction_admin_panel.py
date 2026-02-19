from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field


from app.api.dependencies import notification_session,current_super_user


# ---- Response / Request Schemas ----
class TotalAttendance(BaseModel):
    attendance: int = 0
    absence: int = 0
    late: int = 0


class AttendanceNotificationItem(BaseModel):
    enrollment_id: UUID
    student_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    group_name: Optional[str] = None
    major: str = ""
    st_year: Optional[str] = None
    total_attendance: TotalAttendance
    new_absence_date: Optional[date] = None   # <-- FIX
    subject_name: str
    prof_name: str
    attendance_info_id: Optional[UUID] = None


class MarkSeenBody(BaseModel):
    attendance_info_id: UUID = Field(...)


# ---- Router ----
router = APIRouter(prefix="/notifications/attendance", tags=["ADMIN PANEL - Attendance Notifications"])


@router.get(
    "",
    response_model=list[AttendanceNotificationItem],
    summary="List students attendance notification rows (ordered by total absence desc)",
)
async def list_attendance_notifications(
    service: notification_session,
    super_user_required:current_super_user,
    st_year_id: UUID | None = Query(default=None),
    absence_greater_than: int | None = Query(default=None, ge=0),
    major_id: UUID | None = Query(default=None),
):
    rows = await service.get_assignment_more_info(
        st_year_id=st_year_id,
        absence_greater_than=absence_greater_than,
        major_id=major_id,
    )
    return rows


@router.post(
    "/seen",
    status_code=status.HTTP_200_OK,
    summary="Mark one AttendanceInfo as seen",
)
async def mark_attendance_info_seen(
    super_user_required:current_super_user,
    body: MarkSeenBody,
    service: notification_session,
) -> dict[str, Any]:
    ok = await service.mark_attendance_info_seen(body.attendance_info_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="AttendanceInfo not found",
        )
    return {"ok": True, "attendance_info_id": str(body.attendance_info_id)}
