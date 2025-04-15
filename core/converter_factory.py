from typing import Callable, Dict

class ConverterFactory:
    """A factory class to manage different types of converters"""
    _converters: Dict[str, Callable] = {}

    @classmethod
    def register(cls, conversion_type: str, converter_func: Callable):
        """Register a new converter function"""
        cls._converters[conversion_type] = converter_func

    @classmethod
    def convert(cls, conversion_type: str, input_path: str, **kwargs):
        """Perform conversion using the registered converter"""
        if conversion_type not in cls._converters:
            raise ValueError(f"No converter registered for type: {conversion_type}")
        return cls._converters[conversion_type](input_path, **kwargs)

    @classmethod
    def get_converters(cls):
        """Return all registered converters"""
        return cls._converters