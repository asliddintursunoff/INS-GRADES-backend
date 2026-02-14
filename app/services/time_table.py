from sqlmodel import select
from sqlalchemy.orm import selectinload

from app.database.models import User, ClassTime, Class, Subject, Group  # adjust import

class TimeTableService:
    def __init__(self, session):
        self.session = session

    async def my_time_table(self, user: User):
        # Reload user with group eager-loaded (prevents user.group lazy load)
        stmt_user = (
            select(User)
            .where(User.id == user.id)
            .options(selectinload(User.group))
        )
        db_user = (await self.session.execute(stmt_user)).scalars().first()
        if not db_user:
            return {"detail": "User not found"}

        if not db_user.group_id:
            return {
                "first_name": db_user.first_name or "",
                "group_name": None,
                "timetable": {},
                "detail": "User has no group",
            }

        group_name = db_user.group.group_name if db_user.group else None

        # Load ClassTime -> klass -> subject eagerly (prevents lazy loads)
        stmt = (
            select(ClassTime)
            .join(Class, ClassTime.class_id == Class.id)
            .where(Class.group_id == db_user.group_id)
            .options(
                selectinload(ClassTime.klass).selectinload(Class.subject),
            )
        )
        classtimes = (await self.session.execute(stmt)).scalars().all()

        timetable: dict[str, list[dict]] = {}

        for ct in classtimes:
            # week_day is enum Weeks, keep as lowercase string
            wd = ct.week_day.value if ct.week_day else "unknown"

            subj = ct.klass.subject  # safe now (eager-loaded)
            item = {
                "subject": subj.short_name if subj else None,
                "subject_name": subj.name if subj else None,
                "start_time": ct.start_time.strftime("%H:%M") if ct.start_time else None,
                "end_time": ct.end_time.strftime("%H:%M") if ct.end_time else None,
                "room": ct.room,
            }
            timetable.setdefault(wd, []).append(item)

        # Sort by start_time
        for wd, items in timetable.items():
            items.sort(key=lambda x: (x["start_time"] is None, x["start_time"]))

        # Weekday order
        order = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        ordered = {d: timetable[d] for d in order if d in timetable}

        return {
            "first_name": db_user.first_name or "",
            "group_name": group_name,
            "timetable": ordered,
        }
