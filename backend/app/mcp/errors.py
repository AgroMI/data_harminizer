from typing import Any


class MCPError(Exception):
    def __init__(self, *, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
