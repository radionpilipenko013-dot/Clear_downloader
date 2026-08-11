import os
import glob
import shutil
import time
import asyncio
from typing import Callable, Awaitable, Optional, Union
from shutil import which

import yt_dlp

from config import DOWNLOADS_DIR


def _bootstrap_windows_tools():
    if shutil.which("ffmpeg") and shutil.which("aria2c"):
        return

    local_appdata = os.environ.get("LOCALAPPDATA", "")
    search_patterns = [
        os.path.join(local_appdata, "Microsoft", "WinGet", "Links"),
        os.path.join(local_appdata, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "**", "bin"),
        os.path.join(local_appdata, "Microsoft", "WinGet", "Packages", "aria2.aria2*", "**"),
        r"C:\ffmpeg\bin",
        r"C:\aria2",
    ]

    found_dirs = set()
    for pattern in search_patterns:
        if "*" in pattern:
            for match in glob.glob(pattern, recursive=True):
                if os.path.isdir(match):
                    found_dirs.add(match)
        elif os.path.isdir(pattern):
            found_dirs.add(pattern)

    current_path = os.environ.get("PATH", "")
    for d in found_dirs:
        if d not in current_path:
            current_path += os.pathsep + d
    os.environ["PATH"] = current_path


_bootstrap_windows_tools()
print("=" * 50)
print("[downloader.py] Проверка ffmpeg/aria2c при старте:")
print(f"  ffmpeg  -> {shutil.which('ffmpeg')}")
print(f"  aria2c  -> {shutil.which('aria2c')}")
print("=" * 50)

os.makedirs(DOWNLOADS_DIR, exist_ok=True)


def _resolve_ffmpeg_path() -> str:
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path and (os.path.isfile(env_path) or shutil.which(env_path)):
        return env_path
    if env_path:
        print(f"[downloader.py] ВНИМАНИЕ: FFMPEG_PATH='{env_path}' из .env не найден на диске, игнорирую его.")

    auto = shutil.which("ffmpeg")
    if auto:
        return auto

    return "ffmpeg"


FFMPEG_PATH = _resolve_ffmpeg_path()
print(f"[downloader.py] Итоговый FFMPEG_PATH, который будет передан в yt-dlp: {FFMPEG_PATH}")

COOKIES_PATH = os.path.join(os.path.dirname(__file__), "www.youtube.com_cookies.txt")
print(f"[downloader.py] cookies.txt найден -> {os.path.exists(COOKIES_PATH)}")

ProgressCallback = Optional[Callable[[int, str, str], Awaitable[None]]]

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

YOUTUBE_PLAYER_CLIENTS = ["android", "ios", "web"]


def _has_aria2c() -> bool:
    return which("aria2c") is not None


HAS_ARIA2C = _has_aria2c()


def detect_platform(url: str) -> str:
    if "tiktok.com" in url:
        return "tiktok"
    elif "instagram.com" in url:
        return "instagram"
    elif "music.youtube.com" in url:
        return "youtubemusic"
    elif "youtube.com/shorts" in url or "youtu.be" in url or "youtube.com" in url:
        return "youtube"
    elif "facebook.com" in url or "fb.watch" in url:
        return "facebook"
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


def is_tiktok_photo(url: str) -> bool:
    return "tiktok.com" in url and "/photo/" in url


def is_tiktok_story(url: str) -> bool:
    return "tiktok.com" in url and "/story/" in url


def is_instagram_story(url: str) -> bool:
    return "instagram.com" in url and "/stories/" in url


async def get_video_duration(url: str) -> Optional[int]:
    loop = asyncio.get_event_loop()

    def _extract():
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extractor_args": {
                "youtube": {
                    "player_client": YOUTUBE_PLAYER_CLIENTS,
                }
            },
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            },
        }
        if os.path.exists(COOKIES_PATH):
            opts["cookiefile"] = COOKIES_PATH
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    return None
                return info.get("duration")
        except Exception:
            return None

    return await loop.run_in_executor(None, _extract)


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


def _resolve_file(ydl, info) -> Optional[str]:
    filename = ydl.prepare_filename(info)
    if os.path.exists(filename):
        return filename
    base = os.path.splitext(filename)[0]
    for ext in IMAGE_EXTS + (".mp4", ".gif"):
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
    return None


async def download_video(url: str, progress_callback: ProgressCallback = None) -> Union[str, list]:
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
                if progress_callback and last_pct["v"] < 50:
                    last_pct["v"] = 50
                    asyncio.run_coroutine_threadsafe(
                        progress_callback(50, "Качаю на максимальной скорости...", ""),
                        loop,
                    )
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

    is_tiktok = "tiktok.com" in url
    is_instagram = "instagram.com" in url

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": False,
        "progress_hooks": [ydl_progress_hook],
        "ffmpeg_location": FFMPEG_PATH,
        "concurrent_fragment_downloads": 4 if (is_tiktok or is_instagram) else 8,
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 5,
        "socket_timeout": 30,
        "http_chunk_size": 10485760,
        "buffersize": 1024 * 16,
        "extractor_args": {
            "youtube": {
                "player_client": YOUTUBE_PLAYER_CLIENTS,
            }
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    }

    if os.path.exists(COOKIES_PATH):
        ydl_opts["cookiefile"] = COOKIES_PATH

    if HAS_ARIA2C:
        ydl_opts["external_downloader"] = "aria2c"
        ydl_opts["external_downloader_args"] = {
            "aria2c": [
                "-x", "8",
                "-s", "8",
                "-k", "1M",
                "--min-split-size=1M",
                "--disable-ipv6=true",
                "--max-tries=5",
                "--retry-wait=2",
                "--connect-timeout=15",
            ]
        }

    if is_tiktok:
        if is_tiktok_photo(url) or is_tiktok_story(url):
            ydl_opts["outtmpl"] = f"{DOWNLOADS_DIR}/%(id)s_%(playlist_index)s.%(ext)s"
            ydl_opts["format"] = "best"
        else:
            ydl_opts["outtmpl"] = f"{DOWNLOADS_DIR}/%(id)s.%(ext)s"
            ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best"
            ydl_opts["merge_output_format"] = "mp4"
    elif is_instagram:
        ydl_opts["outtmpl"] = f"{DOWNLOADS_DIR}/%(id)s_%(playlist_index)s.%(ext)s"
        ydl_opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        ydl_opts["merge_output_format"] = "mp4"
    elif "facebook.com" in url or "fb.watch" in url:
        ydl_opts["outtmpl"] = f"{DOWNLOADS_DIR}/%(id)s.%(ext)s"
        ydl_opts["format"] = (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
            "/best[ext=mp4]"
            "/best"
        )
        ydl_opts["merge_output_format"] = "mp4"
    else:
        ydl_opts["outtmpl"] = f"{DOWNLOADS_DIR}/%(id)s.%(ext)s"
        ydl_opts["format"] = (
            "bestvideo[height<=720]+bestaudio"
            "/best[height<=720]"
            "/best"
        )
        ydl_opts["merge_output_format"] = "mp4"

    if progress_callback:
        await progress_callback(10, "Получаю информацию о видео...", "")

    def _run_ydl():
        def _attempt(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = None
                last_err = None
                for attempt in range(3):
                    try:
                        info = ydl.extract_info(url, download=True)
                        break
                    except yt_dlp.utils.DownloadError as e:
                        last_err = e
                        if attempt < 2:
                            time.sleep(2 * (attempt + 1))
                            continue
                        raise
                if info is None:
                    raise last_err or Exception("Не удалось получить информацию о видео")

                if "entries" in info and info["entries"]:
                    files = []
                    for entry in info["entries"]:
                        if entry is None:
                            continue
                        fn = _resolve_file(ydl, entry)
                        if fn:
                            files.append(fn)
                    if files:
                        return files if len(files) > 1 else files[0]
                    raise Exception("Не удалось найти скачанные файлы слайдшоу")

                filename = _resolve_file(ydl, info)
                if not filename:
                    raise Exception("Файл не найден после скачивания")
                return filename

        try:
            return _attempt(ydl_opts)
        except yt_dlp.utils.DownloadError as e:
            if "external_downloader" in ydl_opts and "aria2c" in str(e).lower():
                fallback_opts = {k: v for k, v in ydl_opts.items()
                                  if k not in ("external_downloader", "external_downloader_args")}
                return _attempt(fallback_opts)
            if "Requested format is not available" in str(e):
                fallback_opts = dict(ydl_opts)
                fallback_opts["format"] = "best"
                fallback_opts.pop("external_downloader", None)
                fallback_opts.pop("external_downloader_args", None)
                return _attempt(fallback_opts)
            raise

    result = await loop.run_in_executor(None, _run_ydl)
    return result


async def convert_to_gif(video_path: str, fps: int = 12, width: int = 480) -> str:
    out_path = os.path.splitext(video_path)[0] + "_converted.gif"
    palette_path = os.path.splitext(video_path)[0] + "_palette.png"

    filters = f"fps={fps},scale={width}:-1:flags=lanczos"

    palette_cmd = [
        FFMPEG_PATH, "-y", "-i", video_path,
        "-vf", f"{filters},palettegen",
        palette_path,
    ]
    gif_cmd = [
        FFMPEG_PATH, "-y", "-i", video_path, "-i", palette_path,
        "-lavfi", f"{filters}[x];[x][1:v]paletteuse",
        out_path,
    ]

    for cmd in (palette_cmd, gif_cmd):
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            if os.path.exists(palette_path):
                os.remove(palette_path)
            raise Exception(stderr.decode(errors="ignore")[:300])

    if os.path.exists(palette_path):
        os.remove(palette_path)

    if not os.path.exists(out_path):
        raise Exception("GIF не был создан")

    return out_path


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