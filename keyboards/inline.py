from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from locales import LANGUAGES, t


def platform_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ]
    )


def language_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"setlang:{code}")]
        for code, label in LANGUAGES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def premium_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t("buy_premium_button", lang), callback_data="premium:buy")]
    ])


def stt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎵 Музыка", callback_data="stt:music"),
            InlineKeyboardButton(text="📝 Речь", callback_data="stt:video"),
        ],
        [
            InlineKeyboardButton(text="🎬 GIF", callback_data="gif:make"),
        ],
    ])