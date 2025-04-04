import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple  # Removed unused 'Union' import

import PyPDF2
import pdf2image
import fitz  # PyMuPDF
import img2pdf
# Removed unused import 'from PIL import Image'
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from core.converter_factory import ConverterFactory


def pdf_to_images(pdf_path: str, output_dir: Optional[str] = None, dpi: int = 300,
                  image_format: str = 'PNG') -> List[str]:  # Renamed 'format' to 'image_format'
    """
    Convert a PDF document to a series of images

    :param pdf_path: Path to the PDF file
    :param output_dir: Directory to save images (defaults to same dir as PDF)
    :param dpi: Resolution for the output images
    :param image_format: Output image format (PNG, JPEG, etc.)
    :return: List of paths to the created image files
    """
    if output_dir is None:
        output_dir = os.path.dirname(pdf_path)

    Path(output_dir).mkdir(exist_ok=True)

    # Use pdf2image library for the conversion
    images = pdf2image.convert_from_path(pdf_path, dpi=dpi)

    # Save each image
    file_paths = []
    for i, img in enumerate(images):
        output_file = os.path.join(output_dir, f"page_{i + 1}.{image_format.lower()}")
        img.save(output_file, format=image_format)
        file_paths.append(output_file)

    return file_paths


def images_to_pdf(image_paths: List[str], output_path: Optional[str] = None) -> str:
    """
    Convert a series of images to a PDF document

    :param image_paths: List of paths to image files
    :param output_path: Path for the output PDF file
    :return: Path to the created PDF file
    """
    if not image_paths:
        raise ValueError("No image paths provided")

    if output_path is None:
        # Use the directory of the first image if output path not specified
        first_img_dir = os.path.dirname(image_paths[0])
        output_path = os.path.join(first_img_dir, "combined_images.pdf")

    # Use img2pdf for better quality (preserves image quality better than PIL)
    with open(output_path, "wb") as f:
        f.write(img2pdf.convert([str(p) for p in image_paths]))

    return output_path


def merge_pdfs(pdf_paths: List[str], output_path: Optional[str] = None) -> str:
    """
    Merge multiple PDF files into a single PDF

    :param pdf_paths: List of paths to PDF files
    :param output_path: Path for the output merged PDF
    :return: Path to the merged PDF file
    """
    if not pdf_paths:
        raise ValueError("No PDF paths provided")

    if output_path is None:
        # Use the directory of the first PDF if output path not specified
        first_pdf_dir = os.path.dirname(pdf_paths[0])
        output_path = os.path.join(first_pdf_dir, "merged.pdf")

    merger = PyPDF2.PdfMerger()

    for pdf_path in pdf_paths:
        merger.append(pdf_path)

    merger.write(output_path)
    merger.close()

    return output_path


def split_pdf(pdf_path: str, page_ranges: Optional[List[Tuple[int, int]]] = None,
              output_dir: Optional[str] = None) -> List[str]:
    """
    Split a PDF into multiple PDFs based on page ranges

    :param pdf_path: Path to the PDF file
    :param page_ranges: List of (start, end) page ranges (1-indexed)
    :param output_dir: Directory to save the split PDFs
    :return: List of paths to the created PDF files
    """
    if output_dir is None:
        output_dir = os.path.dirname(pdf_path)

    Path(output_dir).mkdir(exist_ok=True)

    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        total_pages = len(reader.pages)

        # If no page ranges provided, create one file per page
        if not page_ranges:
            page_ranges = [(i, i) for i in range(1, total_pages + 1)]

        output_paths = []

        for i, (start, end) in enumerate(page_ranges):
            # Validate page range
            if start < 1 or end > total_pages or start > end:
                raise ValueError(f"Invalid page range: {start}-{end}. PDF has {total_pages} pages.")

            # Create a new PDF
            writer = PyPDF2.PdfWriter()

            # Add specified pages (convert from 1-indexed to 0-indexed)
            for page_num in range(start - 1, end):
                writer.add_page(reader.pages[page_num])

            # Save the new PDF
            output_file = os.path.join(output_dir, f"split_{i + 1}.pdf")
            with open(output_file, 'wb') as output:
                writer.write(output)

            output_paths.append(output_file)

    return output_paths


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text content from a PDF file

    :param pdf_path: Path to the PDF file
    :return: Extracted text content
    """
    text = ""

    # Using PyMuPDF (fitz) for better text extraction
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text += page.get_text()

    return text


def create_pdf_from_text(text: str, output_path: str) -> str:
    """
    Create a PDF document from plain text

    :param text: Text content to convert
    :param output_path: Path for the output PDF file
    :return: Path to the created PDF file
    """
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter

    # Simple text rendering - for more complex formatting consider Reportlab Platypus
    y = height - 72  # Start 1 inch from the top
    for line in text.split('\n'):
        # Move to next page if needed
        if y < 72:  # 1 inch from bottom
            c.showPage()
            y = height - 72

        c.drawString(72, y, line)
        y -= 15  # Line spacing

    c.save()
    return output_path


def compress_pdf(pdf_path: str, output_path: Optional[str] = None, quality: str = 'medium') -> str:
    """
    Compress a PDF file to reduce its size

    :param pdf_path: Path to the PDF file
    :param output_path: Path for the compressed PDF file
    :param quality: Compression quality ('high', 'medium', 'low')
    :return: Path to the compressed PDF file
    """
    if output_path is None:
        base_path = os.path.splitext(pdf_path)[0]
        output_path = f"{base_path}_compressed.pdf"

    # Quality settings map to different DPI values
    quality_dpi = {
        'high': 150,
        'medium': 100,
        'low': 72
    }
    dpi = quality_dpi.get(quality.lower(), 100)

    # Convert to images and back to PDF for compression
    with tempfile.TemporaryDirectory() as temp_dir:
        # Convert to images
        image_paths = pdf_to_images(pdf_path, output_dir=temp_dir, dpi=dpi, image_format='JPEG')  # Changed 'format' to 'image_format'

        # Convert back to PDF
        images_to_pdf(image_paths, output_path)

    return output_path


def rotate_pdf_pages(pdf_path: str, rotation: int, pages: Optional[List[int]] = None,
                     output_path: Optional[str] = None) -> str:
    """
    Rotate specified pages in a PDF document

    :param pdf_path: Path to the PDF file
    :param rotation: Rotation angle in degrees (90, 180, 270)
    :param pages: List of page numbers to rotate (1-indexed, None for all pages)
    :param output_path: Path for the output PDF file
    :return: Path to the rotated PDF file
    """
    if output_path is None:
        base_path = os.path.splitext(pdf_path)[0]
        output_path = f"{base_path}_rotated.pdf"

    # Ensure rotation is a multiple of 90
    rotation = rotation % 360
    if rotation % 90 != 0:
        rotation = 90 * (rotation // 90)

    reader = PyPDF2.PdfReader(pdf_path)
    writer = PyPDF2.PdfWriter()

    total_pages = len(reader.pages)

    # If no pages specified, rotate all pages
    if pages is None:
        pages = list(range(1, total_pages + 1))

    # Process each page
    for i in range(total_pages):
        page = reader.pages[i]

        # Rotate if this page is in the list (convert from 1-indexed to 0-indexed)
        if i + 1 in pages:
            page.rotate(rotation)

        writer.add_page(page)

    # Save the rotated PDF
    with open(output_path, 'wb') as output_file:
        writer.write(output_file)

    return output_path


def encrypt_pdf(pdf_path: str, user_password: str, owner_password: Optional[str] = None,
                output_path: Optional[str] = None) -> str:
    """
    Encrypt a PDF file with password protection

    :param pdf_path: Path to the PDF file
    :param user_password: Password required to open the document
    :param owner_password: Password with full permissions (defaults to user_password)
    :param output_path: Path for the encrypted PDF file
    :return: Path to the encrypted PDF file
    """
    if output_path is None:
        base_path = os.path.splitext(pdf_path)[0]
        output_path = f"{base_path}_encrypted.pdf"

    if owner_password is None:
        owner_password = user_password

    reader = PyPDF2.PdfReader(pdf_path)
    writer = PyPDF2.PdfWriter()

    # Copy all pages from the original PDF
    for page in reader.pages:
        writer.add_page(page)

    # Encrypt the PDF
    writer.encrypt(user_password=user_password, owner_password=owner_password)

    # Save the encrypted PDF
    with open(output_path, 'wb') as output_file:
        writer.write(output_file)

    return output_path


def decrypt_pdf(pdf_path: str, password: str, output_path: Optional[str] = None) -> str:
    """
    Decrypt a password-protected PDF file

    :param pdf_path: Path to the encrypted PDF file
    :param password: Password to decrypt the PDF
    :param output_path: Path for the decrypted PDF file
    :return: Path to the decrypted PDF file
    """
    if output_path is None:
        base_path = os.path.splitext(pdf_path)[0]
        output_path = f"{base_path}_decrypted.pdf"

    reader = PyPDF2.PdfReader(pdf_path)

    # Try decrypting with provided password
    if reader.is_encrypted:
        try:
            reader.decrypt(password)
        except Exception:  # Fixed bare except by adding Exception
            raise ValueError("Failed to decrypt PDF with provided password")

    writer = PyPDF2.PdfWriter()

    # Copy all pages from the original PDF
    for page in reader.pages:
        writer.add_page(page)

    # Save the decrypted PDF
    with open(output_path, 'wb') as output_file:
        writer.write(output_file)

    return output_path


# Register all conversion methods with the factory
def register_converters():
    """Register all PDF converters with the ConverterFactory"""
    ConverterFactory.register('pdf_to_images', pdf_to_images)
    ConverterFactory.register('images_to_pdf', images_to_pdf)
    ConverterFactory.register('merge_pdfs', merge_pdfs)
    ConverterFactory.register('split_pdf', split_pdf)
    ConverterFactory.register('extract_text_from_pdf', extract_text_from_pdf)
    ConverterFactory.register('create_pdf_from_text', create_pdf_from_text)
    ConverterFactory.register('compress_pdf', compress_pdf)
    ConverterFactory.register('rotate_pdf_pages', rotate_pdf_pages)
    ConverterFactory.register('encrypt_pdf', encrypt_pdf)
    ConverterFactory.register('decrypt_pdf', decrypt_pdf)


# Register converters when module is imported
register_converters()