from __future__ import annotations

from datetime import date
from typing import List, Optional
from uuid import UUID

from sqlmodel import SQLModel


# ---------- Shared small DTOs ----------

class EnrollmentMiniOut(SQLModel):
    id: UUID
    attendance: Optional[int] = None
    late: Optional[int] = None
    absence: Optional[int] = None


class AttendanceInfoOut(SQLModel):
    id: UUID
    date_of_week: date
    class_name: Optional[str] = None
    attendance: bool = False
    absence: bool = False
    late: bool = False


# ---------- Students by Subject ----------

class StudentAttendanceOut(SQLModel):
    # internal UUID (keep it for backend/frontend logic)
    id: UUID

    # ✅ what you want to show in UI
    student_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    # already used in UI
    name: str
    telegram_id: Optional[str] = None
    phone: Optional[str] = None

    enrollments: List[EnrollmentMiniOut] = []


class SubjectMetaWithProfessorsOut(SQLModel):
    subject_id: UUID
    subject_name: str
    professors: List[str] = []


class StudentsBySubjectResponse(SQLModel):
    subject: SubjectMetaWithProfessorsOut
    students: List[StudentAttendanceOut] = []


# ---------- One Student by Enrollment ----------

class EnrollmentWithInfoOut(SQLModel):
    id: UUID
    attendance: Optional[int] = None
    late: Optional[int] = None
    absence: Optional[int] = None
    exact_info: List[AttendanceInfoOut] = []


class OneStudentEnrollmentOut(SQLModel):
    # internal UUID
    id: UUID

    # ✅ what you want to show in UI
    student_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    name: str
    telegram_id: Optional[str] = None
    phone: Optional[str] = None

    enrollments: List[EnrollmentWithInfoOut] = []


class SubjectMetaWithProfessorOut(SQLModel):
    subject_id: UUID
    subject_name: str
    professor_name: str


class OneStudentEnrollmentResponse(SQLModel):
    subject: SubjectMetaWithProfessorOut
    student: OneStudentEnrollmentOut