import os
import shutil
from flask import Flask, render_template, request, send_file
import io
from pathlib import Path

# Import the main conversion function instead of individual converters
from conversions.image_converter import convert_image, convert_from_gif

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
    'tiff': 'image/tiff'
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
                converted_filepath = convert_from_gif(
                    filepath,
                    output_pil_format,
                    quality=int(request.form.get('quality', 80))
                )
            else:
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