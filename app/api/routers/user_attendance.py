from typing import List
from uuid import UUID

from fastapi import APIRouter
from app.api.dependencies import user_attendance_session ,current_super_user# <- use your real dependency
from app.api.schema.user_attendance import OneStudentEnrollmentOut, OneStudentEnrollmentResponse, StudentAttendanceOut, StudentsBySubjectResponse



router = APIRouter(prefix="/attendance", tags=["ADMIN PANEL"])


@router.get(
    "/students-by-subject/{subject_id}",
    response_model=StudentsBySubjectResponse,
)
async def students_by_subject(
    subject_id: UUID,
    session: user_attendance_session,
    super_user: current_super_user,
):
    return await session.get_students_by_subject_id(subject_id)


@router.get(
    "/student-by-enrollment/{enrollment_id}",
    response_model=OneStudentEnrollmentResponse,
)
async def student_by_enrollment(
    enrollment_id: UUID,
    service: user_attendance_session,
    super_user: current_super_user,
):
    return await service.get_one_user_by_enrollment_id(enrollment_id)
