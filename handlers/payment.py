from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from aiogram.filters import Command
from datetime import datetime, timedelta
from sqlalchemy import select

from database import SessionLocal
from database.models import User
from handlers.settings import get_user_language
from locales import t
from keyboards.inline import premium_keyboard

router = Router()

PREMIUM_PRICE_STARS = 10
PREMIUM_DAYS = 30


@router.message(Command("pro", "premium"))
async def cmd_premium(message: Message):
    lang = await get_user_language(message.from_user.id)
    await message.answer(t("premium_info", lang), reply_markup=premium_keyboard(lang), parse_mode="HTML")


@router.callback_query(F.data == "premium:buy")
async def handle_premium_buy(callback: CallbackQuery):
    await callback.answer()
    lang = await get_user_language(callback.from_user.id)
    await callback.message.answer_invoice(
        title=t("premium_invoice_title", lang),
        description=t("premium_invoice_description", lang),
        payload="premium_30days",
        currency="XTR",
        prices=[LabeledPrice(label=t("premium_invoice_title", lang), amount=PREMIUM_PRICE_STARS)],
        provider_token="",
    )


@router.pre_checkout_query(F.invoice_payload == "premium_30days")
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


# ИСПРАВЛЕНО: было F.successful_payment.func(lambda p: p.invoice_payload == "premium_30days")
# Этот фильтр вызывал лямбду даже когда message.successful_payment is None (на любом обычном
# сообщении), из-за чего p.invoice_payload падал с AttributeError на КАЖДОМ апдейте в чате.
# Теперь сначала проверяем, что платёж вообще есть (F.successful_payment), а payload
# сравниваем внутри функции.
@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    if message.successful_payment.invoice_payload != "premium_30days":
        return

    now = datetime.utcnow()
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == message.from_user.id))
        user = result.scalar_one_or_none()
        if user:
            base = user.premium_until if user.premium_until and user.premium_until > now else now
            user.is_premium = True
            user.premium_until = base + timedelta(days=PREMIUM_DAYS)
            lang = user.language or "ru"
        else:
            user = User(
                tg_id=message.from_user.id,
                username=message.from_user.username,
                is_premium=True,
                premium_until=now + timedelta(days=PREMIUM_DAYS),
            )
            session.add(user)
            lang = "ru"
        await session.commit()

    await message.answer(t("premium_success", lang), parse_mode="HTML")