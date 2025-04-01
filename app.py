import os
import shutil
from flask import Flask, render_template, request, send_file
import io

# Ensure you import all conversion functions explicitly
from conversions.image_converter import (
    convert_png_to_jpeg,
    convert_jpeg_to_png,
    convert_png_to_webp,
    convert_webp_to_png,
    # New GIF converters
    convert_gif_to_png,
    convert_png_to_gif,
    convert_jpg_to_gif,
    convert_gif_to_jpg,
    convert_webp_to_gif,
    convert_gif_to_webp
)

# Import the ConverterFactory
from core.converter_factory import ConverterFactory

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create the uploads folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def initialize_converters():
    """
    Register all available converters
    """
    # Original converters
    ConverterFactory.register('jpg_to_png', convert_jpeg_to_png)
    ConverterFactory.register('png_to_jpg', convert_png_to_jpeg)
    ConverterFactory.register('png_to_webp', convert_png_to_webp)
    ConverterFactory.register('webp_to_png', convert_webp_to_png)

    # New GIF converters
    ConverterFactory.register('gif_to_png', convert_gif_to_png)
    ConverterFactory.register('png_to_gif', convert_png_to_gif)
    ConverterFactory.register('jpg_to_gif', convert_jpg_to_gif)
    ConverterFactory.register('gif_to_jpg', convert_gif_to_jpg)
    ConverterFactory.register('webp_to_gif', convert_webp_to_gif)
    ConverterFactory.register('gif_to_webp', convert_gif_to_webp)


# Initialize converters when the app starts
initialize_converters()


def cleanup_upload_folder():
    """
    Remove all files in the upload folder
    """
    for filename in os.listdir(UPLOAD_FOLDER):
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except OSError:
            # Catch specific OSError instead of broad Exception
            print(f'Failed to delete {file_path}')


@app.route('/', methods=['GET'])
def index():
    # Clean up any existing files when the home page is loaded
    cleanup_upload_folder()
    return render_template('index.html')


@app.route('/convert', methods=['POST'])
def convert_image():
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
            input_format = request.form['input_format']
            output_format = request.form['output_format']
            conversion_type = f"{input_format}_to_{output_format}"

            # Perform the conversion using the factory
            converted_filepath = ConverterFactory.convert(conversion_type, filepath)

            # Determine the appropriate MIME type and file extension
            mime_types = {
                'jpg_to_png': 'image/png',
                'png_to_jpg': 'image/jpeg',
                'png_to_webp': 'image/webp',
                'webp_to_png': 'image/png',
                # New GIF mime types
                'gif_to_png': 'image/png',
                'png_to_gif': 'image/gif',
                'jpg_to_gif': 'image/gif',
                'gif_to_jpg': 'image/jpeg',
                'webp_to_gif': 'image/gif',
                'gif_to_webp': 'image/webp'
            }

            # Get the file extension
            def get_extension(conv_type):
                extension_map = {
                    'jpg_to_png': '.png',
                    'png_to_jpg': '.jpg',
                    'png_to_webp': '.webp',
                    'webp_to_png': '.png',
                    # New GIF extensions
                    'gif_to_png': '.png',
                    'png_to_gif': '.gif',
                    'jpg_to_gif': '.gif',
                    'gif_to_jpg': '.jpg',
                    'webp_to_gif': '.gif',
                    'gif_to_webp': '.webp'
                }
                return extension_map.get(conv_type, '.converted')

            # Open the converted file and create a byte stream
            with open(converted_filepath, 'rb') as f:
                file_bytes = f.read()

            # Clean up files
            try:
                os.remove(filepath)
                os.remove(converted_filepath)
                print(f"Deleted files: {filepath} and {converted_filepath}")
            except OSError:
                print("Error deleting files")

            # Return the file as a downloadable attachment
            return send_file(
                io.BytesIO(file_bytes),
                mimetype=mime_types.get(conversion_type, 'application/octet-stream'),
                as_attachment=True,
                download_name=f'converted_image{get_extension(conversion_type)}'
            )

        except ValueError as value_error:
            return str(value_error), 500
        except Exception as conversion_error:
            return f"Conversion error: {str(conversion_error)}", 500


@app.teardown_appcontext
def cleanup_on_shutdown(exc=None):
    """
    Ensure all files are cleaned up when the application context is torn down
    Handle potential exception during shutdown
    """
    if exc is not None:
        # Log the exception if one occurred during request handling
        print(f"Exception during request: {exc}")

    # Always attempt to clean up
    cleanup_upload_folder()


if __name__ == "__main__":
    # Ensure clean uploads folder on startup
    cleanup_upload_folder()

    # Render-specific configuration
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)