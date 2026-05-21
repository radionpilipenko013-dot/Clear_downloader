import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from database.models import Base
from config import DB_URL


async def init():
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("DB initialized")


asyncio.run(init())
