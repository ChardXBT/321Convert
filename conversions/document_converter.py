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


from xhtml2pdf import pisa
import openpyxl
from openpyxl import Workbook

def html_to_pdf(html_input, output_path):
    """
    Convert HTML to PDF using xhtml2pdf

    Parameters:
    html_input (str): Either HTML content as a string or a path to an HTML file
    output_path (str): Path where the output PDF will be saved

    Returns:
    bool: True if successful, False otherwise
    """
    try:
        # Check if html_input is a file path
        if os.path.isfile(html_input):
            with open(html_input, 'r', encoding='utf-8') as html_file:
                html_content = html_file.read()
        else:
            # Assume html_input is the actual HTML content
            html_content = html_input

        # Create PDF
        with open(output_path, "w+b") as result_file:
            pisa_status = pisa.CreatePDF(
                src=html_content,
                dest=result_file,
                encoding='utf-8'
            )

        # Check if PDF generation was successful
        success = not pisa_status.err
        if success:
            print(f"Successfully converted HTML to PDF: {output_path}")
        else:
            print(f"Error converting HTML to PDF: {pisa_status.err}")

        return success
    except Exception as e:
        print(f"HTML to PDF conversion failed: {str(e)}")
        return False

def data_to_excel(data, output_path):
    """
    `data` should be a list of lists:
    [
        ["Name", "Age", "City"],
        ["Alice", 30, "Toronto"],
        ["Bob", 25, "Vancouver"]
    ]
    """
    wb = Workbook()
    ws = wb.active
    for row in data:
        ws.append(row)
    wb.save(output_path)
    return True


def excel_to_pdf(excel_path, **kwargs):
    """
    Convert Excel to PDF using xhtml2pdf

    Parameters:
    excel_path (str): Path to the Excel file
    **kwargs:
        sheet_name (str, optional): Specific sheet to convert
        output_path (str): Path where the output PDF will be saved

    Returns:
    str: Path to the generated PDF file
    """
    sheet_name = kwargs.get('sheet_name')
    output_path = kwargs.get('output_path')

    try:
        # Verify the input file exists
        if not os.path.isfile(excel_path):
            raise FileNotFoundError(f"Excel file not found: {excel_path}")

        # Verify the output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Read the Excel file
        if sheet_name:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
        else:
            # If no sheet specified, read the first sheet
            df = pd.read_excel(excel_path)

        if df.empty:
            raise ValueError("Excel sheet is empty.")

        # Convert DataFrame to HTML with better styling
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    font-family: Arial, sans-serif;
                }}
                th, td {{
                    border: 1px solid #dddddd;
                    text-align: left;
                    padding: 8px;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
                tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
            </style>
        </head>
        <body>
            {df.to_html(index=False)}
        </body>
        </html>
        """

        # Convert HTML to PDF using xhtml2pdf
        from xhtml2pdf import pisa
        with open(output_path, "w+b") as result_file:
            pisa_status = pisa.CreatePDF(
                src=html_content,
                dest=result_file,
                encoding='utf-8'
            )

        # Check if PDF generation was successful
        if pisa_status.err:
            raise ValueError(f"PDF generation failed: {pisa_status.err}")

        if not os.path.exists(output_path):
            raise ValueError("PDF generation failed. Output file not found.")

        return output_path

    except Exception as e:
        # Ensure the error message is detailed
        error_message = f"Error converting Excel to PDF: {str(e)}"
        print(error_message)
        raise ValueError(error_message)


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
    """
    Convert Excel to CSV

    Parameters:
    excel_path (str): Path to the Excel file
    **kwargs:
        sheet_name (str, optional): Specific sheet to convert
        output_path (str): Path where the output CSV will be saved
        all_sheets (bool, optional): If True, convert all sheets to separate CSV files

    Returns:
    str or list: Path to the generated CSV file(s)
    """
    sheet_name = kwargs.get('sheet_name')
    output_path = kwargs.get('output_path')
    all_sheets = kwargs.get('all_sheets', False)

    try:
        # Verify the input file exists
        if not os.path.isfile(excel_path):
            raise FileNotFoundError(f"Excel file not found: {excel_path}")

        # Verify the output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Handle all sheets if requested
        if all_sheets:
            # Get all sheet names
            excel = pd.ExcelFile(excel_path)
            sheet_names = excel.sheet_names
            output_files = []

            # Base filename without extension
            base_name = os.path.splitext(output_path)[0]

            # Convert each sheet
            for sheet in sheet_names:
                df = pd.read_excel(excel_path, sheet_name=sheet)

                if not df.empty:
                    # Create sheet-specific output path
                    sheet_output = f"{base_name}_{sheet}.csv"
                    df.to_csv(sheet_output, index=False)
                    output_files.append(sheet_output)

            return output_files

        # Handle single sheet conversion
        else:
            # Read the Excel file
            if sheet_name:
                df = pd.read_excel(excel_path, sheet_name=sheet_name)
            else:
                # If no sheet specified, read the first sheet
                df = pd.read_excel(excel_path)

            if df.empty:
                raise ValueError("Excel sheet is empty.")

            # Convert to CSV
            df.to_csv(output_path, index=False, encoding='utf-8')

            if not os.path.exists(output_path):
                raise ValueError("CSV generation failed. Output file not found.")

            return output_path

    except Exception as e:
        # Ensure the error message is detailed
        error_message = f"Error converting Excel to CSV: {str(e)}"
        print(error_message)
        raise ValueError(error_message)


def text_to_html(text_path, **kwargs):
    """Convert plain text to HTML"""
    output_path = kwargs.get('output_path')
    title = kwargs.get('title', 'Converted Document')

    try:
        # Read the text file
        with open(text_path, 'r', encoding='utf-8') as f:
            text_content = f.read()

        # Convert to simple HTML
        paragraphs = text_content.split('\n\n')
        formatted_paragraphs = "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs if paragraph.strip())

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
    {formatted_paragraphs}
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