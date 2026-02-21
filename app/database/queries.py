from .connection import get_pool

async def insert_query(telegram_id,username,password):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (telegram_id,student_id,password)" \
            "VALUES" \
            "($1,$2,$3)",
            telegram_id,
            username,
            password
        )
    return {"status":"created","status_code":200}



async def select_query(telegram_id:str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM users WHERE telegram_id = $1",
            telegram_id
        )
        if not result:
            return None
        
        info = {
            "status_code":200,
            "student_id":result["student_id"],
            "password":result["password"]
        }
        return info
      
