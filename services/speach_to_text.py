import asyncio
import os
from typing import Optional


WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
SHAZAM_MIN_SCORE = 0.3

FFMPEG_PATH = os.getenv(
    "FFMPEG_PATH",
    r"C:\Users\User\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin",
)
FFMPEG_EXE = os.path.join(FFMPEG_PATH, "ffmpeg.exe")


def _inject_ffmpeg_to_path():
    if FFMPEG_PATH and os.path.isdir(FFMPEG_PATH):
        current = os.environ.get("PATH", "")
        if FFMPEG_PATH not in current:
            os.environ["PATH"] = FFMPEG_PATH + os.pathsep + current
    if os.path.isfile(FFMPEG_EXE):
        os.environ["FFMPEG_BINARY"] = FFMPEG_EXE
        os.environ["FFMPEG_PATH"] = FFMPEG_EXE


async def transcribe_file(
    path: str,
    language: Optional[str] = None,
    timestamps: bool = False,
    model_name: str = WHISPER_MODEL,
) -> str:
    try:
        import whisper
    except ImportError:
        raise ImportError(
            "openai-whisper не установлен.\nУстанови: pip install openai-whisper"
        )

    if not os.path.exists(path):
        raise FileNotFoundError(f"Файл не найден: {path}")

    _inject_ffmpeg_to_path()

    loop = asyncio.get_event_loop()

    def _run() -> str:
        _inject_ffmpeg_to_path()

        model = whisper.load_model(model_name)

        options: dict = {"fp16": False}
        if language:
            options["language"] = language

        result = model.transcribe(path, **options)

        if not timestamps:
            return result.get("text", "").strip()

        segments = result.get("segments", [])
        if not segments:
            return result.get("text", "").strip()

        lines = []
        for seg in segments:
            start = int(seg["start"])
            mm, ss = divmod(start, 60)
            lines.append(f"[{mm:02d}:{ss:02d}] {seg['text'].strip()}")

        return "\n".join(lines)

    text = await loop.run_in_executor(None, _run)
    return text


async def recognize_music(path: str) -> Optional[dict]:
    try:
        from ShazamAPI import Shazam
    except ImportError:
        raise ImportError("ShazamAPI не установлен.\nУстанови: pip install ShazamAPI")

    if not os.path.exists(path):
        raise FileNotFoundError(f"Файл не найден: {path}")

    loop = asyncio.get_event_loop()

    def _run():
        with open(path, "rb") as f:
            mp3_data = f.read()

        shazam = Shazam(mp3_data)
        result = shazam.recognizeSong()

        try:
            out = next(result)
        except StopIteration:
            return None

        if not out or not out[1].get("track"):
            return None

        track = out[1]["track"]

        metadata = track.get("sections", [{}])[0].get("metadata", [])
        meta_map = {
            item["title"].lower(): item["text"]
            for item in metadata
            if "title" in item and "text" in item
        }

        images = track.get("images", {})
        cover_url = images.get("coverarthq") or images.get("coverart")

        return {
            "title": track.get("title"),
            "artist": track.get("subtitle"),
            "album": meta_map.get("album"),
            "year": meta_map.get("released"),
            "genre": track.get("genres", {}).get("primary"),
            "cover_url": cover_url,
            "score": 1.0,
        }

    return await loop.run_in_executor(None, _run)


def format_transcription(text: str, header: str = "📝 Расшифровка речи:") -> list[str]:
    if not text:
        return []
    full = f"{header}\n\n{text}"
    return [full[i : i + 3800] for i in range(0, len(full), 3800)]


def format_music_info(info: dict) -> str:
    lines = [
        "🎵 <b>Распознан трек:</b>",
        "",
        f"🎤 <b>Исполнитель:</b> {info['artist'] or '—'}",
        f"🎵 <b>Название:</b> {info['title'] or '—'}",
    ]
    if info.get("album"):
        lines.append(f"💿 <b>Альбом:</b> {info['album']}")
    if info.get("year"):
        lines.append(f"📅 <b>Год:</b> {info['year']}")
    if info.get("genre"):
        lines.append(f"🎸 <b>Жанр:</b> {info['genre']}")
    return "\n".join(lines)