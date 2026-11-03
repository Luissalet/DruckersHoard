"""Errors carrying the HTTP status the API and the agent bridge answer with. The message is rendered in the request language."""
from . import texts


class DruckerError(Exception):
    status = 422

    def __init__(self, message, status=None, **extra):
        super().__init__(message)
        if status:
            self.status = status
        self.extra = extra


class NotFound(DruckerError):
    status = 404


def err(key, status=None, extra=None, cls=None, **params):
    """An error whose text comes from the catalogue, in the language of the current call."""
    return (cls or DruckerError)(texts.tr(key, **params), status, **(extra or {}))


def not_found(key, **params):
    return err(key, cls=NotFound, **params)
