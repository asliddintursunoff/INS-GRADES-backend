# app/api/schema/user_attendance.py

from __future__ import annotations

from datetime import date
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class EnrollmentMiniOut(BaseModel):
    id: UUID
    attendance: Optional[int] = None
    late: Optional[int] = None
    absence: Optional[int] = None


class StudentAttendanceOut(BaseModel):
    id: UUID
    name: str
    telegram_id: Optional[str] = None
    phone: Optional[str] = None
    enrollments: List[EnrollmentMiniOut]


class AttendanceInfoOut(BaseModel):
    id: UUID
    date_of_week: date
    class_name: Optional[str] = None
    attendance: bool
    absence: bool
    late: bool


class EnrollmentWithInfoOut(BaseModel):
    id: UUID
    attendance: Optional[int] = None
    late: Optional[int] = None
    absence: Optional[int] = None
    exact_info: Optional[List[AttendanceInfoOut]] = None


class OneStudentEnrollmentOut(BaseModel):
    id: UUID
    name: str
    telegram_id: Optional[str] = None
    phone: Optional[str] = None
    enrollments: List[EnrollmentWithInfoOut]


class SubjectMetaOut(BaseModel):
    subject_id: UUID
    subject_name: str


class SubjectMetaWithProfessorsOut(SubjectMetaOut):
    professors: List[str] = []


class SubjectMetaWithProfessorOut(SubjectMetaOut):
    professor_name: str


class StudentsBySubjectResponse(BaseModel):
    subject: SubjectMetaWithProfessorsOut
    students: List[StudentAttendanceOut]


class OneStudentEnrollmentResponse(BaseModel):
    subject: SubjectMetaWithProfessorOut
    student: OneStudentEnrollmentOut
