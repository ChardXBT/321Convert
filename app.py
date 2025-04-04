# import os
# import shutil
from flask import Flask, render_template, request, send_file, jsonify, url_for
# import io
from pathlib import Path
import time
import threading
import atexit

# Import needed for converter registration
# from core.converter_factory import ConverterFactory
# Import conversions to register all converters (side effect import)
from conversions import *  # noqa: F401

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Set file expiration time (in seconds)
FILE_EXPIRATION = 3600  # 1 hour

# Ensure uploads folder exists
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)

# Dictionary to track uploaded files and their timestamp
file_tracker = {}

# Mapping for format names and their internal PIL names
FORMAT_MAPPING = {
    'jpg': 'JPEG',
    'jpeg': 'JPEG',
    'png': 'PNG',
    'webp': 'WEBP',
    'gif': 'GIF',
    'bmp': 'BMP',
    'tiff': 'TIFF'
}

# Define MIME types for each format
MIME_TYPES = {
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'webp': 'image/webp',
    'gif': 'image/gif',
    'bmp': 'image/bmp',
    'tiff': 'image/tiff',
    'pdf': 'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'csv': 'text/csv',
    'html': 'text/html',
    'txt': 'text/plain',
    'zip': 'application/zip'  # Added zip MIME type
}


def cleanup_files():
    """Clean up expired files in the uploads folder"""
    while True:
        current_time = time.time()
        expired_files = []

        # Find expired files
        for filepath, timestamp in list(file_tracker.items()):
            if current_time - timestamp > FILE_EXPIRATION:
                expired_files.append(filepath)

        # Remove expired files
        for filepath in expired_files:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                file_tracker.pop(filepath, None)
                print(f"Removed expired file: {filepath}")
            except Exception as e:
                print(f"Error removing file {filepath}: {e}")

        # Sleep for 5 minutes before checking again
        time.sleep(300)


def track_file(filepath):
    """Add file to tracking dictionary with current timestamp"""
    file_tracker[filepath] = time.time()


def cleanup_all_files():
    """Remove all files in uploads folder when app shuts down"""
    try:
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
        print("All files cleaned up on application shutdown")
    except Exception as e:
        print(f"Error during shutdown cleanup: {e}")


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


# Create routes to serve the converted files
@app.route('/downloads/<filename>')
def download_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    # Reset file timer on download - user is still active
    if filepath in file_tracker:
        file_tracker[filepath] = time.time()
    return send_file(filepath, as_attachment=True)


@app.route('/previews/<filename>')
def preview_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    # Reset file timer on preview - user is still active
    if filepath in file_tracker:
        file_tracker[filepath] = time.time()
    return send_file(filepath)


@app.route('/convert', methods=['POST'])
def convert_image_route():
    if 'image' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400

    if file:
        # Generate a unique filename to avoid collisions
        filename = f"original_{os.path.basename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Track the new file
        track_file(filepath)

        try:
            input_format = request.form['input_format'].lower()
            output_format = request.form['output_format'].lower()

            # Get the PIL format names
            output_pil_format = FORMAT_MAPPING.get(output_format)

            if not output_pil_format:
                return jsonify({"success": False, "error": f"Unsupported output format: {output_format}"}), 400

            # Determine the correct conversion function based on input format
            if input_format == 'gif' and output_format != 'gif':
                from conversions.image_converter import convert_from_gif
                converted_filepath = convert_from_gif(
                    filepath,
                    output_pil_format,
                    quality=int(request.form.get('quality', 80))
                )
            else:
                from conversions.image_converter import convert_image
                converted_filepath = convert_image(
                    filepath,
                    output_pil_format,
                    quality=int(request.form.get('quality', 80))
                )

            # Track the converted file
            track_file(converted_filepath)

            # Generate unique filename for converted file
            converted_filename = os.path.basename(converted_filepath)

            # Create URLs for download and preview
            download_url = url_for('download_file', filename=converted_filename)
            preview_url = url_for('preview_file', filename=converted_filename)

            return jsonify({
                "success": True,
                "download_url": download_url,
                "preview_url": preview_url
            })

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


@app.route('/pdf/convert', methods=['POST'])
def convert_pdf_route():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400

    if file:
        # Generate a unique filename to avoid collisions
        filename = f"original_{os.path.basename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Track the new file
        track_file(filepath)

        try:
            conversion_type = request.form['conversion_type']

            # Get additional parameters
            params = {}
            if conversion_type == 'pdf_to_images':
                params['dpi'] = int(request.form.get('dpi', 300))
                params['format'] = request.form.get('format', 'PNG')
            elif conversion_type == 'compress_pdf':
                params['quality'] = request.form.get('quality', 'medium')
            elif conversion_type == 'rotate_pdf_pages':
                params['rotation'] = int(request.form.get('rotation', 90))
                pages = request.form.get('pages', '')
                if pages:
                    params['pages'] = [int(p) for p in pages.split(',')]
            elif conversion_type in ('encrypt_pdf', 'decrypt_pdf'):
                params['password'] = request.form.get('password', '')
                if conversion_type == 'encrypt_pdf':
                    owner_password = request.form.get('owner_password', '')
                    if owner_password:
                        params['owner_password'] = owner_password

            # Set output path
            output_file = os.path.join(app.config['UPLOAD_FOLDER'], f"converted_{os.path.basename(filepath)}")
            params['output_path'] = output_file

            # Perform conversion
            result = ConverterFactory.convert(conversion_type, filepath, **params)

            # Handle different return types
            if conversion_type == 'extract_text_from_pdf':
                # For text extraction, return the text content and a download link for a text file
                if isinstance(result, str):
                    # Save the text to a file
                    text_file = os.path.join(app.config['UPLOAD_FOLDER'], "extracted_text.txt")
                    with open(text_file, 'w', encoding='utf-8') as f:
                        f.write(result)

                    # Track the text file
                    track_file(text_file)

                    download_url = url_for('download_file', filename=os.path.basename(text_file))
                    return jsonify({
                        "success": True,
                        "text": result,
                        "download_url": download_url
                    })
            elif conversion_type == 'pdf_to_images':
                # For PDF to images, return URLs for each image
                if isinstance(result, list):
                    # Track each image file
                    for img_path in result:
                        track_file(img_path)

                    # Create a zip file containing all results for bulk download
                    import zipfile
                    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], "converted_images.zip")
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for file_path in result:
                            zipf.write(file_path, os.path.basename(file_path))

                    # Track the zip file
                    track_file(zip_path)

                    # Create image URLs
                    images = []
                    for img_path in result:
                        img_filename = os.path.basename(img_path)
                        images.append({
                            "url": url_for('preview_file', filename=img_filename)
                        })

                    download_all_url = url_for('download_file', filename=os.path.basename(zip_path))
                    return jsonify({
                        "success": True,
                        "images": images,
                        "format": params['format'],
                        "download_all_url": download_all_url
                    })
            else:
                # For other operations that result in a single file
                if isinstance(result, str) and os.path.isfile(result):
                    # Track the result file
                    track_file(result)

                    download_url = url_for('download_file', filename=os.path.basename(result))
                    return jsonify({
                        "success": True,
                        "download_url": download_url
                    })
                elif isinstance(result, list) and all(os.path.isfile(f) for f in result):
                    # Track each file in the result
                    for file_path in result:
                        track_file(file_path)

                    # Create a zip file containing all results
                    import zipfile
                    zip_path = os.path.join(app.config['UPLOAD_FOLDER'], "converted_files.zip")
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for file_path in result:
                            zipf.write(file_path, os.path.basename(file_path))

                    # Track the zip file
                    track_file(zip_path)

                    download_url = url_for('download_file', filename=os.path.basename(zip_path))
                    return jsonify({
                        "success": True,
                        "download_url": download_url
                    })

            # If we get here, something unexpected happened
            return jsonify({"success": False, "error": "Unexpected result format"}), 500

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


@app.route('/document/convert', methods=['POST'])
def convert_document_route():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400

    if file:
        # Generate a unique filename to avoid collisions
        filename = f"original_{os.path.basename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Track the new file
        track_file(filepath)

        try:
            conversion_type = request.form['conversion_type']

            # Get additional parameters
            params = {}
            if conversion_type in ('excel_to_pdf', 'create_csv_from_excel'):
                sheet_name = request.form.get('sheet_name', '')
                if sheet_name:
                    params['sheet_name'] = sheet_name
            elif conversion_type == 'text_to_html':
                params['title'] = request.form.get('title', 'Converted Document')

            # Set output path
            base_name = os.path.splitext(os.path.basename(filepath))[0]

            # Determine output extension based on conversion type
            output_extensions = {
                'docx_to_pdf': 'pdf',
                'html_to_pdf': 'pdf',
                'excel_to_pdf': 'pdf',
                'pdf_to_docx': 'docx',
                'create_csv_from_excel': 'csv',
                'text_to_html': 'html',
                'image_to_text': 'txt'
            }

            ext = output_extensions.get(conversion_type, 'txt')
            output_file = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_converted.{ext}")
            params['output_path'] = output_file

            # Perform conversion
            result = ConverterFactory.convert(conversion_type, filepath, **params)

            # Track the output file
            if os.path.exists(output_file):
                track_file(output_file)

            # Handle different return types based on conversion type
            if conversion_type == 'image_to_text':
                # For OCR, return the extracted text and a download link
                text_file = output_file
                if isinstance(result, str):
                    # If the result is text, save it to a file
                    with open(text_file, 'w', encoding='utf-8') as f:
                        f.write(result)

                    # Track the text file
                    track_file(text_file)

                download_url = url_for('download_file', filename=os.path.basename(text_file))
                return jsonify({
                    "success": True,
                    "text": result if isinstance(result, str) else "Text extraction succeeded",
                    "download_url": download_url
                })
            elif conversion_type == 'text_to_html':
                # For HTML conversion, return the HTML preview and download link
                download_url = url_for('download_file', filename=os.path.basename(output_file))

                # Read the HTML content for preview
                with open(output_file, 'r', encoding='utf-8') as f:
                    html_content = f.read()

                # Escape the HTML content for safe embedding in JSON
                import html
                safe_html = html.escape(html_content)

                return jsonify({
                    "success": True,
                    "html_preview": safe_html,
                    "download_url": download_url
                })
            else:
                # For all other conversions, return a download link to the output file
                if os.path.isfile(output_file):
                    download_url = url_for('download_file', filename=os.path.basename(output_file))
                    return jsonify({
                        "success": True,
                        "download_url": download_url
                    })
                else:
                    return jsonify({
                        "success": False,
                        "error": "Conversion failed: Output file not created"
                    }), 500

        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500


@app.route('/available-converters', methods=['GET'])
def get_available_converters():
    """Return a list of all registered converters"""
    converters = ConverterFactory.get_converters()
    return jsonify(list(converters.keys()))


# Register cleanup on shutdown
atexit.register(cleanup_all_files)

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_files, daemon=True)
cleanup_thread.start()

if __name__ == "__main__":
    # Use environment variables for configuration
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)