from zoneinfo import ZoneInfo
from celery import Celery
from celery.schedules import crontab
from asgiref.sync import async_to_sync

from app.config import db_settings, bot_settings
from app.services import users, time_table
from app.database.session import get_session_ctx,engine
from app.database.models import Weeks

from datetime import datetime, time as dt_time

BOT_TOKEN = bot_settings.BOT_TOKEN
API_URL = bot_settings.API_URL

# Initialize Celery
celery = Celery(
    "notification_tasks",
    broker=db_settings.REDIS_URL(9), 
    broker_connection_retry_on=True
)
celery.conf.timezone = "Asia/Tashkent"
celery.conf.enable_utc = True


# Celery beat schedule
celery.conf.beat_schedule = {
    "send-class-reminders-every-1-minute": {
        "task": "app.worker.notification_scheduler.send_class_reminders",
        "schedule": crontab(minute="*/10", hour="9-18",day_of_week="mon-sun"),
    },
    "send-todays-time-table-every-morning":{
        "task": "app.worker.notification_scheduler.send_today_class",
        "schedule":crontab(hour=16,minute=45,day_of_week="mon-sun")
    }
}


# Async function that sends class reminders
async def send_class_reminders_async():
    try:
        async with get_session_ctx() as session:
            print("I started working...")
            user_session = users.UserService(session)
            time_table_session = time_table.TimeTableService(session, user_session)

            now = datetime.now(tz=ZoneInfo("Asia/Tashkent"))
            current_time = dt_time(now.hour, now.minute)
            current_week_day = Weeks(now.strftime("%A").lower())

            await time_table_session.get_subjects_by_time(current_time, current_week_day)

    finally:
        # IMPORTANT: prevents "different loop" pool reuse
        await engine.dispose()



@celery.task(name="app.worker.notification_scheduler.send_class_reminders")
def send_class_reminders():
    async_to_sync(send_class_reminders_async)()


async def send_today_class_async():
    try:
        async with get_session_ctx() as session:
            user_session = users.UserService(session)
            time_table_session = time_table.TimeTableService(session, user_session)

            now = datetime.now(tz=ZoneInfo("Asia/Tashkent"))
            current_week = now.strftime("%A").lower()

            await time_table_session.send_todays_time_table_everymorning(current_week)
    
    finally:
        await engine.dispose()


@celery.task(name = "app.worker.notification_scheduler.send_today_class")
def send_today_class():
    async_to_sync(send_today_class_async)()