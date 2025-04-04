import os
from typing import Optional

import pandas as pd
import pdfkit
import pytesseract
from PIL import Image
from docx import Document
from fpdf import FPDF
import fitz  # PyMuPDF

from core.converter_factory import ConverterFactory


def docx_to_pdf(docx_path: str, output_path: Optional[str] = None) -> str:
    """
    Convert a DOCX file to PDF

    :param docx_path: Path to the DOCX file
    :param output_path: Path for the output PDF file
    :return: Path to the created PDF file
    """
    try:
        # Try to use docx2pdf if available
        from docx2pdf import convert

        if output_path is None:
            output_path = os.path.splitext(docx_path)[0] + ".pdf"

        convert(docx_path, output_path)
        return output_path

    except ImportError:
        # Fallback to using pypandoc if available
        try:
            import pypandoc

            if output_path is None:
                output_path = os.path.splitext(docx_path)[0] + ".pdf"

            pypandoc.convert_file(docx_path, 'pdf', outputfile=output_path)
            return output_path

        except ImportError:
            raise ImportError("Neither docx2pdf nor pypandoc is installed. Please install one of these packages.")


def html_to_pdf(html_path: str, output_path: Optional[str] = None) -> str:
    """
    Convert an HTML file to PDF

    :param html_path: Path to the HTML file
    :param output_path: Path for the output PDF file
    :return: Path to the created PDF file
    """
    if output_path is None:
        output_path = os.path.splitext(html_path)[0] + ".pdf"

    # Convert HTML to PDF using pdfkit (wkhtmltopdf wrapper)
    pdfkit.from_file(html_path, output_path)

    return output_path


def excel_to_pdf(excel_path: str, output_path: Optional[str] = None,
                 sheet_name: Optional[str] = None) -> str:
    """
    Convert an Excel file to PDF

    :param excel_path: Path to the Excel file
    :param output_path: Path for the output PDF file
    :param sheet_name: Name of the sheet to convert (None for all sheets)
    :return: Path to the created PDF file
    """
    if output_path is None:
        output_path = os.path.splitext(excel_path)[0] + ".pdf"

    # Read Excel file
    if sheet_name:
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        dfs = {sheet_name: df}
    else:
        dfs = pd.read_excel(excel_path, sheet_name=None)

    # Create PDF
    pdf = FPDF()

    # Process each sheet
    for sheet, data in dfs.items():
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        # Add sheet name as title
        pdf.cell(200, 10, txt=f"Sheet: {sheet}", ln=True, align='C')
        pdf.ln(5)

        # Get column headers
        cols = data.columns
        col_widths = [40] * len(cols)  # Simple fixed width

        # Add headers
        for i, col in enumerate(cols):
            pdf.cell(col_widths[i], 10, str(col), border=1)
        pdf.ln()

        # Add data rows
        for _, row in data.iterrows():
            for i, col in enumerate(cols):
                value = row[col]
                # Convert various data types to string
                if pd.isna(value):
                    value = ""
                else:
                    value = str(value)
                pdf.cell(col_widths[i], 10, value[:20], border=1)
            pdf.ln()

    # Save the PDF
    pdf.output(output_path)

    return output_path


def image_to_text(image_path: str) -> str:
    """
    Extract text from an image using OCR

    :param image_path: Path to the image file
    :return: Extracted text
    """
    # Use pytesseract for OCR
    image = Image.open(image_path)
    text = pytesseract.image_to_string(image)

    return text


def pdf_to_docx(pdf_path: str, output_path: Optional[str] = None) -> str:
    """
    Convert a PDF file to DOCX

    :param pdf_path: Path to the PDF file
    :param output_path: Path for the output DOCX file
    :return: Path to the created DOCX file
    """
    if output_path is None:
        output_path = os.path.splitext(pdf_path)[0] + ".docx"

    # Create a new Word document
    doc = Document()

    # Extract text from PDF using PyMuPDF
    pdf_document = fitz.open(pdf_path)

    for page_num in range(len(pdf_document)):
        page = pdf_document[page_num]
        # Fix for extract_text method - use the text_page feature
        text = ""
        for block in page.get_text("blocks"):
            text += block[4] + "\n\n"

        # Add page number as heading
        doc.add_heading(f"Page {page_num + 1}", level=1)

        # Add text as paragraphs
        for para in text.split('\n\n'):
            if para.strip():
                doc.add_paragraph(para)

    # Save the Word document
    doc.save(output_path)

    return output_path


def create_csv_from_excel(excel_path: str, output_path: Optional[str] = None,
                          sheet_name: Optional[str] = None) -> str:
    """
    Convert an Excel file to CSV

    :param excel_path: Path to the Excel file
    :param output_path: Path for the output CSV file
    :param sheet_name: Name of the sheet to convert (required)
    :return: Path to the created CSV file
    """
    if sheet_name is None:
        # Use the first sheet if none specified
        sheet_name = pd.ExcelFile(excel_path).sheet_names[0]

    if output_path is None:
        base_name = os.path.splitext(os.path.basename(excel_path))[0]
        output_path = os.path.join(os.path.dirname(excel_path), f"{base_name}_{sheet_name}.csv")

    # Read Excel and write to CSV
    df = pd.read_excel(excel_path, sheet_name=sheet_name)
    df.to_csv(output_path, index=False)

    return output_path


def text_to_html(text_path: str, output_path: Optional[str] = None,
                 title: str = "Converted Document") -> str:
    """
    Convert a plain text file to HTML

    :param text_path: Path to the text file
    :param output_path: Path for the output HTML file
    :param title: Title for the HTML document
    :return: Path to the created HTML file
    """
    if output_path is None:
        output_path = os.path.splitext(text_path)[0] + ".html"

    # Read the text file
    with open(text_path, 'r', encoding='utf-8') as file:
        content = file.read()

    # Fix possible typo at line 224 with proper HTML content creation
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 40px; }}
        h1 {{ color: #333; }}
        p {{ margin-bottom: 15px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    {''.join(f'<p>{para}</p>' for para in content.split('\n\n') if para.strip())}
</body>
</html>
"""

    # Write HTML file
    with open(output_path, 'w', encoding='utf-8') as file:
        file.write(html_content)

    return output_path


# Fix for Unexpected argument error
# Instead of using a function, register converters directly
ConverterFactory.register('docx_to_pdf', docx_to_pdf)
ConverterFactory.register('html_to_pdf', html_to_pdf)
ConverterFactory.register('excel_to_pdf', excel_to_pdf)
ConverterFactory.register('image_to_text', image_to_text)
ConverterFactory.register('pdf_to_docx', pdf_to_docx)
ConverterFactory.register('create_csv_from_excel', create_csv_from_excel)
ConverterFactory.register('text_to_html', text_to_html)