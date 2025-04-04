import os
import pandas as pd
import pytesseract
from PIL import Image
from core.converter_factory import ConverterFactory


def docx_to_pdf(docx_path, **kwargs):
    """
    Convert DOCX to PDF using external library (requires python-docx2pdf)

    Note: This is a placeholder. You'll need to install docx2pdf or another library
    """
    output_path = kwargs.get('output_path')

    try:
        from docx2pdf import convert
        convert(docx_path, output_path)
        return output_path
    except ImportError:
        raise ImportError("docx2pdf library is required for DOCX to PDF conversion")


def html_to_pdf(html_path, **kwargs):
    """
    Convert HTML to PDF using external library (requires pdfkit)

    Note: This is a placeholder. You'll need to install pdfkit and wkhtmltopdf
    """
    output_path = kwargs.get('output_path')

    try:
        import pdfkit
        pdfkit.from_file(html_path, output_path)
        return output_path
    except ImportError:
        raise ImportError("pdfkit library is required for HTML to PDF conversion")


def excel_to_pdf(excel_path, **kwargs):
    """
    Convert Excel to PDF

    Note: This is a placeholder. Full implementation depends on available libraries.
    """
    sheet_name = kwargs.get('sheet_name')
    output_path = kwargs.get('output_path')

    # Simplified implementation - in a real application you'd use a proper Excel to PDF converter
    try:
        # Read the Excel file
        if sheet_name:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
        else:
            df = pd.read_excel(excel_path)

        # Convert to HTML first
        html_file = os.path.join(os.path.dirname(output_path), "temp.html")
        df.to_html(html_file)

        # Then convert HTML to PDF
        import pdfkit
        pdfkit.from_file(html_file, output_path)

        # Clean up temporary file
        if os.path.exists(html_file):
            os.remove(html_file)

        return output_path
    except ImportError:
        raise ImportError("pandas and pdfkit libraries are required for Excel to PDF conversion")


def pdf_to_docx(pdf_path, **kwargs):
    """
    Convert PDF to DOCX

    Note: This is a placeholder. You'd need a library like pdf2docx
    """
    output_path = kwargs.get('output_path')

    try:
        from pdf2docx import Converter
        print(f"[DEBUG] Input PDF path: {pdf_path}")
        print(f"[DEBUG] Output DOCX path: {output_path}")

        cv = Converter(pdf_path)
        cv.convert(output_path)
        cv.close()

        print(f"[DEBUG] Output file exists: {os.path.exists(output_path)}")
        print(f"[DEBUG] Output absolute path: {os.path.abspath(output_path)}")

        return output_path
    except ImportError:
        raise ImportError("pdf2docx library is required for PDF to DOCX conversion")


def create_csv_from_excel(excel_path, **kwargs):
    """Convert Excel to CSV"""
    sheet_name = kwargs.get('sheet_name')
    output_path = kwargs.get('output_path')

    try:
        # Read the Excel file
        if sheet_name:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
        else:
            df = pd.read_excel(excel_path)

        # Save as CSV
        df.to_csv(output_path, index=False)
        return output_path
    except Exception as e:
        raise ValueError(f"Error converting Excel to CSV: {str(e)}")


def text_to_html(text_path, **kwargs):
    """Convert plain text to HTML"""
    output_path = kwargs.get('output_path')
    title = kwargs.get('title', 'Converted Document')

    try:
        # Read the text file
        with open(text_path, 'r', encoding='utf-8') as f:
            text_content = f.read()

        # Convert to simple HTML
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #333; }}
        p {{ margin-bottom: 16px; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    {''.join(f'<p>{paragraph}</p>' for paragraph in text_content.split('\n\n') if paragraph.strip())}
</body>
</html>"""

        # Save HTML file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return output_path
    except Exception as e:
        raise ValueError(f"Error converting text to HTML: {str(e)}")


def image_to_text(image_path, **kwargs):
    """Extract text from image using OCR"""
    output_path = kwargs.get('output_path')

    try:
        # Use pytesseract for OCR
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)

        # Save to file if output path is provided
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(text)

        return text
    except Exception as e:
        raise ValueError(f"Error extracting text from image: {str(e)}")


# Register document converters
ConverterFactory.register('docx_to_pdf', docx_to_pdf)
ConverterFactory.register('html_to_pdf', html_to_pdf)
ConverterFactory.register('excel_to_pdf', excel_to_pdf)
ConverterFactory.register('pdf_to_docx', pdf_to_docx)
ConverterFactory.register('create_csv_from_excel', create_csv_from_excel)
ConverterFactory.register('text_to_html', text_to_html)
ConverterFactory.register('image_to_text', image_to_text)