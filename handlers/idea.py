from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMIN_ID

router = Router()


class IdeaState(StatesGroup):
    waiting_for_idea = State()

@router.message(Command("idea"))
async def cmd_idea(message: Message, state: FSMContext):
    await state.set_state(IdeaState.waiting_for_idea)
    await message.answer(
        "💡 <b>Есть идея для бота?</b>\n\n"
        "Напиши что хотел бы видеть — новые платформы, функции, улучшения.\n\n"
        "<i>Отправь /cancel чтобы отменить.</i>",
        parse_mode="HTML",
    )


@router.message(Command("cancel"), IdeaState.waiting_for_idea)
async def cmd_cancel_idea(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.", parse_mode="HTML")


@router.message(IdeaState.waiting_for_idea, F.text)
async def receive_idea(message: Message, state: FSMContext):
    await state.clear()

    user = message.from_user
    username = f"@{user.username}" if user.username else "без username"
    full_name = user.full_name or "Без имени"

    idea_text = (
        f"💡 <b>Новая идея для бота!</b>\n\n"
        f"👤 <b>От:</b> {full_name} ({username})\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n\n"
        f"📝 <b>Идея:</b>\n{message.text}"
    )


    try:
        await message.bot.send_message(ADMIN_ID, idea_text, parse_mode="HTML")
    except Exception:
        pass  

    await message.answer(
        "✅ <b>Спасибо! Идея отправлена разработчику.</b>\n\n"
        "🚀 <i>Рассмотрим при следующем обновлении!</i>",
        parse_mode="HTML",
    )
