"""
Typed exceptions for Weather Provider and Service layers.
"""


class WeatherProviderError(Exception):
    """Base exception for all weather provider failures."""
    pass


class WeatherAPIError(WeatherProviderError):
    """Raised when an external weather API returns a non-200 or server error."""

    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class WeatherTimeoutError(WeatherProviderError):
    """Raised when an external weather API request times out."""
    pass


class WeatherValidationError(WeatherProviderError):
    """Raised when weather API response data is malformed or missing required fields."""
    pass

