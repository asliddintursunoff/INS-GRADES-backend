from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
class NgrokSkipBrowserWarningMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["ngrok-skip-browser-warning"] = "true"
        return response
    




origins = [
    "https://ins-admin-frontend.vercel.app",
    # "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(master_router)

