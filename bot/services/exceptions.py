class ServiceError(Exception):
    """Base service layer exception."""


class LinkAmbiguityError(ServiceError):
    """Raised when multiple members match provided criteria."""

    def __init__(self, message: str, candidates: list[int] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


class NotFoundError(ServiceError):
    """Raised when entity cannot be located."""


class PermissionError(ServiceError):
    """Raised when caller lacks permissions."""


class ValidationServiceError(ServiceError):
    """Raised when input data validation fails on service layer."""
