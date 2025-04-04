import os
import shutil
from flask import Flask, render_template, request, send_file, jsonify
import io
from pathlib import Path

# Import needed for converter registration
from core.converter_factory import ConverterFactory
# Import conversions to register all converters (side effect import)
from conversions import *  # noqa: F401

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure uploads folder exists
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)

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


def cleanup_upload_folder():
    """Remove all files in the upload folder"""
    for item in Path(UPLOAD_FOLDER).glob('*'):
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        except OSError as e:
            print(f'Failed to delete {item}: {e}')


@app.route('/', methods=['GET'])
def index():
    # Clean up any existing files when the home page is loaded
    cleanup_upload_folder()
    return render_template('index.html')


@app.route('/convert', methods=['POST'])
def convert_image_route():
    if 'image' not in request.files:
        return "No file part", 400

    file = request.files['image']
    if file.filename == '':
        return "No selected file", 400

    if file:
        # Save the file in the 'uploads' directory
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        try:
            input_format = request.form['input_format'].lower()
            output_format = request.form['output_format'].lower()

            # Get the PIL format names
            output_pil_format = FORMAT_MAPPING.get(output_format)

            if not output_pil_format:
                return f"Unsupported output format: {output_format}", 400

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

            # Open the converted file and create a byte stream
            with open(converted_filepath, 'rb') as f:
                file_bytes = f.read()

            # Clean up files
            try:
                os.remove(filepath)
                os.remove(converted_filepath)
            except OSError as e:
                print(f"Error deleting files: {e}")

            # Return the file as a downloadable attachment
            return send_file(
                io.BytesIO(file_bytes),
                mimetype=MIME_TYPES.get(output_format, 'application/octet-stream'),
                as_attachment=True,
                download_name=f'converted_image.{output_format}'
            )

        except Exception as e:
            # Clean up any files that might have been created
            if 'filepath' in locals():
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            return f"Conversion error: {str(e)}", 500


def handle_file_result(result):
    """Helper function to handle file results to avoid code duplication"""
    if os.path.isfile(result):
        with open(result, 'rb') as f:
            file_bytes = f.read()

        # Determine MIME type based on file extension
        file_ext = os.path.splitext(result)[1][1:].lower()
        mimetype = MIME_TYPES.get(file_ext, 'application/octet-stream')

        return send_file(
            io.BytesIO(file_bytes),
            mimetype=mimetype,
            as_attachment=True,
            download_name=os.path.basename(result)
        )
    else:
        # If result is just text (e.g., extracted text)
        return result


@app.route('/pdf/convert', methods=['POST'])
def convert_pdf_route():
    if 'file' not in request.files:
        return "No file part", 400

    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    if file:
        # Save the file in the 'uploads' directory
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

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

            # Use the getter method instead of direct access to protected member
            converters = ConverterFactory.get_converters()

            # Perform conversion
            result = ConverterFactory.convert(conversion_type, filepath, **params)

            # Handle different return types
            if isinstance(result, list):
                # Multiple files were created (e.g., pdf_to_images)
                # Create a zip file containing all results
                import zipfile
                zip_path = os.path.join(app.config['UPLOAD_FOLDER'], "converted_files.zip")
                with zipfile.ZipFile(zip_path, 'w') as zipf:
                    for file_path in result:
                        zipf.write(file_path, os.path.basename(file_path))

                # Return the zip file
                with open(zip_path, 'rb') as f:
                    file_bytes = f.read()

                return send_file(
                    io.BytesIO(file_bytes),
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name='converted_files.zip'
                )
            elif isinstance(result, str):
                return handle_file_result(result)
            else:
                return "Unknown result type", 500

        except Exception as e:
            # Clean up any files that might have been created
            if 'filepath' in locals():
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            return f"Conversion error: {str(e)}", 500


@app.route('/document/convert', methods=['POST'])
def convert_document_route():
    if 'file' not in request.files:
        return "No file part", 400

    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    if file:
        # Save the file in the 'uploads' directory
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        try:
            conversion_type = request.form['conversion_type']

            # Get additional parameters
            params = {}
            if conversion_type == 'excel_to_pdf' or conversion_type == 'create_csv_from_excel':
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
                'text_to_html': 'html'
            }

            ext = output_extensions.get(conversion_type, 'txt')
            output_file = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}_converted.{ext}")
            params['output_path'] = output_file

            # Use the getter method instead of direct access to protected member
            converters = ConverterFactory.get_converters()

            # Perform conversion
            result = ConverterFactory.convert(conversion_type, filepath, **params)

            # Handle different return types
            if conversion_type == 'image_to_text':
                # Return extracted text
                return result
            else:
                return handle_file_result(result)

        except Exception as e:
            # Clean up any files that might have been created
            if 'filepath' in locals():
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            return f"Conversion error: {str(e)}", 500


@app.route('/available-converters', methods=['GET'])
def get_available_converters():
    """Return a list of all registered converters"""
    # Use the getter method instead of direct access to protected member
    converters = ConverterFactory.get_converters()
    return jsonify(list(converters.keys()))


@app.teardown_appcontext
def cleanup_on_shutdown(exc=None):
    """Ensure all files are cleaned up when the application context ends"""
    if exc is not None:
        print(f"Exception during request: {exc}")
    cleanup_upload_folder()


if __name__ == "__main__":
    # Ensure clean uploads folder on startup
    cleanup_upload_folder()

    # Use environment variables for configuration
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)