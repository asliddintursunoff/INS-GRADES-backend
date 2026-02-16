import json
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select


from app.infra.redis_async import redis_user_info_cache_async,redis_registered_users
from app.scraper.script import AuthExpired, BlockedOrForbidden, EclassClient, EclassError, LoginFailed, RateLimited, pack_student_rest
from app.services.scraping import ScrapService
from app.worker.tasks import take_info_from_eclass_one_user
from app.database.models import User,EclassSnapshot
from app.utils import send_message
from app.database.session_sync import get_sync_session
from app.scraper.script import EclassClient

from sqlalchemy.ext.asyncio import AsyncSession

from typing import Dict, Any
from html import escape



class EClassService():
    def __init__(self,session:AsyncSession):
        self.session = session

    async def register_load_data(self,user:User):
        if user.password == None:
            raise HTTPException(detail="password is not found",status_code=404)
        
        
        def do_scrape():
                data = take_info_from_eclass_one_user.delay(user.id)
                return data
        try:
            
            if  not await redis_registered_users.exists(str(user.id)):
                
                await redis_registered_users.setex(str(user.id),60*60,value="is waiting")
                do_scrape()

            
                return {
                "detail": (
                    "⏳ <b>We’re preparing your data…</b>\n\n"
                    "It looks like this is your first time using the bot or your session has expired.\n"
                    "We are now setting up your E-class information.\n\n"
                    "🕒 This may take <b>1–15 minutes</b>.\n"
                    
                    "🔔 We will send you a notification once everything is ready."
                )
            }

            return {
                "detail": (
                    f"⏳ <b>Please wait, {user.first_name}…</b>\n\n"
                    "Your data setup is already in progress.\n"
                    "It may take up to <b>15 minutes</b>.\n\n"
                    "🔔 You will receive a notification as soon as everything is ready."
                )
            }


  
        except LoginFailed as e:
           
            raise HTTPException(detail="LOGIN FAILED",status_code=403)
        except RateLimited as e:
            raise HTTPException(detail="RATE LIMITED:",status_code=400)
        except BlockedOrForbidden as e:
            raise HTTPException("FORBIDDEN/BLOCKED:", status_code=403)
        except AuthExpired as e:
            raise HTTPException(detail="AUTH EXPIRED:", status_code=403)
        except EclassError as e:
            raise HTTPException("E-class ERROR:",status_code=400)
    
            
    async def get_my_eclass_enfo(self,user:User):
        
        cached = await redis_user_info_cache_async.get(str(user.id))

        if cached:
            return json.loads(cached)
        
        stmt = await self.session.execute(
            select(EclassSnapshot).where(EclassSnapshot.user_id == user.id)
        )
        info = stmt.scalar_one_or_none()

        if not info:
            return HTTPException(status_code=403,detail="User is not found\nCauses from:deleted by user or session expired.\nPlease register again click /start")
        

        await redis_user_info_cache_async.set(str(user.id), json.dumps(info.payload),  ex=60*60*120)

        return info.payload
        
        



        
        
        
    








def full_attendance_message(data: Dict[str, Any]) -> str:
    """
    Builds a beautiful Telegram HTML message showing attendance for all subjects.
    Expects data like:
    {
      "student_id": "...",
      "first_name": "...",
      "last_name": "...",
      "subjects": [
        {"subject": "...", "subject_name": "...", "attendance": {"attendance":0,"absence":0,"late":0}, ...},
        ...
      ]
    }
    """

    first_name = escape(str(data.get("first_name") or ""))
    last_name = escape(str(data.get("last_name") or ""))
    student_id = escape(str(data.get("student_id") or ""))

    subjects = data.get("subjects") or []

    header_name = (first_name + " " + last_name).strip()
    if not header_name:
        header_name = "Student"

    lines = []
    lines.append("📚 <b>Attendance Summary</b>")
    lines.append(f"👤 <b>{header_name}</b>  •  🎓 <code>{student_id}</code>")
    lines.append("")

    if not subjects:
        lines.append("No subjects found.")
        return "\n".join(lines)

    # Totals
  

    # Sort: show worst first (absence desc, late desc)
    def sort_key(s):
        a = s.get("attendance") or {}
        return (-int(a.get("absence") or 0), -int(a.get("late") or 0))

    subjects_sorted = sorted(subjects, key=sort_key)

    for idx, s in enumerate(subjects_sorted, start=1):
        code = escape(str(s.get("subject") or ""))
        name = escape(str(s.get("subject_name") or ""))
        prof = escape(str(s.get("professor_name") or ""))

        a = s.get("attendance") or {}
        att = int(a.get("attendance") or 0)
        absn = int(a.get("absence") or 0)
        late = int(a.get("late") or 0)

     

        # small status emoji
        if absn > 0:
            status = "🔴"
        elif late > 0:
            status = "🟠"
        else:
            status = "🟢"

        title = f"{status} <b>{code}</b>"
        if name:
            title += f" — {name}"

        lines.append(title)
        if prof:
            lines.append(f"👨‍🏫 <i>{prof}</i>")

        # numbers line (aligned-ish)
        lines.append(
            f"✅ Attended: <b>{att}</b>   "
            f"❌ Absent: <b>{absn}</b>   "
            f"⏳ Late: <b>{late}</b>"
        )

        

        # divider (pretty but not too long)
        if idx != len(subjects_sorted):
            lines.append("────────────")
        else:
            lines.append("")


    return "\n".join(lines)