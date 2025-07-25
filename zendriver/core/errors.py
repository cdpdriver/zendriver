"""Exceptions for zendriver package."""


class ZendriverError(Exception):
    """Base exception for zendriver."""

    pass


class BrowserError(ZendriverError):
    """Exception raised from browser."""

    pass


class ElementHandleError(ZendriverError):
    """ElementHandle related exception."""

    pass


class NetworkError(ZendriverError):
    """Network/Protocol related exception."""

    pass


class PageError(ZendriverError):
    """Page/Frame related exception."""

    pass
