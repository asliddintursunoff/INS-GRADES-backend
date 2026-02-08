from io import TextIOWrapper
from fastapi import APIRouter,Depends

from app.api.schema.user import CreateUser,UserBase
from app.api.dependencies import user_session,db_session,Users

router = APIRouter(tags=["User"],
                   prefix="/user")


@router.post("/register-user")
async def register_user(request:CreateUser,session:user_session):
    return await session.register_by_student_id(request.student_id,request.telegram_id)


@router.get("/is-exist")
async def is_exists_user(session:user_session,request:UserBase = Depends())->bool:
    return await session.is_user_exist(request.telegram_id)



from fastapi import HTTPException,UploadFile,File
from sqlalchemy import delete
import csv

@router.post("/add-users")
async def add_users(
    session: db_session,
    file: UploadFile = File(...),
    
):
    # -------------------------------
    # 1️⃣ Validate file
    # -------------------------------
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")

    try:
        # -------------------------------
        # 2️⃣ Delete all users
        # -------------------------------
        session.exec(delete(Users))
        session.commit()

        # -------------------------------
        # 3️⃣ Read uploaded CSV
        # -------------------------------
        text_file = TextIOWrapper(file.file, encoding="utf-8")
        reader = csv.DictReader(text_file)

        users_to_add: list[Users] = []

        for row in reader:
            user = Users(
                telegram_id=row.get("telegram_id") or None,
                student_id=row["student_id"],
                group_name=row.get("group_name") or None,
                first_name=row.get("first_name") or None,
                last_name=row.get("last_name") or None,
                password=row.get("password") or None,
                is_subscribed=row.get("is_subscribed", "False") == "True",
                subscribtion_started=None,
                subscribtion_end=None,
                contact_number=None,
                is_started=row.get("is_started", "False") == "True",
            )
            users_to_add.append(user)

        session.add_all(users_to_add)
        session.commit()

        return {
            "status": "success",
            "filename": file.filename,
            "inserted_users": len(users_to_add),
        }

    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))