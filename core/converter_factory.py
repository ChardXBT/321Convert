from typing import Callable, Dict, Any

class ConverterFactory:
    """
    A factory class to manage different types of converters
    """
    _converters: Dict[str, Callable] = {}  # Fixed the asterisk typo

    @classmethod
    def register(cls, conversion_type: str, converter_func: Callable):  # Fixed the asterisk typo
        """
        Register a new converter function

        :param conversion_type: Unique identifier for the conversion
        :param converter_func: Function to perform the conversion
        """
        cls._converters[conversion_type] = converter_func

    @classmethod
    def convert(cls, conversion_type: str, input_path: str, **kwargs):
        """
        Perform conversion using the registered converter

        :param conversion_type: Type of conversion to perform
        :param input_path: Path to the input file
        :param kwargs: Additional parameters to pass to the converter function
        :return: Path to the converted file or other result
        :raises ValueError: If conversion type is not registered
        """
        if conversion_type not in cls._converters:
            raise ValueError(f"No converter registered for type: {conversion_type}")

        return cls._converters[conversion_type](input_path, **kwargs)

    @classmethod
    def get_converters(cls):
        """
        Return all registered converters.
        """
        return cls._converters