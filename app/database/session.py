from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession
from sqlmodel import SQLModel
from contextlib import asynccontextmanager
from sqlalchemy.orm import sessionmaker
from app.config import db_settings

engine = create_async_engine(
    url=db_settings.ASYNC_DB_URL
)

async def create_db_tables():
    async with engine.begin() as connection:
        from app.database import models
        await connection.run_sync(SQLModel.metadata.create_all)


async def get_session():
    async_session =  sessionmaker(
        bind = engine,class_=AsyncSession,expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        
@asynccontextmanager
async def get_session_ctx():
    async_session = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with async_session() as session:
        yield session

