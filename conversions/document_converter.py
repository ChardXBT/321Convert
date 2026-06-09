import html
import os
import tempfile
from pathlib import Path

import pandas as pd
from docx import Document
from docxcompose.composer import Composer
from openpyxl import load_workbook
from pypdf import PdfReader
from xhtml2pdf import pisa

from core.converter_factory import ConverterFactory


MAX_PDF_PAGES = 150
MAX_SPREADSHEET_CELLS = 500_000
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def html_to_pdf(html_input, output_path=None, **_kwargs):
    """Render uploaded HTML as inert text, preventing scripts and remote fetches."""
    if not output_path:
        raise ValueError("An output path is required.")
    content = Path(html_input).read_text(encoding="utf-8", errors="replace")
    safe_document = f"<html><body><pre>{html.escape(content)}</pre></body></html>"
    with open(output_path, "w+b") as result_file:
        status = pisa.CreatePDF(src=safe_document, dest=result_file, encoding="utf-8")
    if status.err:
        raise ValueError("PDF generation failed.")
    return output_path


def read_spreadsheet(excel_path, sheet_name=None):
    workbook = load_workbook(excel_path, read_only=True, data_only=True, keep_links=False)
    try:
        if sheet_name and sheet_name not in workbook.sheetnames:
            raise ValueError("The requested sheet does not exist.")
        sheet = workbook[sheet_name] if sheet_name else workbook.active
        if sheet.max_row * sheet.max_column > MAX_SPREADSHEET_CELLS:
            raise ValueError("The spreadsheet contains too many cells.")
    finally:
        workbook.close()
    frame = pd.read_excel(excel_path, sheet_name=sheet_name) if sheet_name else pd.read_excel(excel_path)
    if frame.size > MAX_SPREADSHEET_CELLS:
        raise ValueError("The spreadsheet contains too many cells.")
    return frame


def excel_to_pdf(excel_path, **kwargs):
    output_path = kwargs.get("output_path")
    frame = read_spreadsheet(excel_path, kwargs.get("sheet_name"))
    if frame.empty:
        raise ValueError("The selected sheet is empty.")
    table = frame.to_html(index=False, escape=True)
    document = f"""
    <html><head><style>
    table {{ border-collapse: collapse; width: 100%; font-family: sans-serif; }}
    th, td {{ border: 1px solid #bbb; padding: 5px; text-align: left; }}
    th {{ background: #f3e6d8; }}
    </style></head><body>{table}</body></html>
    """
    with open(output_path, "w+b") as result_file:
        status = pisa.CreatePDF(src=document, dest=result_file, encoding="utf-8")
    if status.err:
        raise ValueError("PDF generation failed.")
    return output_path


def pdf_to_docx(pdf_path, **kwargs):
    output_path = kwargs.get("output_path") or str(Path(pdf_path).with_suffix(".docx"))
    reader = PdfReader(pdf_path)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported.")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError(f"PDFs are limited to {MAX_PDF_PAGES} pages.")

    with tempfile.TemporaryDirectory(prefix="321convert-pdf-") as temp_dir:
        chunks = []
        for start in range(0, len(reader.pages), 10):
            document = Document()
            for page_number in range(start, min(start + 10, len(reader.pages))):
                document.add_heading(f"Page {page_number + 1}", level=2)
                document.add_paragraph(reader.pages[page_number].extract_text() or "")
            chunk_path = os.path.join(temp_dir, f"chunk_{start}.docx")
            document.save(chunk_path)
            chunks.append(chunk_path)

        if not chunks:
            Document().save(output_path)
        else:
            master = Document(chunks[0])
            composer = Composer(master)
            for chunk in chunks[1:]:
                composer.append(Document(chunk))
            composer.save(output_path)
    return output_path


def create_csv_from_excel(excel_path, **kwargs):
    output_path = kwargs.get("output_path")
    frame = read_spreadsheet(excel_path, kwargs.get("sheet_name"))
    frame = frame.map(neutralize_formula)
    frame.to_csv(output_path, index=False, encoding="utf-8")
    return output_path


def neutralize_formula(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value


def text_to_html(text_path, **kwargs):
    output_path = kwargs.get("output_path")
    title = html.escape(kwargs.get("title", "Converted Document"))
    content = html.escape(Path(text_path).read_text(encoding="utf-8", errors="replace"))
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:800px;margin:40px auto;padding:0 20px}}pre{{white-space:pre-wrap}}</style>
</head><body><h1>{title}</h1><pre>{content}</pre></body></html>"""
    Path(output_path).write_text(document, encoding="utf-8")
    return output_path


ConverterFactory.register("html_to_pdf", html_to_pdf)
ConverterFactory.register("excel_to_pdf", excel_to_pdf)
ConverterFactory.register("pdf_to_docx", pdf_to_docx)
ConverterFactory.register("create_csv_from_excel", create_csv_from_excel)
ConverterFactory.register("text_to_html", text_to_html)
