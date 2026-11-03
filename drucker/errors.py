"""Errors carrying the HTTP status the API and the agent bridge answer with."""


class DruckerError(Exception):
    status = 422

    def __init__(self, message, status=None, **extra):
        super().__init__(message)
        if status:
            self.status = status
        self.extra = extra


class NotFound(DruckerError):
    status = 404
