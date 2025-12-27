from fastapi import FastAPI,Body,HTTPException,status
from schema.user_info import User
from automation.get_gpa_dict import getting_gpa_dict
from db.connection import connect_db,disconnect_db
from db.queries import insert_query,select_query
from typing import Optional
import re

app = FastAPI()

@app.post("/get-GPA-table")
async def getting_GPA_table(telegram_id:str =Body(...),
                            studentId:Optional[str]= Body(None),
                            password:Optional[str] = Body(None)):
    
    try:
        info = await select_query(telegram_id)
        if not info:
            


            if not re.fullmatch(r"[Uu]\d{7}", studentId):
                raise ValueError(
                    "studentId must start with 'U' or 'u' followed by 7 digits"
                )
            
            if len(password) < 8:
                raise ValueError("Password must be at least 8 characters long")

            if not re.search(r"[A-Z]", password):
                raise ValueError("Password must contain at least one uppercase letter")

            if not re.search(r"\d", password):
                raise ValueError("Password must contain at least one number")

            
        else:
            studentId = info.get("student_id")
            password = info.get("password")
        data = await getting_gpa_dict(studentId,password)
        print(data)
        if not info and data["status_code"] != 403:
            await insert_query(telegram_id,studentId,password)

        return data
    except ValueError as e:
        return {"status_code":422,"error":str(e)}



@app.post("/user-info")
async def get_user(telegram_id:str =Body(...,embed=True)):
    
    data =  await select_query(telegram_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user not found"
        )
    return data

    

@app.on_event("startup")
async def startup():
    await connect_db()

@app.on_event("shutdown")
async def shutdown():
    await disconnect_db()