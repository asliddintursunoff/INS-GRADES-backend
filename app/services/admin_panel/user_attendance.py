from __future__ import annotations

from typing import Dict, List
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AttendanceInfo, Class, Enrollment, Professor, Subject, User
from app.api.schema.user_attendance import (
    AttendanceInfoOut,
    EnrollmentMiniOut,
    EnrollmentWithInfoOut,
    OneStudentEnrollmentOut,
    OneStudentEnrollmentResponse,
    StudentAttendanceOut,
    StudentsBySubjectResponse,
    SubjectMetaWithProfessorOut,
    SubjectMetaWithProfessorsOut,
)


class UserAttendanceService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_students_by_subject_id(self, subject_id: UUID) -> StudentsBySubjectResponse:
        # subject meta
        subj_row = (
            await self.session.execute(
                select(Subject.id, Subject.name).where(Subject.id == subject_id)
            )
        ).first()

        if subj_row is None:
            raise HTTPException(status_code=404, detail="Subject not found")

        subj_id, subj_name = subj_row

        # list of professors (unique) who teach this subject across classes
        prof_res = await self.session.execute(
            select(func.distinct(Professor.name))
            .select_from(Class)
            .join(Professor, Professor.id == Class.professor_id)
            .where(Class.subject_id == subject_id)
            .order_by(Professor.name.asc())
        )
        professors = prof_res.scalars().all()  # list[str]

        # enrollments ordered by absence desc, late desc
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
            return StudentsBySubjectResponse(
                subject=SubjectMetaWithProfessorsOut(
                    subject_id=subj_id,
                    subject_name=subj_name,
                    professors=professors,
                ),
                students=[],
            )

        by_user: Dict[UUID, StudentAttendanceOut] = {}

        for enrollment, user in rows:
            # UI display name: First Last OR student_id
            full_name = " ".join([p for p in [user.first_name, user.last_name] if p]).strip()
            if not full_name:
                full_name = user.student_id

            if user.id not in by_user:
                by_user[user.id] = StudentAttendanceOut(
                    id=user.id,
                    student_id=user.student_id,
                    first_name=user.first_name,
                    last_name=user.last_name,
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

        # keep order by first appearance (rows already sorted)
        ordered_unique_users: List[StudentAttendanceOut] = []
        seen: set[UUID] = set()
        for _, user in rows:
            if user.id not in seen:
                seen.add(user.id)
                ordered_unique_users.append(by_user[user.id])

        return StudentsBySubjectResponse(
            subject=SubjectMetaWithProfessorsOut(
                subject_id=subj_id,
                subject_name=subj_name,
                professors=professors,
            ),
            students=ordered_unique_users,
        )

    async def get_one_user_by_enrollment_id(self, enrollment_id: UUID) -> OneStudentEnrollmentResponse:
        # enrollment + user + class + subject + professor (single professor for this enrollment)
        stmt = (
            select(Enrollment, User, Class, Subject, Professor)
            .join(User, User.id == Enrollment.user_id)
            .join(Class, Class.id == Enrollment.class_id)
            .join(Subject, Subject.id == Class.subject_id)
            .join(Professor, Professor.id == Class.professor_id)
            .where(Enrollment.id == enrollment_id)
        )

        row = (await self.session.execute(stmt)).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Enrollment not found")

        enrollment, user, _klass, subject, professor = row

        # attendance info rows
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

        student_out = OneStudentEnrollmentOut(
            id=user.id,
            student_id=user.student_id,
            first_name=user.first_name,
            last_name=user.last_name,
            name=full_name,
            telegram_id=user.telegram_id,
            phone=user.phone_number,
            enrollments=[enrollment_out],
        )

        return OneStudentEnrollmentResponse(
            subject=SubjectMetaWithProfessorOut(
                subject_id=subject.id,
                subject_name=subject.name,
                professor_name=professor.name,
            ),
            student=student_out,
        )