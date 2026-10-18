class ConversionError(ValueError):
    """A conversion failed for a reason that is safe to show to the user."""


class RequestValidationError(ValueError):
    """The request itself is invalid; the message is safe to show to the user."""


class ConversionTimeout(Exception):
    """The child process did not finish within CONVERSION_TIMEOUT."""


class ConversionCrashed(Exception):
    """The child process died or returned no result."""


class ConverterBusy(Exception):
    """No conversion slot became free within BUSY_WAIT_SECONDS."""
