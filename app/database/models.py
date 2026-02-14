from sqlmodel import ForeignKey, SQLModel, Field, Column, Relationship
from sqlalchemy.dialects import postgresql
from sqlalchemy import UniqueConstraint

from datetime import datetime, time
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
    classes: List["Class"] = Relationship(back_populates="subject")


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
    group: Optional[Group] = Relationship(back_populates="classes")

    subject_id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("subject.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    subject: Optional["Subject"] = Relationship(back_populates="classes")

    professor_id: UUID = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("professor.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    professor: Optional["Professor"] = Relationship(back_populates="classes")

    enrollments: List["Enrollment"] = Relationship(
        back_populates="klass",
        sa_relationship_kwargs={"overlaps": "users,classes"},
    )

    users: List["User"] = Relationship(
        back_populates="classes",
        link_model=Enrollment,
        sa_relationship_kwargs={"overlaps": "enrollments,klass,user"},
    )

    classtimes: List["ClassTime"] = Relationship(back_populates="klass")


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
    klass: Class = Relationship(back_populates="classtimes")

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

    telegram_id: str | None = Field(unique=True, index=True, default=None)
    student_id: str
    first_name: str | None = Field(max_length=50)
    last_name: str | None = Field(max_length=50)
    password: str | None

    is_subscribed: bool = Field(default=False)
    subscribtion_started: datetime | None = None
    subscribtion_end: datetime | None = None
    is_started: bool
    started_date: datetime | None = None
    eclass_registered: datetime |None = None

    enrollments: List["Enrollment"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"overlaps": "classes,users"},
    )

    classes: List["Class"] = Relationship(
        back_populates="users",
        link_model=Enrollment,
        sa_relationship_kwargs={"overlaps": "enrollments,klass,user"},
    )

    group_id: UUID | None = Field(
        sa_column=Column(
            postgresql.UUID(as_uuid=True),
            ForeignKey("group.id", ondelete="SET NULL"),
            nullable=True,
            default=None,
        )
    )
    group: Group = Relationship(back_populates="users")


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
    enrollment: Optional["Enrollment"] = Relationship(back_populates="assignments")


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
    enrollment: Optional["Enrollment"] = Relationship(back_populates="quizzes")


class EclassSnapshot(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(index=True, unique=True)
    payload: dict = Field(sa_column=Column(postgresql.JSONB, nullable=False))