from PIL import Image
import os


def convert_png_to_jpeg(input_path, output_dir=None):
    """
    Convert a PNG image to JPEG format

    Args:
        input_path (str): Path to the input PNG file
        output_dir (str, optional): Directory to save converted file.
                                    Defaults to same directory as input file.

    Returns:
        str: Path to the converted JPEG file
    """
    with Image.open(input_path) as img:
        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        filename = os.path.splitext(os.path.basename(input_path))[0] + '.jpg'
        output_path = os.path.join(output_dir, filename)

        if img.mode in ('RGBA', 'LA'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            background.save(output_path, 'JPEG', quality=80)
        else:
            img.convert('RGB').save(output_path, 'JPEG', quality=80)

        return output_path


def convert_jpeg_to_png(input_path, output_dir=None):
    """
    Convert a JPEG image to PNG format

    Args:
        input_path (str): Path to the input JPEG file
        output_dir (str, optional): Directory to save converted file.
                                    Defaults to same directory as input file.

    Returns:
        str: Path to the converted PNG file
    """
    with Image.open(input_path) as img:
        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        filename = os.path.splitext(os.path.basename(input_path))[0] + '.png'
        output_path = os.path.join(output_dir, filename)

        # Ensure image is in RGB mode to prevent errors
        img.convert('RGB').save(output_path, 'PNG')

        return output_path


def convert_png_to_webp(input_path, output_dir=None):
    """
    Convert a PNG image to WebP format

    Args:
        input_path (str): Path to the input PNG file
        output_dir (str, optional): Directory to save converted file.
                                    Defaults to same directory as input file.

    Returns:
        str: Path to the converted WebP file
    """
    with Image.open(input_path) as img:
        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        filename = os.path.splitext(os.path.basename(input_path))[0] + '.webp'
        output_path = os.path.join(output_dir, filename)

        # Preserve transparency for PNG
        img.save(output_path, 'WEBP', quality=80)

        return output_path


def convert_webp_to_png(input_path, output_dir=None):
    """
    Convert a WebP image to PNG format

    Args:
        input_path (str): Path to the input WebP file
        output_dir (str, optional): Directory to save converted file.
                                    Defaults to same directory as input file.

    Returns:
        str: Path to the converted PNG file
    """
    with Image.open(input_path) as img:
        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        filename = os.path.splitext(os.path.basename(input_path))[0] + '.png'
        output_path = os.path.join(output_dir, filename)

        # Save as PNG, preserving transparency
        img.save(output_path, 'PNG')

        return output_path