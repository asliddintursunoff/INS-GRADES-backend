from fastapi import APIRouter
from app.api.dependencies import current_user_with_password,eclass_session


router = APIRouter(
    tags=["E-class"],
    prefix="/e-class"
)

@router.get("/register")
async def register_eclass(user:current_user_with_password,service:eclass_session):
    return await service.register_load_data(user)


@router.get("/get-my-attendance")
async def get_my_eclass_info(user:current_user_with_password,service:eclass_session):
    return await service.get_my_eclass_enfo(user)