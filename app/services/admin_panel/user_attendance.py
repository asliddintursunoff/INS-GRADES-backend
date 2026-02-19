from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AttendanceInfo, Subject, Class, Enrollment, User
from app.api.schema.user_attendance import AttendanceInfoOut, EnrollmentMiniOut, EnrollmentWithInfoOut, OneStudentEnrollmentOut,StudentAttendanceOut

class UserAttendanceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_students_by_subject_id(self, subject_id: UUID) -> List[StudentAttendanceOut]:
        """
        Takes subject_id -> finds all classes of that subject -> returns all enrolled users
        ordered by absence DESC, late DESC (per enrollment row).
        """
        # Ensure subject exists
        subj_res = await self.session.execute(select(Subject.id).where(Subject.id == subject_id))
        if subj_res.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Subject not found")

        # Load enrollments joined with users and class, filter by subject_id
        # Order by absence desc, then late desc (NULL treated as 0)
        stmt = (
            select(Enrollment, User)
            .join(User, User.id == Enrollment.user_id)
            .join(Class, Class.id == Enrollment.class_id)
            .where(Class.subject_id == subject_id)
            .order_by(
                desc(func.coalesce(Enrollment.absence, 0)),
                desc(func.coalesce(Enrollment.late, 0)),
            )
        )

        res = await self.session.execute(stmt)
        rows = res.all()

        if not rows:
            return []

        # Group enrollments per user (user can appear in multiple classes of same subject)
        by_user: dict[UUID, StudentAttendanceOut] = {}

        for enrollment, user in rows:
            full_name = " ".join([p for p in [user.first_name, user.last_name] if p]).strip()
            if not full_name:
                full_name = user.student_id  # fallback

            if user.id not in by_user:
                by_user[user.id] = StudentAttendanceOut(
                    id=user.id,
                    name=full_name,
                    telegram_id=user.telegram_id,
                    phone=user.phone_number,
                    enrollments=[],
                )

            by_user[user.id].enrollments.append(
                EnrollmentMiniOut(
                    id=enrollment.id,
                    attendance=enrollment.attendance,
                    late=enrollment.late,
                    absence=enrollment.absence,
                )
            )

        # Keep the overall ordering as requested (based on the first enrollment encountered)
        # since rows are already ordered by absence/late desc.
        ordered_unique_users: List[StudentAttendanceOut] = []
        seen: set[UUID] = set()
        for enrollment, user in rows:
            if user.id not in seen:
                seen.add(user.id)
                ordered_unique_users.append(by_user[user.id])

        return ordered_unique_users


    
    async def get_one_user_by_enrollment_id(self, enrollment_id: UUID) -> OneStudentEnrollmentOut:
        """
        enrollment_id -> returns ONE user's info + that enrollment
        and includes exact_info (AttendanceInfo rows).
        """

        # 1) Load enrollment + user
        stmt = (
            select(Enrollment)
            .where(Enrollment.id == enrollment_id)
            .options(
                selectinload(Enrollment.user),
            )
        )
        enrollment = (await self.session.execute(stmt)).scalar_one_or_none()
        if enrollment is None:
            raise HTTPException(status_code=404, detail="Enrollment not found")

        user = enrollment.user
        if user is None:
            raise HTTPException(status_code=404, detail="User not found for this enrollment")

        # 2) Load AttendanceInfo rows safely (IMPORTANT: scalars())
        ai_stmt = (
            select(AttendanceInfo)
            .where(AttendanceInfo.enrollment_id == enrollment.id)
            .order_by(AttendanceInfo.date_of_week.asc(), AttendanceInfo.class_name.asc())
        )
        attendance_infos = (await self.session.execute(ai_stmt)).scalars().all()

        exact_info_out = [
            AttendanceInfoOut(
                id=ai.id,
                date_of_week=ai.date_of_week,
                class_name=ai.class_name,
                attendance=bool(ai.attendance),
                absence=bool(ai.absence),
                late=bool(ai.late),
            )
            for ai in attendance_infos
        ]

        # 3) Build response
        full_name = " ".join([p for p in [user.first_name, user.last_name] if p]).strip()
        if not full_name:
            full_name = user.student_id

        enrollment_out = EnrollmentWithInfoOut(
            id=enrollment.id,
            attendance=enrollment.attendance,
            late=enrollment.late,
            absence=enrollment.absence,
            exact_info=exact_info_out,
        )

        return OneStudentEnrollmentOut(
            id=user.id,
            name=full_name,
            telegram_id=user.telegram_id,
            phone=user.phone_number,
            enrollments=[enrollment_out],
        )