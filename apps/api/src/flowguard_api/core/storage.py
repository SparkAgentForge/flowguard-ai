"""Object-storage ports used by the application layer.

Concrete providers such as RustFS and local disk live under
``flowguard_api.infrastructure.storage``.  Keeping these protocols here means
business services do not need to know which storage product is deployed.
"""

import re
from pathlib import Path
from typing import Protocol

SAFE_FILENAME = re.compile(r"[^a-zA-Z0-9._-]+")


class FileStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class PublicFileStorage(FileStorage, Protocol):
    def get_url(self, key: str, expires_seconds: int = 900) -> str: ...


def sanitize_filename(filename: str) -> str:
    """Return a safe basename suitable for an object-storage key."""

    safe_name = SAFE_FILENAME.sub("_", Path(filename).name).strip("._")
    return safe_name or "document"
