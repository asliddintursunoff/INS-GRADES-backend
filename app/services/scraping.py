from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional, Any
TZ = ZoneInfo("Asia/Tashkent")
from app.infra.redis_sync import redis_scrape_cache,redis_user_info_cache,redis_registered_users_sync
from app.database.models import (
    EclassSnapshot, User, Professor, Class, Subject, Enrollment, Assignment, Quiz
)
from app.scraper.script import AuthExpired, BlockedOrForbidden, EclassClient, EclassError, LoginFailed, RateLimited, pack_student_rest

import requests
from app.config import bot_settings

API_URL = bot_settings.API_URL

failed_message = (
                "⚠️ <b>Authentication Error</b>\n\n"
                "Your password appears to be incorrect or recently changed.\n"
                "For security reasons, please register again.\n\n"
                "🚀 Tap /start to begin registration."
            )


def send_message(user_telegram_id: str, message: str):
    requests.post(API_URL, json={
        "chat_id": user_telegram_id,
        "text": message,
        "parse_mode": "HTML"
    })

import json
from datetime import datetime
from typing import Optional, Dict, Any, List


def _parse_dt(dt_str: str | None) -> Optional[datetime]:
    if not dt_str:
        return None
    s = str(dt_str).strip()
    if s in {"", "-"}:
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=TZ)
    except Exception:
        return None


def build_redis_student_payload(final_json: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Keep assignments only if:
    - submission == "No submission"
    - due_date exists
    - not overdue
    - due within next 12 days
    """
    if now is None:
        now = datetime.now(ZoneInfo("Asia/Tashkent"))

    out = {
        "student_id": final_json.get("student_id"),
        "first_name": final_json.get("first_name"),
        "last_name": final_json.get("last_name"),
        "subjects": [],
    }

    for subj in final_json.get("subjects", []):
        subj_out = {
            "subject": subj.get("subject"),
            "subject_name": subj.get("subject_name"),
            "professor_name": subj.get("professor_name"),
            "course_url": subj.get("course_url"),
            "attendance": subj.get("attendance"),
            "quizzes": subj.get("quizzes"),
            "assignments": None,
        }

        assignments = subj.get("assignments") or []
        filtered: List[Dict[str, Any]] = []

        for a in assignments:
            submission = (a.get("submission") or "").strip()
            if submission != "No submission":
                continue

            due_dt = _parse_dt(a.get("due_date"))
            if due_dt is None:
                continue

            # time difference
            delta = due_dt - now
            seconds_left = delta.total_seconds()

            # skip overdue
            if seconds_left <= 0:
                continue

            # skip if more than 12 days
            if seconds_left > 12 * 24 * 60 * 60:
                continue

            filtered.append(a)

        subj_out["assignments"] = filtered if filtered else None
        out["subjects"].append(subj_out)

    return out


def save_student_payload_to_redis(redis_client, user_id, final_json: Dict[str, Any], ttl_seconds: int = 60 * 60 * 120):
    payload = build_redis_student_payload(final_json)
    redis_client.set(str(user_id), json.dumps(payload, ensure_ascii=False), ex=ttl_seconds)
    return payload

class ScrapService:
    def __init__(self, session: Session,is_send = True):
        self.is_send = is_send
        self.session = session

    # =========================
    # Helpers
    # =========================
    def _now(self) -> datetime:
        # Your DB uses naive datetime
        return datetime.now(ZoneInfo("Asia/Tashkent"))

    def _safe_int(self, v: Any, default: int = 0) -> int:
        try:
            return int(v)
        except Exception:
            return default

    def _parse_dt(self, dt_str: str | None) -> Optional[datetime]:
        if not dt_str:
            return None
        s = str(dt_str).strip()
        if s in {"", "-"}:
            return None
        try:
            dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
            return dt.replace(tzinfo=TZ)
        except Exception:
            return None

    def _norm_grade(self, g: Any) -> Optional[str]:
        if g is None:
            return None
        s = str(g).strip()
        if s in {"", "-", "None"}:
            return None
        return s

    def _format_time_left(self, delta: timedelta) -> str:
        total = int(delta.total_seconds())
        if total <= 0:
            return "0m"
        days = total // 86400
        rem = total % 86400
        hours = rem // 3600
        rem = rem % 3600
        mins = rem // 60

        parts = []
        if days:
            parts.append(f"{days}d")
        if hours or days:
            parts.append(f"{hours}h")
        parts.append(f"{mins}m")
        return " ".join(parts)

    def _notify_once(self, key: str, ttl_seconds: int = 60 * 60 * 24 * 90) -> bool:
        # Redis only for dedupe/time management
        return bool(redis_scrape_cache.set(key, "1", nx=True, ex=ttl_seconds))

    def _send(self, user: User, text: str):
        
        if user.telegram_id and self.is_send:
            send_message(user.telegram_id, text)

    def _subject_title(self, data: dict) -> str:
        code = data.get("subject") or ""
        name = data.get("subject_name") or ""
        if code and name:
            return f"{code} — {name}"
        return name or code or "Subject"

    # =========================
    # DB sync: ensure Subject/Professor/Class/Enrollment exists
    # =========================
    def _get_or_create_enrollment(self, user: User, data: dict) -> Enrollment:
        """
        IMPORTANT:
        Your Class has UNIQUE(group_id, subject_id). So:
        - Find class by (group_id, subject_id)
        - Update professor_id if changed (do NOT insert new class)
        """
        if user.group_id is None:
            raise ValueError(f"user.group_id is None for user_id={user.id} student_id={user.student_id}")

        subject_name = (data.get("subject_name") or "").strip()
        subject_short = (data.get("subject") or "").strip()
        professor_name = (data.get("professor_name") or "").strip()

        # Subject: find or create
        subject = self.session.execute(
            select(Subject).where(Subject.name == subject_name)
        ).scalars().one_or_none()
        if subject is None:
            subject = Subject(name=subject_name, short_name=subject_short)
            self.session.add(subject)
            self.session.flush()

        # Professor: find or create
        professor = self.session.execute(
            select(Professor).where(Professor.name == professor_name)
        ).scalars().one_or_none()
        if professor is None:
            professor = Professor(name=professor_name)
            self.session.add(professor)
            self.session.flush()

        # Class: unique by (group_id, subject_id)
        klass = self.session.execute(
            select(Class).where(
                Class.group_id == user.group_id,
                Class.subject_id == subject.id
            )
        ).scalars().one_or_none()

        if klass is None:
            klass = Class(
                group_id=user.group_id,
                subject_id=subject.id,
                professor_id=professor.id
            )
            self.session.add(klass)
            self.session.flush()
        else:
            # professor can change (online, different teacher) -> update (no insert)
            if klass.professor_id != professor.id:
                klass.professor_id = professor.id
                self.session.add(klass)

        # Enrollment: find or create
        enrollment = self.session.execute(
            select(Enrollment).where(
                Enrollment.user_id == user.id,
                Enrollment.class_id == klass.id
            )
        ).scalars().one_or_none()

        if enrollment is None:
            att = data.get("attendance") or {}
            enrollment = Enrollment(
                user_id=user.id,
                class_id=klass.id,
                attendance=self._safe_int(att.get("attendance"), 0),
                absence=self._safe_int(att.get("absence"), 0),
                late=self._safe_int(att.get("late"), 0),
            )
            self.session.add(enrollment)
            self.session.flush()

        return enrollment

    # =========================
    # Hard delete dropped enrollments
    # =========================
    def _hard_delete_enrollment(self, enrollment: Enrollment):
        # delete children first
        assignments = self.session.execute(
            select(Assignment).where(Assignment.enrollment_id == enrollment.id)
        ).scalars().all()
        for a in assignments:
            self.session.delete(a)

        quizzes = self.session.execute(
            select(Quiz).where(Quiz.enrollment_id == enrollment.id)
        ).scalars().all()
        for q in quizzes:
            self.session.delete(q)

        self.session.delete(enrollment)

    # =========================
    # Compare + update + notify
    # =========================
    def compare_with_old_values(self, user: User, db: Enrollment, data: dict):
        now = self._now()
        subject_label = self._subject_title(data)

        # -------------------------
        # Attendance / Absence / Late
        # -------------------------
        att = data.get("attendance") or {}
        new_att = self._safe_int(att.get("attendance"), 0)
        new_abs = self._safe_int(att.get("absence"), 0)
        new_late = self._safe_int(att.get("late"), 0)

        old_att = db.attendance
        old_abs = db.absence
        old_late = db.late

        # ✅ Detect "first sync" (so you can send at least one message if you want)
        # If your DB columns are NOT nullable and always 0, set them to NULL in DB
        # or change this logic to check a separate flag.
        is_first_sync = (old_att is None and old_abs is None and old_late is None)

        # ✅ Always save latest values
        db.attendance = new_att
        db.absence = new_abs
        db.late = new_late

        def notify_attendance_change(
            old_abs: Optional[int], new_abs: int,
            old_late: Optional[int], new_late: int,
            old_att: Optional[int], new_att: int,
            first_sync: bool,
        ):
            # Helper: notify when increased (your original behavior)
            def increased(old: Optional[int], new: int) -> bool:
                if old is None:
                    return new > 0
                return new > old

            abs_inc = increased(old_abs, new_abs)
            late_inc = increased(old_late, new_late)
            att_inc = increased(old_att, new_att)

            # ✅ If you want a message on the very first scrape, enable this:
            # - It will only send if at least one value is > 0
            first_sync_should_notify = first_sync and (new_att > 0 or new_abs > 0 or new_late > 0)

            if not (abs_inc or late_inc or att_inc or first_sync_should_notify):
                return

            # ✅ Dedupe key (includes new values, so it sends once per new state)
            key = f"notify:u:{user.id}:e:{db.id}:att:{data.get('subject')}:{new_att}:{new_abs}:{new_late}"
            if not self._notify_once(key):
                return

            def fmt_line(label: str, emoji: str, old: Optional[int], new: int, highlight: bool) -> str:
                before = "—" if old is None else str(old)
                if highlight:
                    return f"{emoji} <b>{label}:</b> <b>{before} → {new}</b>"
                return f"{emoji} <b>{label}:</b> {before} → {new}"

            header_emoji = "⚠️" if (abs_inc or late_inc) else "✅"
            title = "Attendance Update" if header_emoji == "✅" else "Warning: Attendance Update"

            msg = (
                f"{header_emoji} <b>{title}</b>\n"
                f"<b>{subject_label}</b>\n\n"
                f"{fmt_line('Attendance', '✅', old_att, new_att, att_inc or first_sync_should_notify)}\n"
                f"{fmt_line('Absence',    '⚠️', old_abs, new_abs, abs_inc or first_sync_should_notify)}\n"
                f"{fmt_line('Late',       '⏳', old_late, new_late, late_inc or first_sync_should_notify)}\n\n"
                f"Keep it up 💪"
            )
            self._send(user, msg)

        # ✅ Call once after computing old/new
        notify_attendance_change(old_abs, new_abs, old_late, new_late, old_att, new_att, is_first_sync)

    # ... keep the rest of your assignments/quizzes logic below unchanged ...


        # -------------------------
        # Assignments (DB existence via Postgres, Redis only for send dedupe)
        # -------------------------
        parsed_assignments = data.get("assignments") or []

        # aggregate "new assignments" for ONE subject
        new_assignment_lines: list[str] = []

        if parsed_assignments:
            existing = self.session.execute(
                select(Assignment).where(Assignment.enrollment_id == db.id)
            ).scalars().all()
            by_url = {a.url_to_assignment: a for a in existing if a.url_to_assignment}

            for a in parsed_assignments:
                a_url = (a.get("url") or "").strip() or None
                a_name = a.get("name") or "Assignment"
                a_week = a.get("week")
                a_due = self._parse_dt(a.get("due_date"))
                a_sub = a.get("submission")  # "No submission" means not submitted
                a_grade = a.get("grade")

                is_not_submitted = (a_sub == "No submission")
                is_overdue = (a_due is not None and a_due < now)

                row = by_url.get(a_url) if a_url else None
                created = False

                # Keep old grade before overwriting
                old_grade_norm = self._norm_grade(row.grade) if row is not None else None

                if row is None:
                    # Save even if overdue/submitted
                    row = Assignment(
                        week=a_week,
                        due_date=a_due,
                        submission_status=a_sub,
                        grade=a_grade,
                        url_to_assignment=a_url,
                        enrollment_id=db.id
                    )
                    self.session.add(row)
                    created = True

                # sync
                row.week = a_week
                row.due_date = a_due
                row.submission_status = a_sub
                row.grade = a_grade
                row.url_to_assignment = a_url

                # NEW assignment notify:
                # only if created now, not overdue, not submitted
                if created and (not is_overdue) and is_not_submitted and a_url:
                    key_new = f"notify:u:{user.id}:e:{db.id}:a:{a_url}:new"
                    if self._notify_once(key_new):
                        due_txt = a_due.strftime("%d-%m-%Y %H:%M") if a_due else "-"
                        open_link = f'<a href="{a_url}">Open</a>' 
                        new_assignment_lines.append(
                            f"📝 <b>{a_name}</b>\n"
                            f"📅 Deadline: <b>{due_txt}</b>\n"
                            f"🔗 {open_link}"
                        )

                    # If new assignment is already within <=5 days:
                    # suppress due5 and due2 reminders forever (redis keys),
                    # BUT allow due1 later.
                    if a_due is not None:
                        left = a_due - now
                        days_left = left.total_seconds() / 86400.0
                        if days_left <= 5:
                            redis_scrape_cache.set(
                                f"notify:u:{user.id}:e:{db.id}:a:{a_url}:due5", "1",
                                ex=60 * 60 * 24 * 90
                            )
                        if days_left <= 2:
                            redis_scrape_cache.set(
                                f"notify:u:{user.id}:e:{db.id}:a:{a_url}:due2", "1",
                                ex=60 * 60 * 24 * 90
                            )

                # Reminders (exact time left):
                # only if not submitted, not overdue, has due date
                # Reminders (exact time left):
                # only if not submitted, not overdue, has due date
                if a_due and (not is_overdue) and is_not_submitted and a_url:
                    left = a_due - now
                    if left.total_seconds() <= 0:
                        continue

                    days_left = left.total_seconds() / 86400.0
                    if days_left <= 1:
                        tag = "due1"
                    elif days_left <= 2:
                        tag = "due2"
                    elif days_left <= 5:
                        tag = "due5"
                    else:
                        tag = None

                    if tag:
                        key = f"notify:u:{user.id}:e:{db.id}:a:{a_url}:{tag}"
                        if self._notify_once(key):  # ✅ you missed this
                            due_txt = a_due.strftime("%d-%m-%Y %H:%M")
                            left_txt = self._format_time_left(left)

                            header = "🚨 <b>Assignment deadline in 24h!</b>" if tag == "due1" else "⏳ <b>Assignment deadline is coming</b>"

                            self._send(
                                user,
                                f"{header}\n"
                                f"━━━━━━━━━━━━━━\n"
                                f"📘 <b>{subject_label}</b>\n\n"
                                f"📝 <b>{a_name}</b>\n"
                                f"📅 Deadline: <b>{due_txt}</b>\n"
                                f"⏰ Time left: <b>{left_txt}</b>\n\n"
                                f"🔗 <a href='{a_url}'>Open</a>\n"
                                f"━━━━━━━━━━━━━━\n"
                                f"🚀 Don’t miss the deadline!"
                            )


                # Grade notify once (even after overdue):
                new_grade_norm = self._norm_grade(a_grade)
                if new_grade_norm and a_url:
                    # notify only if it wasn't graded before
                    if old_grade_norm is None:
                        key = f"notify:u:{user.id}:e:{db.id}:a:{a_url}:graded"
                        if self._notify_once(key):
                            self._send(
                                user,
                                f"✅ <b>Assignment graded</b>\n"
                                f"<b>{subject_label}</b>\n"
                                f"• {a_name}\n"
                                f"Grade: <b>{new_grade_norm}</b>\n"
                                f"{a_url}"
                            )

        # Send ONE message for all new assignments of this subject
        if new_assignment_lines:
            count = len(new_assignment_lines)
            msg = (
                f"🆕 <b>{count} New assignment{'s' if count > 1 else ''} added</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"📘 <b>{subject_label}</b>\n\n"
                + "\n\n".join(new_assignment_lines) +
                "\n\n━━━━━━━━━━━━━━\n"
                f"✅ Good luck! Submit early 💪"
            )
            self._send(user, msg)

        # -------------------------
        # Quizzes (DB existence via Postgres, Redis only for send dedupe)
        # -------------------------
        parsed_quizzes = data.get("quizzes") or []
        new_quiz_lines: list[str] = []

        if parsed_quizzes:
            existing_q = self.session.execute(
                select(Quiz).where(Quiz.enrollment_id == db.id)
            ).scalars().all()

            by_url_q = {q.url: q for q in existing_q if q.url}

            for q in parsed_quizzes:
                q_url = (q.get("url") or "").strip() or None
                q_name = q.get("name") or "Quiz"
                q_week = q.get("week")
                q_close = self._parse_dt(q.get("quiz_closes"))
                q_grade = q.get("grade")

                # ✅ NEW: use parser status instead of grade
                q_status = (q.get("status") or "").strip().lower()
                is_submitted = q_status == "submitted"

                is_overdue = (q_close is not None and q_close < now)

                row = by_url_q.get(q_url) if q_url else None
                created = False

                if row is None:
                    row = Quiz(
                        week=q_week,
                        name=q_name,
                        quiz_close=q_close,
                        grade=str(q_grade) if q_grade is not None else None,
                        url=q_url,
                        enrollment_id=db.id
                    )
                    self.session.add(row)
                    created = True

                # sync
                row.week = q_week
                row.name = q_name
                row.quiz_close = q_close
                row.grade = str(q_grade) if q_grade is not None else None
                row.url = q_url

                # -------------------------
                # New quiz notification
                # Only if NOT submitted and NOT overdue
                # -------------------------
                if created and (not is_overdue) and (not is_submitted) and q_url:
                    key_new = f"notify:u:{user.id}:e:{db.id}:q:{q_url}:new"
                    if self._notify_once(key_new):
                        close_txt = q_close.strftime("%d-%m-%Y %H:%M") if q_close else "-"
                        new_quiz_lines.append(
                            f"• <b>{q_name}</b>\n"
                            f"  Closes: <b>{close_txt}</b>\n"
                            f"  {q_url}"
                        )

                # -------------------------
                # Reminder logic
                # Only if NOT submitted and NOT overdue
                # -------------------------
                if q_close and (not is_overdue) and (not is_submitted) and q_url:
                    left = q_close - now
                    if left.total_seconds() <= 0:
                        continue

                    days_left = left.total_seconds() / 86400.0
                    if days_left <= 1:
                        tag = "close1"
                    elif days_left <= 2:
                        tag = "close2"
                    elif days_left <= 5:
                        tag = "close5"
                    else:
                        tag = None

                    if tag:
                        key = f"notify:u:{user.id}:e:{db.id}:q:{q_url}:{tag}"
                        if self._notify_once(key):
                            close_txt = q_close.strftime("%d-%m-%Y %H:%M")
                            left_txt = self._format_time_left(left)
                            header = "🚨 <b>Quiz closing soon!</b>" if tag == "due1" else "⏳ <b>Quiz reminder</b>"

                            self._send(
                                user,
                                f"{header}\n"
                                f"━━━━━━━━━━━━━━\n"
                                f"📘 <b>{subject_label}</b>\n\n"
                                f"📝 <b>{q_name}</b>\n"
                                f"📅 Closes: <b>{close_txt}</b>\n"
                                f"⏰ Time left: <b>{left_txt}</b>\n\n"
                                f"🔗 {q_url}\n"
                                f"━━━━━━━━━━━━━━\n"
                                f"⚡ Don’t wait until the last minute!"
                            )

        # Send one message for new quizzes
        # Send one message for new quizzes
        if new_quiz_lines:
            msg = (
                f"🆕 <b>New Quiz Available!</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"📘 <b>{subject_label}</b>\n\n"
                + "\n\n".join(new_quiz_lines) +
                "\n\n━━━━━━━━━━━━━━\n"
                f"🚀 Don’t forget to complete it on time!"
            )
            self._send(user, msg)



    # =========================
    # Scrape for all + hard delete dropped
    # =========================
    def scrape_e_class_for_all(self):
        users = self.session.execute(
            select(User).where(
                User.telegram_id != None,
                User.password != None
            )
        ).scalars().all()

        
        errors = []

        for user in users:
            if user.group_id is None:
                continue

            client = EclassClient()

            try:
                client.login(user.student_id, user.password)
                rows = client.get_all_attendance()
                final_json = pack_student_rest(user.student_id, rows)

                scraped_enrollment_ids: set = set()

                # 1) Sync subjects
                for subj in final_json.get("subjects", []):
                    enrollment = self._get_or_create_enrollment(user, subj)
                    scraped_enrollment_ids.add(enrollment.id)
                    self.compare_with_old_values(user, enrollment, subj)

                # 2) Hard delete dropped enrollments
                db_enrollments = self.session.execute(
                    select(Enrollment)
                    .join(Class, Enrollment.class_id == Class.id)
                    .where(
                        Enrollment.user_id == user.id,
                        Class.group_id == user.group_id
                    )
                ).scalars().all()

                for enr in db_enrollments:
                    if enr.id not in scraped_enrollment_ids:
                        self._hard_delete_enrollment(enr)

                # commit db changes for this user
                self.session.commit()

                # store cache in redis
                final_json["first_name"] = user.first_name
                final_json["last_name"] = user.last_name
                save_student_payload_to_redis(
                    redis_user_info_cache,
                    user.id,
                    final_json=final_json
                )
                stmt = select(EclassSnapshot).where(EclassSnapshot.user_id == user.id)
                snap = self.session.execute(stmt).scalars().first() 
                if snap:
                    snap.payload = final_json
                else:
                    snap = EclassSnapshot(user_id=user.id, payload=final_json)
                    self.session.add(snap)

                self.session.commit()
                        
            except (LoginFailed, AuthExpired, BlockedOrForbidden) as e:
                # ✅ disable this user for future scraping: clear password
                user.password = None
                self.session.add(user)
                self.session.commit()

                send_message(user.telegram_id,failed_message)
                errors.append({
                    "user_id": str(user.id),
                    "student_id": user.student_id,
                    "error": type(e).__name__
                })
                continue

            except (RateLimited, EclassError) as e:
                # ✅ just skip user, don't stop whole job
                self.session.rollback()
                errors.append({
                    "user_id": str(user.id),
                    "student_id": user.student_id,
                    "error": type(e).__name__
                })
                continue

            except Exception as e:
                # ✅ any unexpected error: rollback and continue
                self.session.rollback()
                errors.append({
                    "user_id": str(user.id),
                    "student_id": user.student_id,
                    "error": str(e)
                })
                continue

        return {
      
            "failed": len(errors),
            "errors": errors,
          
        }

    def scrape_e_class_for_one_user(self,user_id,password:str):
        
        user = self.session.execute(
            select(User).where(User.id==user_id)
        ).scalar_one_or_none()

        if not user:
            return HTTPException(detail="User not found",status_code=404)
        client = EclassClient()
        try:
            client.login(user.student_id, password)
            rows = client.get_all_attendance()
            final_json = pack_student_rest(user.student_id, rows)

            scraped_enrollment_ids: set = set()

            # 1) Sync subjects that exist in e-class
            for subj in final_json.get("subjects", []):
                enrollment = self._get_or_create_enrollment(user, subj)
                scraped_enrollment_ids.add(enrollment.id)

                self.compare_with_old_values(user, enrollment, subj)
            

            # 2) HARD DELETE enrollments that are in DB but NOT in scrape
            db_enrollments = self.session.execute(
                select(Enrollment).join(Class, Enrollment.class_id == Class.id).where(
                    Enrollment.user_id == user.id,
                    Class.group_id == user.group_id
                )
            ).scalars().all()

            for enr in db_enrollments:
                if enr.id not in scraped_enrollment_ids:
                    self._hard_delete_enrollment(enr)

            self.session.commit()

            final_json["first_name"] = user.first_name
            final_json["last_name"] = user.last_name
            
            save_student_payload_to_redis(
                redis_user_info_cache,user.id,final_json=final_json
            )

            stmt = select(EclassSnapshot).where(EclassSnapshot.user_id == user.id)
            snap = self.session.execute(stmt).scalars().first() 
            if snap:
                snap.payload = final_json
            else:
                snap = EclassSnapshot(user_id=user.id, payload=final_json)
                self.session.add(snap)

            self.session.commit()
            send_message(user_telegram_id=user.telegram_id,message="We are done please click /start")
            redis_registered_users_sync.delete(str(user.id))
            return final_json
        
        except LoginFailed as e:
           
            redis_registered_users_sync.delete(str(user.id))
            
            send_message(user.telegram_id,failed_message)
        except RateLimited as e:
            raise HTTPException(detail="RATE LIMITED:",status_code=400)
        except BlockedOrForbidden as e:
            raise HTTPException("FORBIDDEN/BLOCKED:", status_code=403)
        except AuthExpired as e:
            raise HTTPException(detail="AUTH EXPIRED:", status_code=403)
        except EclassError as e:
            raise HTTPException("E-class ERROR:",status_code=400)
        except Exception as e:
            self.session.rollback()
            return str(e)
    