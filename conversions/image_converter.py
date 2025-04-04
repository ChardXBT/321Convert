import os
from PIL import Image
from core.converter_factory import ConverterFactory


def convert_image(input_path, output_format, **kwargs):
    """
    Convert an image to a different format

    :param input_path: Path to the input image
    :param output_format: Target format (PIL format name)
    :param kwargs: Additional parameters (quality, etc.)
    :return: Path to the converted image
    """
    quality = kwargs.get('quality', 80)

    # Define output path
    output_dir = os.path.dirname(input_path)
    filename = os.path.splitext(os.path.basename(input_path))[0]
    output_ext = output_format.lower()
    output_path = os.path.join(output_dir, f"converted_{filename}.{output_ext}")

    # Open and convert the image
    with Image.open(input_path) as img:
        # Convert to RGB if saving as JPEG
        if output_format == 'JPEG' and img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])  # 3 is the alpha channel
            img = background

        # Save with appropriate parameters
        save_image(img, output_path, output_format, quality)

    return output_path


def convert_from_gif(input_path, output_format, **kwargs):
    """
    Convert a GIF to another format (takes the first frame)

    :param input_path: Path to the input GIF
    :param output_format: Target format (PIL format name)
    :param kwargs: Additional parameters (quality, etc.)
    :return: Path to the converted image
    """
    quality = kwargs.get('quality', 80)

    # Define output path
    output_dir = os.path.dirname(input_path)
    filename = os.path.splitext(os.path.basename(input_path))[0]
    output_ext = output_format.lower()
    output_path = os.path.join(output_dir, f"converted_{filename}.{output_ext}")

    # Open GIF and get first frame
    with Image.open(input_path) as img:
        # Take first frame of the GIF
        img.seek(0)

        # Convert to RGB if needed
        if output_format == 'JPEG' and img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')

        # Save with appropriate parameters
        save_image(img, output_path, output_format, quality)

    return output_path


def save_image(img, output_path, output_format, quality):
    """
    Helper function to save an image with the appropriate parameters

    :param img: PIL Image object
    :param output_path: Path where the image will be saved
    :param output_format: Format to save the image in
    :param quality: Quality setting for JPEG/WEBP formats
    """
    if output_format in ('JPEG', 'WEBP'):
        img.save(output_path, output_format, quality=quality, optimize=True)
    elif output_format == 'PNG':
        img.save(output_path, output_format, optimize=True)
    else:
        img.save(output_path, output_format)


# Register converters with factory
ConverterFactory.register('convert_image', convert_image)
ConverterFactory.register('convert_from_gif', convert_from_gif)