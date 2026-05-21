from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config import DB_URL
from database.models import Base

engine = create_async_engine(DB_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with SessionLocal() as session:
        yield session
