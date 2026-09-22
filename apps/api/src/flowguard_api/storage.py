import re
from pathlib import Path
from typing import Protocol

from flowguard_api.config import get_settings

SAFE_FILENAME = re.compile(r"[^a-zA-Z0-9._-]+")


class FileStorage(Protocol):
    def put(self, key: str, content: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...


class LocalFileStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def put(self, key: str, content: bytes) -> None:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def get(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def _resolve(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if self.root not in target.parents:
            raise ValueError("非法存储路径")
        return target


def sanitize_filename(filename: str) -> str:
    safe_name = SAFE_FILENAME.sub("_", Path(filename).name).strip("._")
    return safe_name or "document"


def get_file_storage() -> FileStorage:
    return LocalFileStorage(get_settings().upload_dir)
