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
)
from aiogram.filters import CommandStart
from aiogram.enums import ChatType
from services.downloader import download_video, detect_platform, is_music_platform
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

router = Router()

PLATFORM_EMOJI = {
    "tiktok": "🎵 TikTok",
    "instagram": "📸 Instagram",
    "youtube": "▶️ YouTube",
    "pinterest": "📌 Pinterest",
    "twitch": "🎮 Twitch",
    "youtubemusic": "🎵 YouTube Music",
}

GROUP_CHAT_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}

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


def _stt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎵 Распознать текст музыки", callback_data="stt:music"),
        ],
        [
            InlineKeyboardButton(text="📝 Распознать речь", callback_data="stt:video"),
        ],
    ])


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


async def _ensure_user(tg_id: int, username: str | None):
    async with SessionLocal() as session:
        from sqlalchemy import select

        result = await session.execute(select(User).where(User.tg_id == tg_id))
        if not result.scalar_one_or_none():
            session.add(User(tg_id=tg_id, username=username))
            await session.commit()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await _ensure_user(message.from_user.id, message.from_user.username)

    if message.chat.type in GROUP_CHAT_TYPES:
        await message.reply(
            "👋 <b>ClearDownloader здесь!</b>\n\n"
            "Просто скинь ссылку — скачаю видео или музыку 🚀\n\n"
            "📹 TikTok · Reels · YouTube · Twitch\n"
            "🖼 Pinterest\n\n"
            "💡 <i>Для полной справки напиши мне в личку.</i>",
            parse_mode="HTML",
        )
        return

    await message.answer(
        "👋 <b>Привет! Я ClearDownloader — твой умный бот-загрузчик!</b>\n\n"
        "Просто отправь мне ссылку на видео или трек, и я скачаю его на "
        "турбо-скорости 🚀\n\n"
        "📊 <b>Я покажу индикатор загрузки в реальном времени, а также:</b>\n"
        "📹 Видео из <b>TikTok, Reels, YouTube Shorts, Twitch</b> — <i>полностью без водяных знаков!</i>\n"
        "🖼 Контент из <b>Pinterest</b> — <i>фото и GIF.</i>\n\n"
        "📝 <b>AI-фишка:</b> Распознаю и прикреплю текст из видео к твоему файлу!\n\n"
        "⚡ <i>Жду твою первую ссылку...</i>",
        parse_mode="HTML",
    )


@router.message(F.text.regexp(r"https?://"))
async def handle_link(message: Message):
    url = message.text.strip()
    platform = detect_platform(url)

    await _ensure_user(message.from_user.id, message.from_user.username)

    if platform == "unknown":
        if message.chat.type in GROUP_CHAT_TYPES:
            return
        await message.answer("❌ <b>Ссылка не поддерживается.</b>", parse_mode="HTML")
        return

    is_group = message.chat.type in GROUP_CHAT_TYPES

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

        is_image = path.endswith((".jpg", ".jpeg", ".png", ".webp"))
        is_gif = path.endswith(".gif")

        if path.endswith(".mp3"):
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

        if not is_image and not is_gif:
            _pending_stt[message.from_user.id] = url
            kb = _stt_keyboard()
            stt_text = "Что хочешь сделать с файлом?"
            if is_group:
                await message.reply(stt_text, reply_markup=kb, parse_mode="HTML")
            else:
                await message.answer(stt_text, reply_markup=kb, parse_mode="HTML")

        await _animate_done(msg)

    except Exception as e:
        error = e
        try:
            await msg.edit_text(
                f"❌ <b>Ошибка:</b> <code>{e}</code>", parse_mode="HTML"
            )
        except Exception:
            pass
    finally:
        if path and os.path.exists(path):
            os.remove(path)

    if not error:
        async with SessionLocal() as session:
            session.add(
                Download(tg_id=message.from_user.id, url=url, platform=platform)
            )
            await session.commit()


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
                    "🧠 <b>Расшифровываю текст через Whisper...</b>\n"
                    "<i>Первый запуск загружает модель — подожди 1-2 минуты</i>",
                )

            except asyncio.TimeoutError:
                await safe_edit(
                    status,
                    "⏱ Shazam не ответил вовремя.\n\n"
                    "🧠 <b>Пробую Whisper...</b>\n"
                    "<i>Первый запуск загружает модель — подожди 1-2 минуты</i>",
                )
            except ImportError:
                await safe_edit(
                    status,
                    "\n\n"
                    "🧠 Пробую Whisper...\n"
                    "<i>Первый запуск загружает модель — подожди 1-2 минуты</i>",
                )

        elif mode == "video":
            await safe_edit(
                status,
                "🧠 <b>Распознаю речь через Whisper...</b>\n"
                "<i>Первый запуск загружает модель — подожди 1-2 минуты</i>",
            )

        else:  # lyrics
            await safe_edit(
                status,
                "🧠 <b>Расшифровываю текст песни через Whisper...</b>\n"
                "<i>Первый запуск загружает модель — подожди 1-2 минуты</i>",
            )

        lang = None if music_mode else "ru"
        use_timestamps = mode == "video"

        text = await asyncio.wait_for(
            transcribe_file(path, language=lang, timestamps=use_timestamps),
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
        await safe_edit(
            status,
            f"❌ <b>Ошибка распознавания:</b>\n<code>{e}</code>",
        )
    finally:
        if path and os.path.exists(path):
            os.remove(path)