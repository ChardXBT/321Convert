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


# New functions for GIF conversions
def convert_gif_to_png(input_path, output_dir=None):
    """
    Convert a GIF image to PNG format

    Args:
        input_path (str): Path to the input GIF file
        output_dir (str, optional): Directory to save converted file.
                                    Defaults to same directory as input file.

    Returns:
        str: Path to the converted PNG file
    """
    with Image.open(input_path) as img:
        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        # Use the first frame of the GIF
        if hasattr(img, 'n_frames') and img.n_frames > 1:
            img.seek(0)  # Select first frame

        filename = os.path.splitext(os.path.basename(input_path))[0] + '.png'
        output_path = os.path.join(output_dir, filename)

        # Save as PNG
        img.save(output_path, 'PNG')

        return output_path


def convert_png_to_gif(input_path, output_dir=None):
    """
    Convert a PNG image to GIF format

    Args:
        input_path (str): Path to the input PNG file
        output_dir (str, optional): Directory to save converted file.
                                    Defaults to same directory as input file.

    Returns:
        str: Path to the converted GIF file
    """
    with Image.open(input_path) as img:
        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        filename = os.path.splitext(os.path.basename(input_path))[0] + '.gif'
        output_path = os.path.join(output_dir, filename)

        # Save as GIF
        if img.mode == 'RGBA':
            # Convert transparent image to 'P' mode with transparency
            img = img.convert('RGBA')
            alpha = img.split()[3]
            img = img.convert('RGB').convert('P', colors=256)
            mask = Image.eval(alpha, lambda a: 255 if a <= 128 else 0)
            img.paste(255, mask)
            img.save(output_path, 'GIF', transparency=255)
        else:
            img.convert('RGB').convert('P').save(output_path, 'GIF')

        return output_path


def convert_jpg_to_gif(input_path, output_dir=None):
    """
    Convert a JPEG image to GIF format

    Args:
        input_path (str): Path to the input JPEG file
        output_dir (str, optional): Directory to save converted file.
                                    Defaults to same directory as input file.

    Returns:
        str: Path to the converted GIF file
    """
    with Image.open(input_path) as img:
        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        filename = os.path.splitext(os.path.basename(input_path))[0] + '.gif'
        output_path = os.path.join(output_dir, filename)

        # Convert to GIF (first convert to RGB if needed)
        img.convert('RGB').convert('P').save(output_path, 'GIF')

        return output_path


def convert_gif_to_jpg(input_path, output_dir=None):
    """
    Convert a GIF image to JPEG format

    Args:
        input_path (str): Path to the input GIF file
        output_dir (str, optional): Directory to save converted file.
                                    Defaults to same directory as input file.

    Returns:
        str: Path to the converted JPEG file
    """
    with Image.open(input_path) as img:
        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        # Use the first frame of the GIF
        if hasattr(img, 'n_frames') and img.n_frames > 1:
            img.seek(0)  # Select first frame

        filename = os.path.splitext(os.path.basename(input_path))[0] + '.jpg'
        output_path = os.path.join(output_dir, filename)

        # Convert to JPEG with white background
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1])
            background.save(output_path, 'JPEG', quality=80)
        else:
            img.convert('RGB').save(output_path, 'JPEG', quality=80)

        return output_path


def convert_webp_to_gif(input_path, output_dir=None):
    """
    Convert a WebP image to GIF format

    Args:
        input_path (str): Path to the input WebP file
        output_dir (str, optional): Directory to save converted file.
                                    Defaults to same directory as input file.

    Returns:
        str: Path to the converted GIF file
    """
    with Image.open(input_path) as img:
        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        filename = os.path.splitext(os.path.basename(input_path))[0] + '.gif'
        output_path = os.path.join(output_dir, filename)

        # Convert to GIF
        if img.mode == 'RGBA':
            # Convert transparent image to 'P' mode with transparency
            alpha = img.split()[3]
            img = img.convert('RGB').convert('P')
            mask = Image.eval(alpha, lambda a: 255 if a <= 128 else 0)
            img.paste(255, mask)
            img.save(output_path, 'GIF', transparency=255)
        else:
            img.convert('RGB').convert('P').save(output_path, 'GIF')

        return output_path


def convert_gif_to_webp(input_path, output_dir=None):
    """
    Convert a GIF image to WebP format

    Args:
        input_path (str): Path to the input GIF file
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

        # Check if this is an animated GIF
        if hasattr(img, 'n_frames') and img.n_frames > 1:
            # For animated GIFs, we'll take just the first frame
            img.seek(0)

        # Save as WebP
        img.save(output_path, 'WEBP', quality=80)

        return output_path