from fastapi import FastAPI
from rich import panel,print
from .database.session import create_db_tables
from app.api.router import master_router


async def life_cycle(app:FastAPI):
    print(panel.Panel("DB Tables created",border_style="green"))
    yield await create_db_tables()
    print(panel.Panel("BYE",border_style="red"))

app = FastAPI(
    lifespan=life_cycle,
    
)

app.include_router(master_router)

