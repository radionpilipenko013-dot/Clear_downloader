import os
import uuid
import asyncio
from aiogram import Router, F
from aiogram.types import Message, FSInputFile, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from services.converter import (
    images_to_pdf,
    pdf_to_docx,
    docx_to_pdf,
    files_to_zip,
)
from config import DOWNLOADS_DIR

router = Router()

MODE_PHOTO_PDF = "photo_pdf"
MODE_PHOTO_ZIP = "photo_zip"
MODE_PDF_DOCX = "pdf_docx"
MODE_DOCX_PDF = "docx_pdf"

_convert_mode: dict[int, str] = {}
_convert_photos: dict[int, list[str]] = {}
_pending_file: dict[int, tuple[str, str]] = {}
_awaiting_name: dict[int, bool] = {}


def convert_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Фото → PDF", callback_data=f"conv_{MODE_PHOTO_PDF}")],
        [InlineKeyboardButton(text="🗜 Фото → ZIP", callback_data=f"conv_{MODE_PHOTO_ZIP}")],
        [InlineKeyboardButton(text="📄 PDF → DOCX", callback_data=f"conv_{MODE_PDF_DOCX}")],
        [InlineKeyboardButton(text="📝 DOCX → PDF", callback_data=f"conv_{MODE_DOCX_PDF}")],
        [InlineKeyboardButton(text="◀ В меню", callback_data="conv_cancel")],
    ])


def skip_name_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="conv_skip_name")]
    ])


def _clear_state(user_id: int):
    photos = _convert_photos.pop(user_id, [])
    for photo in photos:
        if os.path.exists(photo):
            os.remove(photo)
    pending = _pending_file.pop(user_id, None)
    if pending and os.path.exists(pending[0]):
        os.remove(pending[0])
    _convert_mode.pop(user_id, None)
    _awaiting_name.pop(user_id, None)


async def in_convert_mode(message: Message) -> bool:
    return _convert_mode.get(message.from_user.id) in (MODE_PHOTO_PDF, MODE_PHOTO_ZIP)


async def in_single_file_mode(message: Message) -> bool:
    return _convert_mode.get(message.from_user.id) in (MODE_PDF_DOCX, MODE_DOCX_PDF)


async def is_awaiting_name(message: Message) -> bool:
    return _awaiting_name.get(message.from_user.id, False)


@router.message(Command("convert"))
async def cmd_convert(message: Message):
    user_id = message.from_user.id
    _clear_state(user_id)
    await message.answer(
        "🔄 <b>Выбери тип конвертации:</b>",
        parse_mode="HTML",
        reply_markup=convert_menu_kb(),
    )


@router.callback_query(F.data == "conv_cancel")
async def cb_cancel(callback: CallbackQuery):
    user_id = callback.from_user.id
    _clear_state(user_id)
    await callback.message.edit_text("❌ Конвертация отменена.")
    await callback.answer()


@router.callback_query(F.data == "conv_skip_name")
async def cb_skip_name(callback: CallbackQuery):
    user_id = callback.from_user.id
    await callback.message.delete()
    await _send_pending_file(callback.message, user_id, None)
    await callback.answer()


@router.callback_query(F.data.startswith("conv_") & ~F.data.in_({"conv_cancel", "conv_skip_name"}))
async def cb_select_mode(callback: CallbackQuery):
    user_id = callback.from_user.id
    mode = callback.data.removeprefix("conv_")
    _convert_mode[user_id] = mode
    _convert_photos[user_id] = []
    _pending_file.pop(user_id, None)
    _awaiting_name[user_id] = False

    if mode in (MODE_PHOTO_PDF, MODE_PHOTO_ZIP):
        text = "📸 Скидывай фото по одной.\nКогда закончишь, напиши /done."
    elif mode == MODE_PDF_DOCX:
        text = "📄 Скинь PDF файл для конвертации в DOCX."
    else:
        text = "📝 Скинь DOCX файл для конвертации в PDF."

    await callback.message.edit_text(text)
    await callback.answer()


@router.message(F.photo, in_convert_mode)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    path = os.path.join(DOWNLOADS_DIR, f"{uuid.uuid4().hex}.jpg")
    await message.bot.download_file(file.file_path, path)

    _convert_photos.setdefault(user_id, []).append(path)
    count = len(_convert_photos[user_id])
    await message.answer(f"✅ Фото добавлено ({count}). Ещё, или /done, когда закончишь.")


@router.message(Command("done"))
async def cmd_done(message: Message):
    user_id = message.from_user.id
    mode = _convert_mode.get(user_id)

    if mode not in (MODE_PHOTO_PDF, MODE_PHOTO_ZIP):
        await message.answer("⚠️ Сначала выбери тип конвертации через /convert")
        return

    photos = _convert_photos.get(user_id, [])
    if not photos:
        await message.answer("⚠️ Ты не отправил ни одного фото.")
        return

    as_zip = mode == MODE_PHOTO_ZIP
    ext = ".zip" if as_zip else ".pdf"
    output_path = os.path.join(DOWNLOADS_DIR, f"{uuid.uuid4().hex}{ext}")

    try:
        if as_zip:
            await asyncio.to_thread(files_to_zip, photos, output_path)
        else:
            await asyncio.to_thread(images_to_pdf, photos, output_path)
    except Exception as e:
        await message.answer(f"❌ <b>Ошибка:</b> <code>{e}</code>", parse_mode="HTML")
        _clear_state(user_id)
        return

    for photo in photos:
        if os.path.exists(photo):
            os.remove(photo)
    _convert_photos[user_id] = []

    _pending_file[user_id] = (output_path, ext)
    _awaiting_name[user_id] = True
    await message.answer(
        "✍️ Введи имя файла (без расширения) или нажми Пропустить.",
        reply_markup=skip_name_kb(),
    )


@router.message(F.document, in_single_file_mode)
async def handle_document(message: Message):
    user_id = message.from_user.id
    mode = _convert_mode.get(user_id)
    doc = message.document
    file_name = doc.file_name or ""
    ext = os.path.splitext(file_name)[1].lower()

    expected_ext = ".pdf" if mode == MODE_PDF_DOCX else ".docx"
    if ext != expected_ext:
        await message.answer(f"⚠️ Ожидается файл с расширением {expected_ext}")
        return

    file = await message.bot.get_file(doc.file_id)
    input_path = os.path.join(DOWNLOADS_DIR, f"{uuid.uuid4().hex}{ext}")
    await message.bot.download_file(file.file_path, input_path)

    status = await message.answer("🔄 <b>Конвертирую...</b>", parse_mode="HTML")

    try:
        if mode == MODE_PDF_DOCX:
            output_path = input_path.replace(ext, ".docx")
            await asyncio.to_thread(pdf_to_docx, input_path, output_path)
            out_ext = ".docx"
        else:
            output_path = input_path.replace(ext, ".pdf")
            await asyncio.to_thread(docx_to_pdf, input_path, output_path)
            out_ext = ".pdf"
    except Exception as e:
        await status.edit_text(f"❌ <b>Ошибка:</b> <code>{e}</code>", parse_mode="HTML")
        if os.path.exists(input_path):
            os.remove(input_path)
        _clear_state(user_id)
        return

    if os.path.exists(input_path):
        os.remove(input_path)

    await status.delete()
    _pending_file[user_id] = (output_path, out_ext)
    _awaiting_name[user_id] = True
    await message.answer(
        "✍️ Введи имя файла (без расширения) или нажми Пропустить.",
        reply_markup=skip_name_kb(),
    )


async def _send_pending_file(target, user_id: int, name: str | None):
    pending = _pending_file.pop(user_id, None)
    if not pending:
        return
    output_path, ext = pending
    final_name = f"{name}{ext}" if name else os.path.basename(output_path)
    try:
        await target.answer_document(FSInputFile(output_path, filename=final_name))
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)
        _clear_state(user_id)


@router.message(is_awaiting_name)
async def handle_file_name(message: Message):
    user_id = message.from_user.id
    name = message.text.strip() if message.text else None
    if not name:
        await message.answer("⚠️ Введи текстовое имя файла или нажми Пропустить.")
        return
    await _send_pending_file(message, user_id, name)