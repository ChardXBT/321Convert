from typing import Callable, Dict


class ConverterFactory:
    """
    A factory class to manage different types of converters
    """
    _converters: Dict[str, Callable] = {}

    @classmethod
    def register(cls, conversion_type: str, converter_func: Callable):
        """
        Register a new converter function

        :param conversion_type: Unique identifier for the conversion
        :param converter_func: Function to perform the conversion
        """
        cls._converters[conversion_type] = converter_func

    @classmethod
    def convert(cls, conversion_type: str, input_path: str, output_dir: str = None):
        """
        Perform conversion using the registered converter

        :param conversion_type: Type of conversion to perform
        :param input_path: Path to the input file
        :param output_dir: Optional output directory
        :return: Path to the converted file
        :raises ValueError: If conversion type is not registered
        """
        if conversion_type not in cls._converters:
            raise ValueError(f"No converter registered for type: {conversion_type}")

        return cls._converters[conversion_type](input_path, output_dir)