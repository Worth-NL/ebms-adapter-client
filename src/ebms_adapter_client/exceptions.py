from __future__ import annotations


class EbmsAdapterError(Exception):
    """Base exception for all ebms-adapter-client errors."""

    def __init__(self, message: str, *, status_code: int | None = None, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class EbmsBadRequestError(EbmsAdapterError):
    """Raised on HTTP 400 (e.g. invalid CPA XML, malformed request)."""


class EbmsNotFoundError(EbmsAdapterError):
    """Raised on HTTP 404 (unknown cpaId/messageId/urlMapping/certificateMapping)."""


class EbmsServerError(EbmsAdapterError):
    """Raised on HTTP 5xx responses from ebms-core."""


class EbmsConnectionError(EbmsAdapterError):
    """Raised when ebms-core could not be reached at all (network/timeout)."""
