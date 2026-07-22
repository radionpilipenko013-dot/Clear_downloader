import os
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.filters import CommandStart
from sqlalchemy import select, func, desc
from database import SessionLocal
from database.models import User, Download
from config import ADMIN_ID

router = Router()


async def get_total_users() -> int:
    """Получить общее количество пользователей"""
    async with SessionLocal() as session:
        result = await session.execute(select(func.count(User.tg_id)))
        return result.scalar() or 0


async def get_total_downloads() -> int:
    """Получить общее количество загрузок"""
    async with SessionLocal() as session:
        result = await session.execute(select(func.count(Download.id)))
        return result.scalar() or 0


async def get_downloads_today() -> int:
    """Получить количество загрузок сегодня"""
    async with SessionLocal() as session:
        today = datetime.now().date()
        result = await session.execute(
            select(func.count(Download.id)).where(
                func.date(Download.created_at) == today
            )
        )
        return result.scalar() or 0


async def get_downloads_week() -> int:
    """Получить количество загрузок за неделю"""
    async with SessionLocal() as session:
        week_ago = datetime.now() - timedelta(days=7)
        result = await session.execute(
            select(func.count(Download.id)).where(Download.created_at >= week_ago)
        )
        return result.scalar() or 0


async def get_popular_platforms() -> list[tuple]:
    """Получить самые популярные платформы"""
    async with SessionLocal() as session:
        result = await session.execute(
            select(Download.platform, func.count(Download.id).label("count"))
            .group_by(Download.platform)
            .order_by(desc("count"))
            .limit(5)
        )
        return result.all()


async def get_all_users_info() -> list[dict]:
    """Получить информацию обо всех пользователях"""
    async with SessionLocal() as session:
        users = await session.execute(select(User).order_by(desc(User.tg_id)))
        users_list = []
        for user in users.scalars():
            # Подсчитаем загрузки каждого пользователя
            downloads = await session.execute(
                select(func.count(Download.id)).where(Download.tg_id == user.tg_id)
            )
            user_downloads = downloads.scalar() or 0
            users_list.append(
                {
                    "tg_id": user.tg_id,
                    "username": user.username or "Нет имени",
                    "downloads": user_downloads,
                }
            )
        return users_list


def _admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура главного меню админки"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Общая статистика", callback_data="admin:stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Список пользователей", callback_data="admin:users"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📈 Статистика платформ", callback_data="admin:platforms"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 График за неделю", callback_data="admin:weekly"
                )
            ],
        ]
    )


def _back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для возврата в меню"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="admin:menu")],
        ]
    )


@router.message(CommandStart(), F.from_user.id == ADMIN_ID)
async def cmd_admin(message: Message):
    """Команда /start для админа"""
    await message.answer(
        "🔐 <b>Админ-панель ClearDownloader</b>\n\n"
        "Выбери опцию для просмотра статистики:",
        parse_mode="HTML",
        reply_markup=_admin_keyboard(),
    )


@router.message(F.text == "/admin")
async def admin_command(message: Message):
    """Команда /admin для доступа к админке"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ У тебя нет доступа к этой команде.")
        return

    await message.answer(
        "🔐 <b>Админ-панель ClearDownloader</b>\n\n"
        "Выбери опцию для просмотра статистики:",
        parse_mode="HTML",
        reply_markup=_admin_keyboard(),
    )


@router.callback_query(F.data == "admin:stats", F.from_user.id == ADMIN_ID)
async def show_stats(callback: CallbackQuery):
    """Показать общую статистику"""
    await callback.answer()

    total_users = await get_total_users()
    total_downloads = await get_total_downloads()
    downloads_today = await get_downloads_today()
    downloads_week = await get_downloads_week()

    avg_downloads = round(total_downloads / total_users, 2) if total_users > 0 else 0

    text = (
        f"📊 <b>Общая статистика</b>\n\n"
        f"👥 <b>Всего пользователей:</b> <code>{total_users}</code>\n"
        f"⬇️ <b>Всего загрузок:</b> <code>{total_downloads}</code>\n"
        f"📈 <b>Средний загрузок на юзера:</b> <code>{avg_downloads}</code>\n\n"
        f"📅 <b>За сегодня:</b> <code>{downloads_today}</code> загрузок\n"
        f"📊 <b>За неделю:</b> <code>{downloads_week}</code> загрузок\n"
    )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_back_keyboard(),
    )


@router.callback_query(F.data == "admin:users", F.from_user.id == ADMIN_ID)
async def show_users(callback: CallbackQuery):
    """Показать список пользователей"""
    await callback.answer()

    users = await get_all_users_info()

    if not users:
        await callback.message.edit_text(
            "👥 <b>Пользователей не найдено</b>",
            parse_mode="HTML",
            reply_markup=_back_keyboard(),
        )
        return

    # Разбиваем на части по 10 пользователей
    users_per_page = 10
    text_parts = []

    for i in range(0, len(users), users_per_page):
        chunk = users[i : i + users_per_page]
        text = f"👥 <b>Список пользователей ({i // users_per_page + 1})</b>\n\n"
        for idx, user in enumerate(chunk, 1):
            username_display = (
                f"@{user['username']}"
                if user["username"] != "Нет имени"
                else user["username"]
            )
            text += (
                f"<b>{i + idx}.</b> <code>{user['tg_id']}</code> — {username_display}\n"
                f"   📥 Загрузок: <b>{user['downloads']}</b>\n\n"
            )
        text_parts.append(text)

    # Отправляем первую часть
    await callback.message.edit_text(
        text_parts[0],
        parse_mode="HTML",
        reply_markup=_get_pagination_keyboard(0, len(text_parts)),
    )

    # Сохраняем части для пагинации
    callback.bot._admin_users_pages = text_parts


@router.callback_query(F.data.startswith("admin:users_page:"), F.from_user.id == ADMIN_ID)
async def users_pagination(callback: CallbackQuery):
    """Пагинация пользователей"""
    await callback.answer()

    page = int(callback.data.split(":")[2])
    pages = callback.bot._admin_users_pages

    if 0 <= page < len(pages):
        await callback.message.edit_text(
            pages[page],
            parse_mode="HTML",
            reply_markup=_get_pagination_keyboard(page, len(pages)),
        )


@router.callback_query(F.data == "admin:platforms", F.from_user.id == ADMIN_ID)
async def show_platforms(callback: CallbackQuery):
    """Показать статистику платформ"""
    await callback.answer()

    platforms = await get_popular_platforms()

    if not platforms:
        await callback.message.edit_text(
            "📈 <b>Нет данных о платформах</b>",
            parse_mode="HTML",
            reply_markup=_back_keyboard(),
        )
        return

    platform_emoji = {
        "tiktok": "🎵",
        "instagram": "📸",
        "youtube": "▶️",
        "pinterest": "📌",
        "twitch": "🎮",
        "spotify": "🎧",
        "applemusic": "🍎",
        "yandexmusic": "🎶",
        "youtubemusic": "🎵",
    }

    text = "📈 <b>Популярные платформы</b>\n\n"
    total = sum(count for _, count in platforms)

    for idx, (platform, count) in enumerate(platforms, 1):
        emoji = platform_emoji.get(platform, "🌐")
        percentage = round((count / total) * 100, 1)
        bar = "█" * int(percentage / 5) + "░" * (20 - int(percentage / 5))
        text += (
            f"{idx}. {emoji} <b>{platform.capitalize()}</b>\n"
            f"   <code>[{bar}]</code> {percentage}% ({count})\n\n"
        )

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_back_keyboard(),
    )


@router.callback_query(F.data == "admin:weekly", F.from_user.id == ADMIN_ID)
async def show_weekly(callback: CallbackQuery):
    """Показать график за неделю"""
    await callback.answer()

    async with SessionLocal() as session:
        # Получаем загрузки за каждый день последней недели
        daily_stats = []
        for i in range(6, -1, -1):
            date = (datetime.now() - timedelta(days=i)).date()
            result = await session.execute(
                select(func.count(Download.id)).where(
                    func.date(Download.created_at) == date
                )
            )
            count = result.scalar() or 0
            daily_stats.append((date, count))

    text = "📅 <b>Загрузки за неделю</b>\n\n"
    max_count = max([count for _, count in daily_stats]) or 1

    for date, count in daily_stats:
        day_name = [
            "Пн",
            "Вт",
            "Ср",
            "Чт",
            "Пт",
            "Сб",
            "Вс",
        ][date.weekday()]
        bar_length = int((count / max_count) * 15) if count > 0 else 0
        bar = "█" * bar_length + "░" * (15 - bar_length)
        text += f"{day_name} {date.strftime('%d.%m')}  <code>[{bar}]</code> {count}\n"

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_back_keyboard(),
    )


@router.callback_query(F.data == "admin:menu", F.from_user.id == ADMIN_ID)
async def back_to_menu(callback: CallbackQuery):
    """Вернуться в главное меню"""
    await callback.answer()
    await callback.message.edit_text(
        "🔐 <b>Админ-панель ClearDownloader</b>\n\n"
        "Выбери опцию для просмотра статистики:",
        parse_mode="HTML",
        reply_markup=_admin_keyboard(),
    )


def _get_pagination_keyboard(
    current_page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """Клавиатура пагинации"""
    buttons = []

    if current_page > 0:
        buttons.append(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=f"admin:users_page:{current_page - 1}",
            )
        )

    buttons.append(
        InlineKeyboardButton(
            text=f"{current_page + 1}/{total_pages}",
            callback_data="admin:noop",
        )
    )

    if current_page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton(
                text="Вперёд ➡️",
                callback_data=f"admin:users_page:{current_page + 1}",
            )
        )

    buttons.append(InlineKeyboardButton(text="⬅️ В меню", callback_data="admin:menu"))

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


@router.callback_query(F.data == "admin:noop", F.from_user.id == ADMIN_ID)
async def noop(callback: CallbackQuery):
    """No-op для кнопки номера страницы"""
    await callback.answer()