from fastapi import APIRouter
from app.api.routers import time_table,user
master_router = APIRouter()

master_router.include_router(time_table.router)
master_router.include_router(user.router)