import os
import subprocess
import zipfile
from PIL import Image
from pdf2docx import Converter


def images_to_pdf(image_paths: list[str], output_path: str) -> str:
    images = [Image.open(path).convert("RGB") for path in image_paths]
    first, rest = images[0], images[1:]
    first.save(output_path, save_all=True, append_images=rest)
    return output_path


def pdf_to_docx(input_path: str, output_path: str) -> str:
    converter = Converter(input_path)
    converter.convert(output_path)
    converter.close()
    return output_path


def docx_to_pdf(input_path: str, output_path: str) -> str:
    """
    Конвертация DOCX -> PDF через LibreOffice в headless-режиме.
    Требует установленного пакета libreoffice в системе (см. railpack-plan.json).
    """
    output_dir = os.path.dirname(output_path) or "."
    os.makedirs(output_dir, exist_ok=True)

    result = subprocess.run(
        [
            "libreoffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            output_dir,
            input_path,
        ],
        capture_output=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise Exception(
            f"LibreOffice conversion failed: {result.stderr.decode(errors='ignore')[:300]}"
        )

    generated = os.path.join(
        output_dir, os.path.splitext(os.path.basename(input_path))[0] + ".pdf"
    )

    if not os.path.exists(generated):
        raise Exception("LibreOffice did not produce the expected output file")

    if generated != output_path:
        os.replace(generated, output_path)

    return output_path


def files_to_zip(file_paths: list[str], output_path: str) -> str:
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in file_paths:
            zf.write(path, arcname=os.path.basename(path))
    return output_path


def extract_zip(input_path: str, extract_dir: str) -> list[str]:
    os.makedirs(extract_dir, exist_ok=True)
    extracted = []
    with zipfile.ZipFile(input_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            safe_name = os.path.basename(name)
            if not safe_name:
                continue
            target = os.path.join(extract_dir, safe_name)
            with zf.open(name) as src, open(target, "wb") as dst:
                dst.write(src.read())
            extracted.append(target)
    return extracted