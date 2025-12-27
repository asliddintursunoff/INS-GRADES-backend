import asyncio
import asyncpg
import dotenv
import os
dotenv.load_dotenv()

db_url = os.getenv("DB_LINK")
pool :asyncpg.Pool| None= None

async def connect_db():
    global pool
    pool = await asyncpg.create_pool(
        dsn = db_url,
        min_size=1,
        max_size=5
    )
    

async def disconnect_db():
    await pool.close()
    

async def get_pool():
    return pool
