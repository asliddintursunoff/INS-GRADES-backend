
from datetime import date
from pydantic import BaseModel
from typing import Optional,List
from uuid import UUID
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
    date_of_week: "date"
    class_name: Optional[str] = None
    attendance: bool
    absence: bool
    late: bool


class EnrollmentWithInfoOut(BaseModel):
    id: UUID
    attendance: Optional[int] = None
    late: Optional[int] = None
    absence: Optional[int] = None
    exact_info: List[AttendanceInfoOut]|None 


class OneStudentEnrollmentOut(BaseModel):
    id: UUID
    name: str
    telegram_id: Optional[str] = None
    phone: Optional[str] = None
    enrollments: List[EnrollmentWithInfoOut]

