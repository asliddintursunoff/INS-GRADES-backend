import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infra.redis_sync import notification_cache,redis_user_info_cache
from app.config import db_settings,bot_settings



# ---- imports from your app (adjust path if needed) ----
import os
import json
import time as time_mod
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

import requests
from redis import Redis
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

# ---- YOUR MODELS (adjust import path) ----
from app.database.models import ClassTime, Class, User, Enrollment  # adjust if needed




DATABASE_URL = db_settings.SYNC_DB_URL  # e.g. postgres://...
REDIS_DEDUPE_URL = db_settings.REDIS_DB(9)
REDIS_INFO_URL = redis_user_info_cache  # redis db=3 url for payload cache

BOT_TOKEN = bot_settings.BOT_TOKEN
TELEGRAM_SEND_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
TELEGRAM_SLEEP_SEC = float(os.environ.get("TELEGRAM_SLEEP_SEC", "0.05"))
# =========================
# Config
# =========================
TZ = ZoneInfo("Asia/Tashkent")




# Small delay to be gentle with Telegram (optional)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

redis_info = REDIS_INFO_URL
redis_dedupe = Redis.from_url(REDIS_DEDUPE_URL,decode_responses=True)

# =========================
# Telegram
# =========================
def send_message(chat_id: str, text: str):
    resp = requests.post(
        TELEGRAM_SEND_URL,
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )
    if resp.status_code != 200:
        # print errors so Railway logs show them
        print("Telegram error:", resp.status_code, resp.text)

# =========================
# Helpers
# =========================
def today_weekday_name(now: datetime) -> str:
    # Weeks enum values are like "monday", "tuesday", ...
    return now.strftime("%A").lower()

def combine_date_time(d: date, t) -> datetime:
    return datetime(d.year, d.month, d.day, t.hour, t.minute, 0, tzinfo=TZ)

def fmt_hhmm(t) -> str:
    return t.strftime("%H:%M")

def get_user_payload_map(user_id: str) -> dict:
    """
    Returns a dict: { "first_name":..., "subjects_by_code": { "AE4": {"attendance":2,"absence":0,"late":0}, ... } }
    If user payload not in redis -> empty map (still send reminders without stats).
    """
    raw = redis_info.get(str(user_id))
    if not raw:
        return {"first_name": None, "subjects_by_code": {}}

    try:
        data = json.loads(raw)
    except Exception:
        return {"first_name": None, "subjects_by_code": {}}

    subjects_by_code = {}
    for s in (data.get("subjects") or []):
        code = s.get("subject")
        att = (s.get("attendance") or {})
        if code:
            subjects_by_code[code] = {
                "attendance": int(att.get("attendance") or 0),
                "absence": int(att.get("absence") or 0),
                "late": int(att.get("late") or 0),
                "subject_name": s.get("subject_name"),
                "professor_name": s.get("professor_name"),
            }

    return {
        "first_name": data.get("first_name"),
        "subjects_by_code": subjects_by_code,
    }

def dedupe_key(kind: str, user_id: str, class_id: str, start_dt: datetime) -> str:
    # Unique per occurrence (date+time) per user per class
    tag = start_dt.strftime("%Y%m%d_%H%M")
    return f"rem:{kind}:{user_id}:{class_id}:{tag}"

def should_send_once(kind: str, user_id: str, class_id: str, start_dt: datetime, ttl_sec: int) -> bool:
    key = dedupe_key(kind, user_id, class_id, start_dt)
    # SET NX = only first time returns True
    return bool(redis_dedupe.set(key, "1", nx=True, ex=ttl_sec))

# =========================
# Message builders
# =========================
def build_30m_message(user_first_name: str, subject_code: str, subject_name: str, professor: str, room: str | None,
                     start_time, end_time, week_day: str,
                     stats: dict | None) -> str:
    # stats = {"attendance":..,"absence":..,"late":..}
    start = fmt_hhmm(start_time)
    end = fmt_hhmm(end_time) if end_time else "??:??"

    stats_line = ""
    extra = "Don’t be late — your future self will thank you 😄"
    if stats:
        stats_line = (
            f"\n\n📊 <b>Attendance stats</b>\n"
            f"✅ Attended: <b>{stats.get('attendance', 0)}</b>\n"
            f"❌ Absence: <b>{stats.get('absence', 0)}</b>\n"
            f"⏳ Late: <b>{stats.get('late', 0)}</b>"
        )
        if stats.get('absence', 0) >=5:
            extra = f"<b>⚠️ Go faster — you have {stats.get('absence', 0)} absences!</b>"
    
    room_line = f"🏫 Room: <b>{room}</b>\n" if room else ""

    return (
        f"👋 Hey <b>{user_first_name or 'there'}</b>!\n\n"
        f"⏰ <b>Heads up!</b> Your class starts in <b>30 minutes</b> 👀\n\n"
        f"📘 <b>{subject_code}</b> — {subject_name}\n"
        f"👨‍🏫 {professor}\n"
        f"{room_line}"
        f"🕒 <b>{start} – {end}</b>\n"
        f"📅 {week_day.capitalize()}"
        f"{stats_line}\n\n"

        
        f"{extra}"
    )

def build_8am_message(user_first_name: str, today_name: str, classes_lines: list[str]) -> str:
    return (
        f"☀️ Hello, <b>{user_first_name or 'there'}</b> 👋\n\n"
        f"📅 <b>Today’s classes</b> ({today_name.capitalize()})\n\n"
        + "\n".join(classes_lines)
        + "\n\n✅ Have a productive day!"
    )

# =========================
# Jobs
# =========================
def run_30min_reminders():
    now = datetime.now(TZ)
    wd = today_weekday_name(now)

    with Session(engine) as session:
        # Load all classes for today's weekday (small list usually)
        stmt = (
            select(ClassTime)
            .where(ClassTime.week_day == wd)
            .options(
                selectinload(ClassTime.klass)
                .selectinload(Class.users),
                selectinload(ClassTime.klass)
                .selectinload(Class.subject),
                selectinload(ClassTime.klass)
                .selectinload(Class.professor),
            )
        )
        classtimes = session.execute(stmt).scalars().all()

        for ct in classtimes:
            if not ct.start_time:
                continue

            start_dt = combine_date_time(now.date(), ct.start_time)
            # Condition: now is between start-30m and start (strictly before start)
            if not (start_dt - timedelta(minutes=30) <= now < start_dt):
                continue

            klass = ct.klass
            if not klass or not klass.subject or not klass.professor:
                continue

            subj_code = klass.subject.short_name
            subj_name = klass.subject.name
            prof_name = klass.professor.name

            for u in (klass.users or []):
                if not u.telegram_id:
                    continue

                # Dedupe (keep it for 3 hours)
                if not should_send_once("30m", str(u.id), str(klass.id), start_dt, ttl_sec=60 * 60 * 3):
                    continue

                payload_map = get_user_payload_map(str(u.id))
                stats = payload_map["subjects_by_code"].get(subj_code)

                msg = build_30m_message(
                    user_first_name=payload_map["first_name"] or u.first_name,
                    subject_code=subj_code,
                    subject_name=subj_name,
                    professor=prof_name,
                    room=ct.room,
                    start_time=ct.start_time,
                    end_time=ct.end_time,
                    week_day=wd,
                    stats=stats,
                )
                send_message(u.telegram_id, msg)
                time_mod.sleep(TELEGRAM_SLEEP_SEC)

def run_daily_8am():
    now = datetime.now(TZ)
    wd = today_weekday_name(now)

    with Session(engine) as session:
        # Fetch today's class times with users in one go
        stmt = (
            select(ClassTime)
            .where(ClassTime.week_day == wd)
            .options(
                selectinload(ClassTime.klass).selectinload(Class.users),
                selectinload(ClassTime.klass).selectinload(Class.subject),
                selectinload(ClassTime.klass).selectinload(Class.professor),
            )
        )
        classtimes = session.execute(stmt).scalars().all()

        # Build per-user list
        per_user: dict[str, list[tuple]] = {}  # user_id -> [(start_time, end_time, room, subj_code, subj_name, prof_name, class_id)]
        for ct in classtimes:
            klass = ct.klass
            if not klass or not klass.subject or not klass.professor or not ct.start_time:
                continue

            subj_code = klass.subject.short_name
            subj_name = klass.subject.name
            prof_name = klass.professor.name

            for u in (klass.users or []):
                if not u.telegram_id:
                    continue
                per_user.setdefault(str(u.id), []).append(
                    (ct.start_time, ct.end_time, ct.room, subj_code, subj_name, prof_name, str(klass.id), u.telegram_id, u.first_name)
                )

        # Send per user
        for user_id, items in per_user.items():
            # If no classes -> do nothing (your requirement)
            if not items:
                continue

            # Dedupe daily (per user per day)
            daily_key = f"rem:8am:{user_id}:{now.strftime('%Y%m%d')}"
            if not redis_dedupe.set(daily_key, "1", nx=True, ex=60 * 60 * 18):
                continue

            payload_map = get_user_payload_map(user_id)
            first_name = payload_map["first_name"] or items[0][9]
            subjects_by_code = payload_map["subjects_by_code"]

            items.sort(key=lambda x: x[0])  # sort by start_time
            lines = []
            chat_id = items[0][8]

            for start_t, end_t, room, subj_code, subj_name, prof_name, class_id, _, _ in items:
                stats = subjects_by_code.get(subj_code, {})
                # morning: only absence + late (your requirement)
                abs_v = stats.get("absence", 0)
                late_v = stats.get("late", 0)

                start = fmt_hhmm(start_t)
                end = fmt_hhmm(end_t) if end_t else "??:??"
                room_part = f" | 🏫 {room}" if room else ""

                lines.append(
                    f"🕒 <b>{start}–{end}</b> | 📘 <b>{subj_code}</b>{room_part}\n"
                    f"   👨‍🏫 {prof_name}\n"
                    f"   ❌ Absence: <b>{abs_v}</b>   ⏳ Late: <b>{late_v}</b>\n"
                )

            msg = build_8am_message(first_name, wd, lines)
            send_message(chat_id, msg)
            time_mod.sleep(TELEGRAM_SLEEP_SEC)

# =========================
# Entry
# =========================
if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "30m"

    if mode == "30m":
        run_30min_reminders()
    elif mode == "8am":
        run_daily_8am()
    else:
        raise SystemExit("Usage: python scripts/reminder.py [30m|8am]")
