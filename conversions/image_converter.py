import os
import warnings

from PIL import Image, ImageOps

from core.converter_factory import ConverterFactory


Image.MAX_IMAGE_PIXELS = 40_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)


def convert_image(input_path, output_format, **kwargs):
    quality = kwargs.get("quality", 82)
    output_dir = os.path.dirname(input_path)
    filename = os.path.splitext(os.path.basename(input_path))[0]
    output_ext = "jpg" if output_format == "JPEG" else output_format.lower()
    output_path = os.path.join(output_dir, f"converted_{filename}.{output_ext}")

    with Image.open(input_path) as source:
        source.verify()
    with Image.open(input_path) as source:
        source.seek(0)
        image = ImageOps.exif_transpose(source)
        image.load()
        if output_format == "JPEG":
            if image.mode in ("RGBA", "LA"):
                alpha = image.getchannel("A")
                background = Image.new("RGB", image.size, "white")
                background.paste(image.convert("RGB"), mask=alpha)
                image = background
            elif image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
        save_options = {}
        if output_format in ("JPEG", "WEBP"):
            save_options.update(quality=quality, optimize=True)
        elif output_format == "PNG":
            save_options["optimize"] = True
        image.save(output_path, output_format, **save_options)
    return output_path


ConverterFactory.register("convert_image", convert_image)
