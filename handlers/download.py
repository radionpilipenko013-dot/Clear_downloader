import os
import asyncio
from aiogram import Router, F
from aiogram.types import (
    Message,
    FSInputFile,
    BufferedInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto,
    InputMediaVideo,
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatType
from services.downloader import download_video, detect_platform, is_music_platform, convert_to_gif, get_video_duration
from services.speach_to_text import (
    transcribe_file,
    recognize_music,
    format_transcription,
    format_music_info,
)
from database import SessionLocal
from database.models import User, Download
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from sqlalchemy import select, func

from handlers.settings import get_user, is_premium_active
from keyboards.inline import stt_keyboard, premium_keyboard, language_keyboard
from locales import t

router = Router()

PLATFORM_EMOJI = {
    "tiktok": "🎵 TikTok",
    "instagram": "📸 Instagram",
    "youtube": "▶️ YouTube",
    "facebook": "📘 Facebook",
    "youtubemusic": "🎵 YouTube Music",
    "spotify": "🎧 Spotify",
}

GROUP_CHAT_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

FREE_YOUTUBE_LIMIT_MIN = 10
PREMIUM_YOUTUBE_LIMIT_MIN = 60

NOT_FOUND_MSG = (
    "😕 <b>По этой ссылке ничего не найдено.</b>\n\n"
    "Проверь, что ссылка правильная и пост/видео доступны публично."
)

_pending_stt: dict[int, str] = {}


def make_progress_bar(percent: int, width: int = 12) -> str:
    filled = int(width * percent / 100)
    return "[" + "█" * filled + "░" * (width - filled) + f"] {percent}%"


def format_progress_msg(
    platform: str, stage: str, percent: int, detail: str = ""
) -> str:
    emoji_name = PLATFORM_EMOJI.get(platform, "🌐 Загрузка")
    bar = make_progress_bar(percent)
    lines = [
        f"⬇️ <b>{emoji_name}</b>",
        "",
        f"<code>{bar}</code>",
        "",
        f"📡 <i>{stage}</i>",
    ]
    if detail:
        lines.append(f"<tg-spoiler>🔍 {detail}</tg-spoiler>")
    return "\n".join(lines)


async def safe_edit(msg: Message, text: str):
    try:
        await msg.edit_text(text, parse_mode="HTML")
    except Exception:
        pass


async def _animate_done(msg: Message):
    await safe_edit(
        msg,
        "✅ <b>Готово!</b>\n\n<code>[████████████] 100%</code>\n\n📦 <i>Файл отправлен</i>",
    )
    await asyncio.sleep(1.8)
    try:
        await msg.delete()
    except Exception:
        pass


async def _send_audio(message: Message, path: str) -> None:
    try:
        tags = ID3(path)
        audio = MP3(path)
        duration = int(audio.info.length)
        title = str(tags.get("TIT2", "Неизвестно"))
        artist = str(tags.get("TPE1", "Неизвестно"))
        album = str(tags.get("TALB", ""))
        caption = f"🎵 <b>{title}</b>\n👤 {artist}"
        if album:
            caption += f"\n💿 {album}"
        apic = tags.get("APIC:")
        kwargs = dict(
            caption=caption,
            parse_mode="HTML",
            duration=duration,
            title=title,
            performer=artist,
        )
        if apic:
            kwargs["thumbnail"] = BufferedInputFile(apic.data, filename="thumb.jpg")
        await message.answer_audio(FSInputFile(path), **kwargs)
    except Exception:
        await message.answer_audio(FSInputFile(path))


async def _send_media_group(message: Message, paths: list[str], is_group: bool) -> None:
    media = []
    for p in paths:
        if p.endswith(IMAGE_EXTS):
            media.append(InputMediaPhoto(media=FSInputFile(p)))
        else:
            media.append(InputMediaVideo(media=FSInputFile(p)))
    if is_group:
        await message.reply_media_group(media)
    else:
        await message.answer_media_group(media)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await get_user(message.from_user.id, message.from_user.username)

    if message.chat.type in GROUP_CHAT_TYPES:
        await message.reply(t("start_group", user.language), parse_mode="HTML")
        return

    if not user.language_selected:
        await message.answer(t("choose_language", user.language), reply_markup=language_keyboard())
        return

    await message.answer(t("start_private", user.language), parse_mode="HTML")


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    user = await get_user(message.from_user.id, message.from_user.username)
    lang = user.language

    async with SessionLocal() as session:
        result = await session.execute(
            select(Download.platform, func.count(Download.id))
            .where(Download.tg_id == message.from_user.id)
            .group_by(Download.platform)
        )
        stats = result.all()

    if not stats:
        await message.answer(
            "📊 <b>Твоя статистика</b>\n\n"
            "Пока пусто — пришли первую ссылку, и здесь появится статистика! 🚀",
            parse_mode="HTML",
        )
        return

    stats_sorted = sorted(stats, key=lambda x: x[1], reverse=True)
    total = sum(count for _, count in stats_sorted)

    lines = ["📊 <b>Твоя статистика скачиваний</b>", ""]
    for platform, count in stats_sorted:
        label = PLATFORM_EMOJI.get(platform, f"🌐 {platform.capitalize()}")
        lines.append(f"{label}: <b>{count}</b>")

    lines.append("")
    lines.append(f"🔥 Всего скачано: <b>{total}</b>")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text.regexp(r"https?://"))
async def handle_link(message: Message):
    url = message.text.strip()
    platform = detect_platform(url)

    user = await get_user(message.from_user.id, message.from_user.username)
    lang = user.language

    if platform == "unknown":
        if message.chat.type in GROUP_CHAT_TYPES:
            return
        await message.answer(t("unsupported_link", lang), parse_mode="HTML")
        return

    is_group = message.chat.type in GROUP_CHAT_TYPES

    if platform == "youtube":
        duration = await get_video_duration(url)
        premium = await is_premium_active(message.from_user.id)
        limit_min = PREMIUM_YOUTUBE_LIMIT_MIN if premium else FREE_YOUTUBE_LIMIT_MIN
        if duration and duration > limit_min * 60:
            await message.answer(
                t(
                    "duration_limit",
                    lang,
                    limit=FREE_YOUTUBE_LIMIT_MIN,
                    premium_limit=PREMIUM_YOUTUBE_LIMIT_MIN,
                ),
                reply_markup=premium_keyboard(lang),
                parse_mode="HTML",
            )
            return

    if is_group:
        msg = await message.reply(
            format_progress_msg(platform, "Подключаюсь к серверу...", 5),
            parse_mode="HTML",
        )
    else:
        msg = await message.answer(
            format_progress_msg(platform, "Подключаюсь к серверу...", 5),
            parse_mode="HTML",
        )

    async def on_progress(percent: int, stage: str, detail: str = ""):
        await safe_edit(msg, format_progress_msg(platform, stage, percent, detail))

    path = None
    error = None

    try:
        path = await download_video(url, progress_callback=on_progress)
        await safe_edit(msg, format_progress_msg(platform, "Отправляю файл...", 95))

        if isinstance(path, list):
            await _send_media_group(message, path, is_group)
        else:
            is_image = path.endswith(IMAGE_EXTS)
            is_gif = path.endswith(".gif")
            is_audio = path.endswith(".mp3")

            if is_audio:
                await _send_audio(message, path)
            elif is_image:
                if is_group:
                    await message.reply_photo(FSInputFile(path))
                else:
                    await message.answer_photo(FSInputFile(path))
            elif is_gif:
                if is_group:
                    await message.reply_animation(FSInputFile(path))
                else:
                    await message.answer_animation(FSInputFile(path))
            else:
                if is_group:
                    await message.reply_video(FSInputFile(path))
                else:
                    await message.answer_video(FSInputFile(path))

            if not is_image and not is_gif and not is_audio:
                _pending_stt[message.from_user.id] = url
                kb = stt_keyboard()
                stt_text = "Что хочешь сделать с файлом?"
                if is_group:
                    await message.reply(stt_text, reply_markup=kb, parse_mode="HTML")
                else:
                    await message.answer(stt_text, reply_markup=kb, parse_mode="HTML")

        await _animate_done(msg)

    except Exception as e:
        error = e
        print(f"[handlers/download.py] Ошибка скачивания {url}: {e}")
        try:
            await msg.edit_text(NOT_FOUND_MSG, parse_mode="HTML")
        except Exception:
            pass
    finally:
        if path:
            paths = path if isinstance(path, list) else [path]
            for p in paths:
                if p and os.path.exists(p):
                    os.remove(p)

    if not error:
        async with SessionLocal() as session:
            session.add(
                Download(tg_id=message.from_user.id, url=url, platform=platform)
            )
            await session.commit()


@router.callback_query(F.data.startswith("gif:"))
async def handle_gif(callback: CallbackQuery):
    await callback.answer()

    url = _pending_stt.get(callback.from_user.id)
    if not url:
        await callback.message.answer("⚠️ Ссылка устарела, отправь её заново.")
        return

    try:
        await callback.message.delete()
    except Exception:
        pass

    status = await callback.message.answer(
        "⬇️ <b>Скачиваю видео для конвертации...</b>",
        parse_mode="HTML",
    )

    video_path = None
    gif_path = None
    try:
        video_path = await asyncio.wait_for(download_video(url), timeout=120)

        if isinstance(video_path, list):
            await safe_edit(status, "⚠️ <b>GIF недоступен для слайдшоу.</b>")
            return

        if video_path.endswith(IMAGE_EXTS):
            await safe_edit(status, "⚠️ <b>Это фото, а не видео — GIF не получится.</b>")
            return

        await safe_edit(status, "🎬 <b>Конвертирую в GIF...</b>")

        gif_path = await asyncio.wait_for(convert_to_gif(video_path), timeout=180)

        await status.delete()
        is_group = callback.message.chat.type in GROUP_CHAT_TYPES
        if is_group:
            await callback.message.reply_animation(FSInputFile(gif_path))
        else:
            await callback.message.answer_animation(FSInputFile(gif_path))

    except asyncio.TimeoutError:
        await safe_edit(
            status,
            "⏱ <b>Превышено время ожидания.</b>\n\nПопробуй позже или с видео покороче.",
        )
    except Exception as e:
        print(f"[handlers/download.py] Ошибка конвертации в GIF: {e}")
        await safe_edit(status, NOT_FOUND_MSG)
    finally:
        for p in (video_path, gif_path):
            if p and isinstance(p, str) and os.path.exists(p):
                os.remove(p)


@router.callback_query(F.data.startswith("stt:"))
async def handle_stt(callback: CallbackQuery):
    await callback.answer()

    url = _pending_stt.get(callback.from_user.id)
    if not url:
        await callback.message.answer("⚠️ Ссылка устарела, отправь её заново.")
        return

    mode = callback.data.split(":")[1]

    try:
        await callback.message.delete()
    except Exception:
        pass

    status = await callback.message.answer(
        "⬇️ <b>Скачиваю файл для анализа...</b>",
        parse_mode="HTML",
    )

    path = None
    try:
        path = await asyncio.wait_for(download_video(url), timeout=120)

        if isinstance(path, list):
            await safe_edit(
                status,
                "⚠️ <b>Распознавание недоступно для слайдшоу.</b>",
            )
            return

        music_mode = mode in ("music", "lyrics")

        if mode == "music":
            await safe_edit(status, "🔍 <b>Определяю трек через Shazam...</b>")
            try:
                info = await asyncio.wait_for(recognize_music(path), timeout=30)

                if info:
                    msg_text = format_music_info(info)

                    if info.get("cover_url"):
                        try:
                            await status.delete()
                            await callback.message.answer_photo(
                                photo=info["cover_url"],
                                caption=msg_text,
                                parse_mode="HTML",
                            )
                        except Exception:
                            await safe_edit(status, msg_text)
                    else:
                        await safe_edit(status, msg_text)

                    await callback.message.answer(
                        "📝 Хочешь ещё и текст песни расшифровать?",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="🎤 Расшифровать текст",
                                        callback_data="stt:lyrics",
                                    )
                                ]
                            ]
                        ),
                    )
                    return

                await safe_edit(
                    status,
                    "🤷 Shazam не распознал трек.\n\n"
                    "🧠 <b>Расшифровываю текст...</b>\n"
                    "<i>Первый запуск загружает модель — подожди 1-2 минуты</i>",
                )

            except asyncio.TimeoutError:
                await safe_edit(
                    status,
                    "⏱ Shazam не ответил вовремя.\n\n"
                    "🧠 <b>Расшифровываю...</b>\n"
                    "<i>Первый запуск загружает модель — подожди 1-2 минуты</i>",
                )
            except ImportError:
                await safe_edit(
                    status,
                    "\n\n"
                    "🧠 Расшифровываю...\n"
                    "<i>Первый запуск загружает модель — подожди 1-2 минуты</i>",
                )

        elif mode == "video":
            await safe_edit(
                status,
                "🧠 <b>Распознаю речь...</b>\n"
                "<i>Первый запуск загружает модель — подожди 1-2 минуты</i>",
            )

        else:
            await safe_edit(
                status,
                "🧠 <b>Расшифровываю текст песни...</b>\n"
                "<i>Первый запуск загружает модель — подожди 1-2 минуты</i>",
            )

        lang_code = None if music_mode else "ru"
        use_timestamps = mode == "video"

        text = await asyncio.wait_for(
            transcribe_file(path, language=lang_code, timestamps=use_timestamps),
            timeout=300,
        )

        if not text:
            await safe_edit(
                status,
                "🤷 <b>Текст не найден</b> — возможно, в файле нет речи или музыки.",
            )
            return

        header = (
            "🎵 <b>Текст песни:</b>" if music_mode else "📝 <b>Расшифровка речи:</b>"
        )

        chunks = format_transcription(text, header)
        await safe_edit(status, chunks[0])
        for chunk in chunks[1:]:
            await callback.message.answer(chunk, parse_mode="HTML")

    except asyncio.TimeoutError:
        await safe_edit(
            status,
            "⏱ <b>Превышено время ожидания.</b>\n\n"
            "Файл слишком большой или сервер перегружен. Попробуй позже.",
        )
    except ImportError:
        await safe_edit(
            status,
            "⚠️ <b>Whisper не установлен.</b>\n\n"
            "<code>pip install openai-whisper</code>",
        )
    except Exception as e:
        print(f"[handlers/download.py] Ошибка распознавания: {e}")
        await safe_edit(status, NOT_FOUND_MSG)
    finally:
        if path:
            paths = path if isinstance(path, list) else [path]
            for p in paths:
                if p and os.path.exists(p):
                    os.remove(p)