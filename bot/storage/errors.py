class StorageError(Exception):
    """Base class for storage related errors."""


class ValidationError(StorageError):
    """Raised when incoming data does not meet validation rules."""

