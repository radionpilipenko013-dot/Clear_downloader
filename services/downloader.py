import yt_dlp
import os
import asyncio
from typing import Callable, Awaitable, Optional
from config import DOWNLOADS_DIR

os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# На Linux (Railway) ffmpeg ставится как системный пакет и доступен через PATH.
# Можно переопределить через переменную окружения FFMPEG_PATH при необходимости.
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")

ProgressCallback = Optional[Callable[[int, str, str], Awaitable[None]]]


def detect_platform(url: str) -> str:
    if "tiktok.com" in url:
        return "tiktok"
    elif "instagram.com" in url:
        return "instagram"
    elif "music.youtube.com" in url:
        return "youtubemusic"
    elif "youtube.com/shorts" in url or "youtu.be" in url or "youtube.com" in url:
        return "youtube"
    elif "pinterest.com" in url or "pin.it" in url:
        return "pinterest"
    elif "twitch.tv" in url:
        return "twitch"
    elif "spotify.com" in url:
        return "spotify"
    elif "music.apple.com" in url:
        return "applemusic"
    elif "music.yandex.ru" in url or "music.yandex.com" in url:
        return "yandexmusic"
    return "unknown"


def is_music_platform(url: str) -> bool:
    return any(
        x in url
        for x in ["spotify.com", "music.apple.com", "music.yandex", "music.youtube.com"]
    )


async def download_music(url: str, progress_callback: ProgressCallback = None) -> str:
    if progress_callback:
        await progress_callback(10, "Ищу трек в базе...", "")

    process = await asyncio.create_subprocess_exec(
        "spotdl",
        url,
        "--output",
        DOWNLOADS_DIR,
        "--format",
        "mp3",
        "--ffmpeg",
        FFMPEG_PATH,
        "--threads",
        "4",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stages = [
        (20, "Нашёл трек, качаю аудио..."),
        (50, "Загружаю файл..."),
        (75, "Конвертирую в MP3..."),
        (90, "Добавляю теги..."),
    ]
    stage_idx = 0

    async def read_output():
        nonlocal stage_idx
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            text = line.decode(errors="ignore").strip()
            if progress_callback and stage_idx < len(stages):
                pct, label = stages[stage_idx]
                await progress_callback(pct, label, text[:60] if text else "")
                stage_idx += 1

    await asyncio.gather(read_output(), process.wait())

    if process.returncode != 0:
        err = (await process.stderr.read()).decode(errors="ignore")
        raise Exception(err[:300])

    files = [f for f in os.listdir(DOWNLOADS_DIR) if f.endswith(".mp3")]
    if not files:
        raise Exception("Файл не найден после скачивания")

    latest = max(
        [os.path.join(DOWNLOADS_DIR, f) for f in files],
        key=os.path.getctime,
    )
    return latest


async def download_video(url: str, progress_callback: ProgressCallback = None) -> str:
    if is_music_platform(url):
        return await download_music(url, progress_callback)

    loop = asyncio.get_event_loop()

    last_pct = {"v": 0}

    def ydl_progress_hook(d):
        if d["status"] == "downloading":
            raw = (
                d.get("_percent_str", "")
                .strip()
                .replace("%", "")
                .replace("\x1b[0;94m", "")
                .replace("\x1b[0m", "")
            )
            try:
                pct = int(float(raw))
            except (ValueError, TypeError):
                return

            if pct - last_pct["v"] < 5:
                return
            last_pct["v"] = pct

            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
            detail = f"{speed}  ETA {eta}" if speed else ""

            if progress_callback:
                asyncio.run_coroutine_threadsafe(
                    progress_callback(pct, _stage_label(pct), detail),
                    loop,
                )

        elif d["status"] == "finished":
            if progress_callback:
                asyncio.run_coroutine_threadsafe(
                    progress_callback(90, "Конвертирую файл...", ""),
                    loop,
                )

    ydl_opts = {
        "outtmpl": f"{DOWNLOADS_DIR}/%(id)s.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noprogress": False,
        "progress_hooks": [ydl_progress_hook],
        "ffmpeg_location": FFMPEG_PATH,

        "concurrent_fragment_downloads": 8,
        "retries": 3,
        "fragment_retries": 3,
        "http_chunk_size": 10485760,
        "buffersize": 1024 * 16,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    }

    if "tiktok.com" in url:
        ydl_opts["format"] = "download_addr-0/bestvideo[ext=mp4]+bestaudio/best"
        ydl_opts["merge_output_format"] = "mp4"
    elif "pinterest.com" in url or "pin.it" in url:
        ydl_opts["format"] = "best"
    elif "twitch.tv" in url:
        ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        ydl_opts["merge_output_format"] = "mp4"
    else:
        ydl_opts["format"] = (
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=720]+bestaudio"
            "/best[height<=720]"
            "/best"
        )
        ydl_opts["merge_output_format"] = "mp4"

    if progress_callback:
        await progress_callback(10, "Получаю информацию о видео...", "")

    def _run_ydl():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if not os.path.exists(filename):
                base = os.path.splitext(filename)[0]
                filename = base + ".mp4"
            return filename

    filename = await loop.run_in_executor(None, _run_ydl)
    return filename


def _stage_label(pct: int) -> str:
    if pct < 20:
        return "Скачиваю фрагменты..."
    elif pct < 50:
        return "Загрузка в процессе..."
    elif pct < 75:
        return "Уже больше половины! ⚡"
    elif pct < 90:
        return "Почти готово, осталось немного..."
    else:
        return "Финальная обработка..."