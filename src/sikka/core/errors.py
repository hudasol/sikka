"""Error hierarchy. The service layer maps these to problem+json responses."""

from __future__ import annotations


class SikkaError(Exception):
    """Base class for every error raised on purpose by Sikka."""

    title = "Sikka error"
    status = 500


class InputError(SikkaError):
    """The caller supplied input that cannot be processed."""

    title = "Invalid input"
    status = 400


class NotFoundError(SikkaError):
    """A requested resource does not exist."""

    title = "Not found"
    status = 404


class PayloadTooLargeError(InputError):
    """An upload is larger than the configured limit."""

    title = "Payload too large"
    status = 413


class UnsupportedMediaTypeError(InputError):
    """An upload has a content type that Sikka does not parse."""

    title = "Unsupported media type"
    status = 415
