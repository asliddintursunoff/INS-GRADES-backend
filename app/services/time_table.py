from collections import defaultdict
from typing import List
from fastapi import HTTPException


from sqlalchemy import delete,select
from pydantic import ValidationError
from app.api.schema.time_table import TimeTableBase
from app.database.models import TimeTable,Weeks,Users
from app.utils import send_message
from app.database.redis import class_notification_cache
# from app.api.dependencies import user_session

from rich import print,panel
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile
import pandas as pd
from datetime import time
from datetime import datetime, date, timedelta, time

def start_time_minus(start_time: time,min_:int) -> time:
    dt = datetime.combine(date.today(), start_time)
    return (dt - timedelta(minutes=min_)).time()

ALLOWED_CONTENT_TYPES = [
    "text/csv",
    
]
ALLOWED_EXTENSIONS = ["csv",]


class TimeTableService():
    def __init__(self,session:AsyncSession,user_service = None):
        self.session = session
        self.user_session = user_service

    async def update_whole_time_time(self,file:UploadFile):
        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(detail="File type not allowed. Allowed only for .csv!",status_code=400)
    
        if file.filename.split('.')[-1].lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(detail="File type not allowed. Allowed only for .csv!",status_code=400)
        
        df = pd.read_csv(file.file)
        data_lst =  df.to_dict(orient="records")
        
        try:
            data = [TimeTableBase(**row)  for row in data_lst]

            stmp = delete(TimeTable)
            await self.session.execute(stmp)
            
            self.session.add_all(
                [TimeTable(**i.model_dump()) for i in data]
            )
            
            await self.session.commit()

            return "successfully updated whole database"

        except ValidationError as e:
            raise HTTPException(detail=str(e),status_code=422)
        except Exception as e:
            raise HTTPException(detail = str(e),status_code=500)
        
    
    async def send_class_reminder_notification(self,lst_users:List[Users],cls:TimeTable):
        for user in lst_users:
            message = f"""👋 Hey {user.first_name}!

⏰ Heads up! Your class is starting soon 👀

📘 {cls.subject}
👨‍🏫 {cls.professor}
🏫 Room: {cls.room}

🕒 {cls.start_time} – {cls.end_time}
📅 {cls.week_day.capitalize()}

Don’t be late — your future self will thank you 😄"""
           
            await send_message(user.telegram_id,message=message)
    
    async def get_subjects_by_time(self,_time:time,week_day:Weeks):

        stmt = select(TimeTable).where(TimeTable.week_day == week_day)
        
        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        print(panel.Panel(str(rows),border_style="red"))
        lst_reminder_classes = []
        for row in rows:
            if _time<=row.start_time and _time>=start_time_minus(row.start_time,35) and not bool(class_notification_cache.exists(str(row.class_id))):

                lst_reminder_classes.append(row)
                class_notification_cache.setex(name = str(row.class_id),value="notified",time=3600)
        print(panel.Panel(str(lst_reminder_classes),border_style="green"))

        if not lst_reminder_classes:
            return
        

        for cls in lst_reminder_classes:
            users = await self.user_session.get_all_users_by_group_name(cls.group_name)
            print(users)
            await self.send_class_reminder_notification(users,cls)
        return 
    
    def message_format_today_time_table(self, user, group_name, today, table) -> str:
        first_name = user.first_name or "there"
        classes = sorted(table, key=lambda c: c.start_time)

        if not classes:
            return (
                f"Hello, {first_name} 👋\n\n"
                f"📅 You have <b>no classes today ({today.capitalize()})</b>.\n"
                f"Enjoy your day! 😊"
            )

        message = [
            f"Hello, {first_name} 👋",
            "",
            f"📅 <b>Your timetable for {today.capitalize()}</b>",
            f"🎓 <b>Group:</b> {group_name}",
            ""
        ]

        for cls in classes:
            start = cls.start_time.strftime("%H:%M")
            end = cls.end_time.strftime("%H:%M")

            message.extend([
                f"🕒 <b>{start} – {end}</b>",
                f"📘 <b>{cls.subject}</b>",
                f"👨‍🏫 {cls.professor}",
                f"🏫 {cls.room}",
                ""
            ])

        message.append("✅ Have a productive class!")

        return "\n".join(message)

    

    def message_format_full_timetable_compact(self, user, group_name, table: List[TimeTable]) -> str:
        first_name = user.first_name or "there"

        if not table:
            return (
                f"Hello, {first_name} 👋\n\n"
                f"📅 <b>No classes found for your group {group_name}</b>.\n"
                f"Enjoy your week! 😊"
            )

        # Map weekdays → list of classes
        weekdays_order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        timetable_map = defaultdict(list)
        for cls in table:
            timetable_map[cls.week_day.lower()].append(cls)

        message_lines = [
            f"Hello, {first_name} 👋",
            f"🎓 <b>Weekly timetable for group {group_name}</b>",
            ""
        ]

        for day in weekdays_order:
            day_classes = timetable_map.get(day, [])
            if not day_classes:
                continue

            # Sort classes by start_time
            day_classes.sort(key=lambda c: c.start_time)

            message_lines.append(f"📅 <b>{day.capitalize()}</b>")

            # Use one line per class: Subject | HH:MM–HH:MM | Room
            for cls in day_classes:
                start = cls.start_time.strftime("%H:%M")
                end = cls.end_time.strftime("%H:%M")
                message_lines.append(f"📘 <b>{cls.subject}</b> | 🕒 {start}–{end} | 🏫 {cls.room}")

            message_lines.append("")  # Blank line between days

        message_lines.append("✅ Have a productive week!")

        return "\n".join(message_lines)



    async def send_todays_time_table_everymorning(self,today):

        stmt  = select(TimeTable).where(TimeTable.week_day == today)
        query = await self.session.execute(stmt)
        groups_with_lessons:dict[str:list] = {}
        for row in query.scalars().all():
            if row.group_name in groups_with_lessons:
                groups_with_lessons[row.group_name].append(row)
            else:
                groups_with_lessons[row.group_name] = [row]
        
        for group,val in groups_with_lessons.items():
            users = await self.user_session.get_all_users_by_group_name(group)
            for user in users:
                message = self.message_format_today_time_table(user,group,today,val)

                await send_message(user.telegram_id,message)
        return groups_with_lessons
        

    async def get_user_full_time_table(self,user:Users)->List[TimeTable]:
        
        stmt = select(TimeTable).where(TimeTable.group_name == user.group_name)
        query = await self.session.execute(stmt)

        result = query.scalars().all()
        response = {
            "user_first_name":user.first_name,
            "group":user.group_name,
            "time_table":result
        }
        # message = self.message_format_full_timetable_compact(user,user.group_name,result)
        # await send_message(user.telegram_id,message)
        return response
