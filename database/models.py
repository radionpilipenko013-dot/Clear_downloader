from sqlalchemy import Column, Integer, String, DateTime, Boolean, func
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    language = Column(String, default="ru", nullable=False)
    language_selected = Column(Boolean, default=False, nullable=False)
    is_premium = Column(Boolean, default=False, nullable=False)
    premium_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())


class Download(Base):
    __tablename__ = "downloads"
    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, nullable=False)
    url = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())


class Stories(Base):
    __tablename__ = "stories"
    id = Column(Integer, primary_key=True)