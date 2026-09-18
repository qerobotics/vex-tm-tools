"""Shared exception types used across backend modules."""
from __future__ import annotations


class QECompError(Exception):
    """Base exception for all QEComp application errors."""


class ProcessingError(QECompError):
    """Raised by the media processing pipeline (FFmpeg, S3) on failure."""


class ConfigurationError(QECompError):
    """Raised when required configuration is missing or invalid."""


class IntegrationError(QECompError):
    """Raised by integration clients for unrecoverable errors."""
