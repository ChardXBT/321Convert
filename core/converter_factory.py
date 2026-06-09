from collections.abc import Callable


class ConverterFactory:
    _converters: dict[str, Callable] = {}

    @classmethod
    def register(cls, conversion_type: str, converter_func: Callable) -> None:
        if not conversion_type or not callable(converter_func):
            raise ValueError("A converter requires a name and callable.")
        cls._converters[conversion_type] = converter_func

    @classmethod
    def convert(cls, conversion_type: str, input_path: str, **kwargs):
        try:
            converter = cls._converters[conversion_type]
        except KeyError as exc:
            raise ValueError("Unsupported conversion.") from exc
        return converter(input_path, **kwargs)

    @classmethod
    def get_converters(cls) -> tuple[str, ...]:
        return tuple(cls._converters)
