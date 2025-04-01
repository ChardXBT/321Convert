from PIL import Image
import os


def convert_image(input_path, output_format, output_dir=None, quality=80):
    """
    Convert an image to the specified format

    Args:
        input_path (str): Path to the input image file
        output_format (str): Target format ('JPEG', 'PNG', 'GIF', 'WEBP', 'BMP', 'TIFF')
        output_dir (str, optional): Directory to save converted file.
                                    Defaults to same directory as input file.
        quality (int, optional): Quality for lossy formats. Defaults to 80.

    Returns:
        str: Path to the converted image file
    """
    # Map of format to file extension
    format_extensions = {
        'JPEG': '.jpg',
        'PNG': '.png',
        'GIF': '.gif',
        'WEBP': '.webp',
        'BMP': '.bmp',
        'TIFF': '.tiff'
    }

    with Image.open(input_path) as img:
        if output_dir is None:
            output_dir = os.path.dirname(input_path)

        # Create output filename with the appropriate extension
        filename = os.path.splitext(os.path.basename(input_path))[0] + format_extensions[output_format]
        output_path = os.path.join(output_dir, filename)

        # Handle special cases based on input format and target format
        if output_format == 'JPEG':
            # Handle transparency for JPEG output (needs white background)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P' and 'transparency' in img.info:
                    img = img.convert('RGBA')
                if 'A' in img.mode:
                    background.paste(img, mask=img.split()[-1])
                    background.save(output_path, output_format, quality=quality)
                else:
                    img.convert('RGB').save(output_path, output_format, quality=quality)
            else:
                img.convert('RGB').save(output_path, output_format, quality=quality)

        elif output_format == 'GIF':
            # Handle transparency for GIF
            if img.mode == 'RGBA':
                alpha = img.split()[3]
                img.convert('RGB').convert('P', palette=Image.Palette.ADAPTIVE)
                mask = Image.eval(alpha, lambda a: 255 if a <= 128 else 0)
                img.paste(255, mask)
                img.save(output_path, output_format, transparency=255)
            else:
                img.convert('RGB').convert('P', palette=Image.Palette.ADAPTIVE).save(output_path, output_format)

        elif output_format == 'BMP' or output_format == 'TIFF':
            # BMP and TIFF don't handle transparency well, convert to RGB
            if img.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                background.save(output_path, output_format)
            else:
                img.convert('RGB').save(output_path, output_format)

        else:  # PNG and WEBP preserve transparency
            if output_format == 'WEBP':
                img.save(output_path, output_format, quality=quality)
            else:
                img.save(output_path, output_format)

        return output_path


def convert_from_gif(input_path, output_format, output_dir=None, quality=80):
    """
    Handle special case for GIF conversion (to account for animations)

    Args:
        input_path (str): Path to the input GIF file
        output_format (str): Target format ('JPEG', 'PNG', 'WEBP', 'BMP', 'TIFF')
        output_dir (str, optional): Directory to save converted file.
                                    Defaults to same directory as input file.
        quality (int, optional): Quality for lossy formats. Defaults to 80.

    Returns:
        str: Path to the converted image file
    """
    with Image.open(input_path) as img:
        # Use the first frame of animated GIFs
        if hasattr(img, 'n_frames') and img.n_frames > 1:
            img.seek(0)  # Select first frame

        # Use the regular conversion function for the actual conversion
        return convert_image(input_path, output_format, output_dir, quality)


# Create wrapper functions for backward compatibility

def convert_png_to_jpeg(input_path, output_dir=None):
    return convert_image(input_path, 'JPEG', output_dir)


def convert_jpeg_to_png(input_path, output_dir=None):
    return convert_image(input_path, 'PNG', output_dir)


def convert_png_to_webp(input_path, output_dir=None):
    return convert_image(input_path, 'WEBP', output_dir)


def convert_webp_to_png(input_path, output_dir=None):
    return convert_image(input_path, 'PNG', output_dir)


def convert_gif_to_png(input_path, output_dir=None):
    return convert_from_gif(input_path, 'PNG', output_dir)


def convert_png_to_gif(input_path, output_dir=None):
    return convert_image(input_path, 'GIF', output_dir)


def convert_jpg_to_gif(input_path, output_dir=None):
    return convert_image(input_path, 'GIF', output_dir)


def convert_gif_to_jpg(input_path, output_dir=None):
    return convert_from_gif(input_path, 'JPEG', output_dir)


def convert_webp_to_gif(input_path, output_dir=None):
    return convert_image(input_path, 'GIF', output_dir)


def convert_gif_to_webp(input_path, output_dir=None):
    return convert_from_gif(input_path, 'WEBP', output_dir)


def convert_bmp_to_png(input_path, output_dir=None):
    return convert_image(input_path, 'PNG', output_dir)


def convert_png_to_bmp(input_path, output_dir=None):
    return convert_image(input_path, 'BMP', output_dir)


def convert_jpg_to_bmp(input_path, output_dir=None):
    return convert_image(input_path, 'BMP', output_dir)


def convert_bmp_to_jpg(input_path, output_dir=None):
    return convert_image(input_path, 'JPEG', output_dir)


def convert_webp_to_bmp(input_path, output_dir=None):
    return convert_image(input_path, 'BMP', output_dir)


def convert_bmp_to_webp(input_path, output_dir=None):
    return convert_image(input_path, 'WEBP', output_dir)


def convert_gif_to_bmp(input_path, output_dir=None):
    return convert_from_gif(input_path, 'BMP', output_dir)


def convert_bmp_to_gif(input_path, output_dir=None):
    return convert_image(input_path, 'GIF', output_dir)


def convert_tiff_to_png(input_path, output_dir=None):
    return convert_image(input_path, 'PNG', output_dir)


def convert_png_to_tiff(input_path, output_dir=None):
    return convert_image(input_path, 'TIFF', output_dir)


def convert_jpg_to_tiff(input_path, output_dir=None):
    return convert_image(input_path, 'TIFF', output_dir)


def convert_tiff_to_jpg(input_path, output_dir=None):
    return convert_image(input_path, 'JPEG', output_dir)


def convert_webp_to_tiff(input_path, output_dir=None):
    return convert_image(input_path, 'TIFF', output_dir)


def convert_tiff_to_webp(input_path, output_dir=None):
    return convert_image(input_path, 'WEBP', output_dir)


def convert_gif_to_tiff(input_path, output_dir=None):
    return convert_from_gif(input_path, 'TIFF', output_dir)


def convert_tiff_to_gif(input_path, output_dir=None):
    return convert_image(input_path, 'GIF', output_dir)


def convert_bmp_to_tiff(input_path, output_dir=None):
    return convert_image(input_path, 'TIFF', output_dir)


def convert_tiff_to_bmp(input_path, output_dir=None):
    return convert_image(input_path, 'BMP', output_dir)