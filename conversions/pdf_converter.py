import os
import fitz  # PyMuPDF
from PIL import Image
import zipfile
from core.converter_factory import ConverterFactory


# Register PDF converters with the ConverterFactory

def pdf_to_images(pdf_path, **kwargs):
    """Convert PDF to images"""
    dpi = kwargs.get('dpi', 300)
    format = kwargs.get('format', 'PNG')
    output_path = kwargs.get('output_path', os.path.dirname(pdf_path))

    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Open the PDF
    pdf_document = fitz.open(pdf_path)
    result_files = []

    # Convert each page to an image
    for page_num in range(len(pdf_document)):
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))

        # Define output image path
        img_filename = f"page_{page_num + 1}.{format.lower()}"
        img_path = os.path.join(os.path.dirname(output_path), img_filename)

        # Save the image
        pix.save(img_path)
        result_files.append(img_path)

    pdf_document.close()
    return result_files


def extract_text_from_pdf(pdf_path, **kwargs):
    """Extract text from PDF"""
    output_path = kwargs.get('output_path')

    # Open the PDF
    pdf_document = fitz.open(pdf_path)
    text = ""

    # Extract text from each page
    for page_num in range(len(pdf_document)):
        page = pdf_document.load_page(page_num)
        text += page.get_text()

    pdf_document.close()

    # Save to file if output path is provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)

    return text


def compress_pdf(pdf_path, **kwargs):
    """Compress PDF"""
    quality = kwargs.get('quality', 'medium')
    output_path = kwargs.get('output_path')

    # Quality settings (adjust as needed)
    quality_settings = {
        'high': [120, 'deflate', 95],
        'medium': [100, 'deflate', 75],
        'low': [80, 'deflate', 60]
    }

    dpi, compress_method, jpeg_quality = quality_settings.get(quality, quality_settings['medium'])

    # Open the PDF
    pdf_document = fitz.open(pdf_path)

    # Save with compression settings
    pdf_document.save(
        output_path,
        garbage=4,  # Clean up unused objects
        deflate=True,  # Use deflate compression
        clean=True  # Clean content streams
    )

    pdf_document.close()
    return output_path


def rotate_pdf_pages(pdf_path, **kwargs):
    """Rotate pages in a PDF"""
    rotation = kwargs.get('rotation', 90)
    pages = kwargs.get('pages', [])
    output_path = kwargs.get('output_path')

    # Open the PDF
    pdf_document = fitz.open(pdf_path)

    # If no specific pages are provided, rotate all pages
    if not pages:
        pages = list(range(1, len(pdf_document) + 1))

    # Convert page numbers to 0-based index
    page_indices = [p - 1 for p in pages if 0 < p <= len(pdf_document)]

    # Rotate specified pages
    for page_idx in page_indices:
        page = pdf_document[page_idx]
        page.set_rotation(rotation)

    # Save the rotated PDF
    pdf_document.save(output_path)
    pdf_document.close()

    return output_path


def encrypt_pdf(pdf_path, **kwargs):
    """Encrypt a PDF with a password"""
    password = kwargs.get('password', '')
    owner_password = kwargs.get('owner_password', password)
    output_path = kwargs.get('output_path')

    # Open the PDF
    pdf_document = fitz.open(pdf_path)

    # Set encryption
    pdf_document.save(
        output_path,
        encryption=fitz.PDF_ENCRYPT_AES_256,  # Use AES 256-bit encryption
        user_pw=password,
        owner_pw=owner_password,
        permissions=fitz.PDF_PERM_PRINT  # Allow printing only
    )

    pdf_document.close()
    return output_path


def decrypt_pdf(pdf_path, **kwargs):
    """Decrypt a PDF with a password"""
    password = kwargs.get('password', '')
    output_path = kwargs.get('output_path')

    # Open the PDF with the password
    pdf_document = fitz.open(pdf_path, password=password)

    # Save without encryption
    pdf_document.save(output_path)
    pdf_document.close()

    return output_path


def images_to_pdf(image_paths, **kwargs):
    """Convert images to PDF"""
    output_path = kwargs.get('output_path')

    # Create a new PDF
    pdf_document = fitz.open()

    for img_path in image_paths:
        # Open the image
        img = fitz.open(img_path)

        # Convert image to PDF page
        pdf_bytes = img.convert_to_pdf()
        img.close()

        # Create a new PDF from the image
        img_pdf = fitz.open("pdf", pdf_bytes)

        # Add the page to our PDF
        pdf_document.insert_pdf(img_pdf)
        img_pdf.close()

    # Save the PDF
    pdf_document.save(output_path)
    pdf_document.close()

    return output_path


# Register all converters
ConverterFactory.register('pdf_to_images', pdf_to_images)
ConverterFactory.register('extract_text_from_pdf', extract_text_from_pdf)
ConverterFactory.register('compress_pdf', compress_pdf)
ConverterFactory.register('rotate_pdf_pages', rotate_pdf_pages)
ConverterFactory.register('encrypt_pdf', encrypt_pdf)
ConverterFactory.register('decrypt_pdf', decrypt_pdf)
ConverterFactory.register('images_to_pdf', images_to_pdf)