from fastapi import APIRouter
from app.api.routers import time_table,user,subjects,professor,groups,classes,scraper,e_class,superuser
master_router = APIRouter()

master_router.include_router(time_table.router)
master_router.include_router(user.router)
master_router.include_router(subjects.router)
master_router.include_router(professor.router)
master_router.include_router(groups.router)
master_router.include_router(classes.router)
master_router.include_router(e_class.router)
master_router.include_router(scraper.router)
master_router.include_router(superuser.router)