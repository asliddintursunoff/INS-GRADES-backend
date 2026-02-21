from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AttendanceInfo,
    Class,
    Enrollment,
    Group,
    Major,
    Professor,
    StudentYear,
    Subject,
    User,
)


class NotificationAttendanceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_assignment_more_info(
        self,
        st_year_id: Optional[UUID] = None,
        absence_greater_than: Optional[int] = None,
        major_id: Optional[UUID] = None,
    ) -> list[dict[str, Any]]:
        # latest unseen "absence/late" AttendanceInfo per enrollment
        ai_ranked_sq = (
            select(
                AttendanceInfo.id.label("attendance_info_id"),
                AttendanceInfo.enrollment_id.label("enrollment_id"),
                AttendanceInfo.date_of_week.label("date_of_week"),
                AttendanceInfo.absence.label("ai_absence"),
                AttendanceInfo.late.label("ai_late"),
                AttendanceInfo.attendance.label("ai_attendance"),
                func.row_number()
                .over(
                    partition_by=AttendanceInfo.enrollment_id,
                    order_by=AttendanceInfo.date_of_week.desc(),
                )
                .label("rn"),
            )
            .where(
                AttendanceInfo.is_seen.is_(False),
                (AttendanceInfo.absence.is_(True) | AttendanceInfo.late.is_(True)),
            )
            .subquery()
        )

        ai_last_sq = (
            select(
                ai_ranked_sq.c.attendance_info_id,
                ai_ranked_sq.c.enrollment_id,
                ai_ranked_sq.c.date_of_week,
                ai_ranked_sq.c.ai_absence,
                ai_ranked_sq.c.ai_late,
                ai_ranked_sq.c.ai_attendance,
            )
            .where(ai_ranked_sq.c.rn == 1)
            .subquery()
        )

        total_attendance_obj = func.json_build_object(
            "attendance", func.coalesce(Enrollment.attendance, 0),
            "absence", func.coalesce(Enrollment.absence, 0),
            "late", func.coalesce(Enrollment.late, 0),
        ).label("total_attendance")

        stmt = (
            select(
                Enrollment.id.label("enrollment_id"),
                User.student_id.label("student_id"),
                User.first_name.label("first_name"),  # <-- added
                User.last_name.label("last_name"),
                Group.group_name.label("group_name"),
                Major.major_name.label("major"),
                StudentYear.year_name.label("st_year"),
                total_attendance_obj,
                ai_last_sq.c.date_of_week.label("new_absence_date"),
                Subject.name.label("subject_name"),
                Professor.name.label("prof_name"),
                ai_last_sq.c.attendance_info_id.label("attendance_info_id"),
            )
            .select_from(Enrollment)
            .join(ai_last_sq, ai_last_sq.c.enrollment_id == Enrollment.id)
            .join(User, User.id == Enrollment.user_id)
            .outerjoin(Group, Group.id == User.group_id)
            .outerjoin(Major, Major.id == Group.major_id)
            .join(Class, Class.id == Enrollment.class_id)
            .join(Subject, Subject.id == Class.subject_id)
            .outerjoin(StudentYear, StudentYear.id == Subject.student_year_id)
            .join(Professor, Professor.id == Class.professor_id)
        )

        where_clauses = []
        if st_year_id is not None:
            where_clauses.append(Subject.student_year_id == st_year_id)
        if absence_greater_than is not None:
            where_clauses.append(func.coalesce(Enrollment.absence, 0) > absence_greater_than)
        if major_id is not None:
            where_clauses.append(Group.major_id == major_id)

        if where_clauses:
            stmt = stmt.where(and_(*where_clauses))

        stmt = stmt.order_by(
            func.coalesce(Enrollment.absence, 0).desc(),
            func.coalesce(Enrollment.late, 0).desc(),
            User.student_id.asc(),
        )

        res = await self.session.execute(stmt)
        rows = res.mappings().all()

        return [
            {
                "enrollment_id": r["enrollment_id"],
                "student_id": r["student_id"],
                "first_name": r["first_name"],  # <-- added
                "last_name": r["last_name"],
                "group_name": r["group_name"],
                "major": r["major"],
                "st_year": r["st_year"],
                "total_attendance": r["total_attendance"],
                "new_absence_date": r["new_absence_date"],
                "subject_name": r["subject_name"],
                "prof_name": r["prof_name"],
                "attendance_info_id": r["attendance_info_id"],
            }
            for r in rows
        ]

    async def mark_attendance_info_seen(self, attendance_info_id: UUID) -> bool:
        """
        Marks:
          - the given AttendanceInfo as seen
          - AND all previous AttendanceInfo rows (same enrollment) as seen too.
        Returns True if attendance_info_id exists, else False.
        """

        # 1) Find the target row (need enrollment_id + date_of_week)
        stmt_get = select(
            AttendanceInfo.enrollment_id,
            AttendanceInfo.date_of_week,
        ).where(AttendanceInfo.id == attendance_info_id)

        row = (await self.session.execute(stmt_get)).first()
        if row is None:
            await self.session.rollback()
            return False

        enrollment_id, target_date = row

        # 2) Update this and all older ones for same enrollment
        stmt_upd = (
            update(AttendanceInfo)
            .where(
                AttendanceInfo.enrollment_id == enrollment_id,
                AttendanceInfo.date_of_week <= target_date,
                AttendanceInfo.is_seen.is_(False),
            )
            .values(is_seen=True)
        )

        await self.session.execute(stmt_upd)
        await self.session.commit()
        return True
