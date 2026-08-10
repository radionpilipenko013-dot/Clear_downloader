from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from datetime import datetime

from database import SessionLocal
from database.models import User
from keyboards.inline import language_keyboard
from locales import t, LANGUAGES

router = Router()


async def get_user(tg_id: int, username: str | None = None) -> User:
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
        if user:
            return user
        user = User(tg_id=tg_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def get_user_language(tg_id: int) -> str:
    user = await get_user(tg_id)
    return user.language or "ru"


async def is_premium_active(tg_id: int) -> bool:
    user = await get_user(tg_id)
    if not user.is_premium:
        return False
    if user.premium_until and user.premium_until < datetime.utcnow():
        return False
    return True


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    lang = await get_user_language(message.from_user.id)
    await message.answer(t("settings_menu", lang), reply_markup=language_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("setlang:"))
async def handle_set_language(callback: CallbackQuery):
    lang_code = callback.data.split(":")[1]
    if lang_code not in LANGUAGES:
        await callback.answer()
        return

    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            user.language = lang_code
            user.language_selected = True
        else:
            user = User(
                tg_id=callback.from_user.id,
                username=callback.from_user.username,
                language=lang_code,
                language_selected=True,
            )
            session.add(user)
        await session.commit()

    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass

    is_start_flow = callback.message.chat.type == "private"
    if is_start_flow:
        await callback.message.answer(t("start_private", lang_code), parse_mode="HTML")
    else:
        await callback.message.answer(t("language_set", lang_code), parse_mode="HTML")