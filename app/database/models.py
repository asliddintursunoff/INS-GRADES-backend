from sqlmodel import Boolean, ForeignKey, SQLModel, Field, Column, Relationship
from sqlalchemy.dialects import postgresql
from sqlalchemy import UniqueConstraint

from datetime import datetime, time,date
from uuid import UUID, uuid4
from enum import Enum
from typing import List, Optional

class Weeks(str, Enum):
    monday = "monday"
    tuesday = "tuesday"
    wednesday = "wednesday"
    thursday = "thursday"
    friday = "friday"
    saturday = "saturday"
    sunday = "sunday"


class StudentYear(SQLModel,table = True):
    id:UUID = Field(
        sa_column=Column(
            postgresql.UUID,
            primary_key=True,
            default = uuid4
        )
    )
    year_name:str
    starting_year:int
    graduation_year:int

    subjects:List["Subject"] = Relationship(back_populates="student_year",sa_relationship_kwargs={"lazy": "selectin"},)


class SubjectMajorLink(SQLModel,table= True):
    id:UUID =  Field(
        sa_column=Column(
            postgresql.UUID,
            primary_key=True,
            default = uuid4
        )
    )
    major_id: UUID | None = Field(
        default=None,
        foreign_key="major.id",
        nullable=True,
    )
    subject_id: UUID | None = Field(
        default=None,
        foreign_key="subject.id",
        nullable=True,
    )

class Major(SQLModel,table=True):
    id:UUID =  Field(
        sa_column=Column(
            postgresql.UUID,
            primary_key=True,
            default = uuid4
        )
    )
    major_name:str
    major_full_name:str|None = None
    subjects:List['Subject'] = Relationship(back_populates="majors",
                                            link_model=SubjectMajorLink,
                                            sa_relationship_kwargs={"lazy": "selectin"},)
    groups:List["Group"] = Relationship(back_populates="major",sa_relationship_kwargs={"lazy":"selectin"})


class Subject(SQLModel, table=True):
    id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            default=uuid4,
            primary_key=True,
        ),
    )
    short_name: str
    name: str = Field(unique=True)

    student_year_id:UUID = Field(foreign_key='studentyear.id',nullable=True)


    classes: List["Class"] = Relationship(back_populates="subject",
                                            sa_relationship_kwargs={"lazy": "selectin"},)

    majors:List["Major"] = Relationship(back_populates='subjects',
                                        link_model=SubjectMajorLink,
                                        sa_relationship_kwargs={"lazy": "selectin"},)
    
    student_year : StudentYear= Relationship(back_populates="subjects",
                                             sa_relationship_kwargs={"lazy": "selectin"},)



class Professor(SQLModel, table=True):
    id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            default=uuid4,
            primary_key=True,
        ),
    )
    name: str = Field(unique=True)
    office_hours: str | None = Field(default=None)
    classes: List["Class"] = Relationship(back_populates="professor")


class Group(SQLModel, table=True):
    id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            default=uuid4,
            primary_key=True,
        ),
    )
    group_name: str = Field(unique=True, index=True)

    major_id:UUID = Field(foreign_key="major.id",nullable=True)

    major:Major = Relationship(back_populates="groups",sa_relationship_kwargs={"lazy":"selectin"})

    classes: List["Class"] = Relationship(back_populates="group")
    users: List["User"] = Relationship(back_populates="group")


class Enrollment(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", "class_id", name="uq_enrollment_user_class"),
    )

    id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            default=uuid4,
            primary_key=True,
        ),
    )

    user_id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    class_id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("class.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )

    absence: int | None = Field(default=None)
    attendance: int | None = Field(default=None)
    late: int | None = Field(default=None)

    assignments: List["Assignment"] = Relationship(back_populates="enrollment")
    quizzes: List["Quiz"] = Relationship(back_populates="enrollment")

    user: Optional["User"] = Relationship(
        back_populates="enrollments",
        sa_relationship_kwargs={"overlaps": "classes,users"},
    )
    klass: Optional["Class"] = Relationship(
        back_populates="enrollments",
        sa_relationship_kwargs={"overlaps": "classes,users"},
    )

    attendanceinfos:Optional["AttendanceInfo"] = Relationship(back_populates="enrollment",sa_relationship_kwargs={"lazy": "selectin"},)

class AttendanceInfo(SQLModel,table=True):
    id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            default=uuid4,
            primary_key=True,
        ),
    )
    date_of_week:date
    class_name:str = None
    attendance:bool = False
    absence :bool = False
    late:bool = False
    is_seen:bool = False

    enrollment_id:UUID = Field(foreign_key="enrollment.id")
    enrollment:Enrollment = Relationship(back_populates="attendanceinfos",sa_relationship_kwargs={"lazy": "selectin"},)

class Class(SQLModel, table=True):
    id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            default=uuid4,
            primary_key=True,
        ),
    )

    __table_args__ = (
        UniqueConstraint("group_id", "subject_id", name="uq_class_group_subject_prof"),
    )

    group_id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("group.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    group: Optional[Group] = Relationship(back_populates="classes",
                                            sa_relationship_kwargs={"lazy": "selectin"},)

    subject_id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("subject.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    subject: Optional["Subject"] = Relationship(back_populates="classes",
                                                  sa_relationship_kwargs={"lazy": "selectin"},)

    professor_id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("professor.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    professor: Optional["Professor"] = Relationship(back_populates="classes",
                                                      sa_relationship_kwargs={"lazy": "selectin"},)

    enrollments: List["Enrollment"] = Relationship(
        back_populates="klass",
        sa_relationship_kwargs={"overlaps": "users,classes"},
    )

    users: List["User"] = Relationship(
        back_populates="classes",
        link_model=Enrollment,
        sa_relationship_kwargs={"overlaps": "enrollments,klass,user"},
    )

    classtimes: List["ClassTime"] = Relationship(back_populates="klass",
                                                   sa_relationship_kwargs={"lazy": "selectin"},)


class ClassTime(SQLModel, table=True):
    id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            default=uuid4,
            primary_key=True,
        ),
    )

    class_id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("class.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    klass: Class = Relationship(back_populates="classtimes",sa_relationship_kwargs={"lazy": "selectin"},)

    room: str | None = None
    week_day: Optional[Weeks | None] = None
    start_time: time | None = None
    end_time: time | None = None


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            default=uuid4,
            primary_key=True,
        )
    )

    phone_number:str|None = None
    telegram_id: str | None = Field(unique=True, index=True, default=None)
    student_id: str
    first_name: str | None = Field(max_length=50)
    last_name: str | None = Field(max_length=50)
    password: str | None

    is_subscribed: bool = Field(default=False)
    subscribtion_started: datetime | None = None
    subscribtion_end: datetime | None = None
    is_started: bool = False
    started_date: datetime | None = None
    eclass_registered: datetime |None = None

    enrollments: List["Enrollment"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"overlaps": "classes,users","lazy": "selectin"},
    )

    classes: List["Class"] = Relationship(
        back_populates="users",
        link_model=Enrollment,
        sa_relationship_kwargs={"overlaps": "enrollments,klass,user","lazy": "selectin"},
    )

    group_id: UUID | None = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("group.id", ondelete="SET NULL"),
            nullable=True,
            default=None,
        )
    )
    group: Group = Relationship(back_populates="users",sa_relationship_kwargs={"lazy": "selectin"},)


class Assignment(SQLModel, table=True):
    id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            default=uuid4,
            primary_key=True,
        )
    )

    week: str | None = None
    due_date: datetime | None = None
    submission_status: str | None = None
    grade: str | None = None
    url_to_assignment: str | None = None

    enrollment_id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("enrollment.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    enrollment: Optional["Enrollment"] = Relationship(back_populates="assignments",sa_relationship_kwargs={"lazy": "selectin"},)


class Quiz(SQLModel, table=True):
    id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            default=uuid4,
            primary_key=True,
        )
    )

    week: str | None = None
    name: str | None = None
    quiz_close: datetime | None = None
    grade: str | None = None
    url: str | None = None

    enrollment_id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("enrollment.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    enrollment: Optional["Enrollment"] = Relationship(back_populates="quizzes",sa_relationship_kwargs={"lazy": "selectin"},)


class EclassSnapshot(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True, unique=True)
    payload: dict = Field(sa_column=Column(postgresql.JSONB, nullable=False))


class SuperUser(SQLModel,table = True):
    id:UUID = Field(
        sa_column=Column(
            postgresql.UUID,
            default = uuid4,
            primary_key=True
        )
    )
    first_name :str
    last_name:str
    username:str = Field(index=True,unique=True)
    hashed_password:str
    telegram_id:str|None = Field(nullable=True)
    is_root:bool = Column(Boolean, default=False, nullable=False)

    