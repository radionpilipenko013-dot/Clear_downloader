import os
import zipfile
from PIL import Image
from pdf2docx import Converter
from docx2pdf import convert as docx2pdf_convert


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
    docx2pdf_convert(input_path, output_path)
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