from fastapi import APIRouter


from app.api.dependencies import current_user,time_table_session



router = APIRouter()





@router.get("/my-timetable")
async def get_my_timetable(current_user:current_user,session:time_table_session):
    result  = await session.my_time_table(current_user)
    return result

