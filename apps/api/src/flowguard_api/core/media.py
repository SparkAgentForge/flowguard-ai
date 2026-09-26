"""Media tool discovery shared by video inference and preview adapters."""

import shutil
import subprocess
import sys
from pathlib import Path


def resolve_media_tool(configured: str, tool_name: str) -> str:
    """Resolve a configured executable or the executable beside the Python runtime."""

    configured_path = Path(configured).expanduser()
    if configured_path.is_absolute() or configured_path.parent != Path("."):
        if configured_path.is_file():
            return str(configured_path)
        raise FileNotFoundError(tool_name)
    else:
        found = shutil.which(configured)
        if found:
            return found
        if configured != tool_name:
            raise FileNotFoundError(tool_name)

    sibling = Path(sys.executable).resolve().parent / tool_name
    if sibling.is_file():
        return str(sibling)
    raise FileNotFoundError(tool_name)


def is_media_tool_runtime_error(error: subprocess.CalledProcessError) -> bool:
    """Detect an executable whose dynamic libraries or runtime are incomplete."""

    stderr = error.stderr if isinstance(error.stderr, str) else ""
    return error.returncode < 0 or "Library not loaded" in stderr or "dyld" in stderr
