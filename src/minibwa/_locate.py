"""Binary discovery for the ``minibwa`` engine.

The single source of truth for *where* the engine lives. Resolution order:

1. an explicit ``binary=`` argument,
2. the ``MINIBWA_BIN`` environment variable,
3. ``shutil.which("minibwa")`` on ``PATH``.

If none resolve to an existing, executable file, :class:`MinibwaNotFoundError`
is raised with a message telling the user how to install the engine.
"""

from __future__ import annotations

import os
import shutil
from typing import Union

from .errors import NOT_FOUND_MESSAGE, MinibwaNotFoundError

__all__ = ["resolve_binary"]

PathLike = Union[str, "os.PathLike[str]"]


def _validate(path: str, *, source: str) -> str:
    """Return *path* if it is an existing executable file, else raise."""
    if not os.path.isfile(path):
        raise MinibwaNotFoundError(f"minibwa binary from {source} does not exist: {path!r}")
    if not os.access(path, os.X_OK):
        raise MinibwaNotFoundError(f"minibwa binary from {source} is not executable: {path!r}")
    return os.path.abspath(path)


def resolve_binary(binary: PathLike | None = None) -> str:
    """Locate the ``minibwa`` executable.

    Args:
        binary: An explicit path to the engine. When given it takes precedence
            over the environment and ``PATH``.

    Returns:
        The absolute path to the resolved executable.

    Raises:
        MinibwaNotFoundError: If no usable binary can be found. The message
            contains the literal ``conda install -c bioconda minibwa``.
    """
    if binary is not None:
        return _validate(os.fspath(binary), source="binary= argument")

    env_value = os.environ.get("MINIBWA_BIN")
    if env_value:
        return _validate(env_value, source="MINIBWA_BIN")

    found = shutil.which("minibwa")
    if found:
        return os.path.abspath(found)

    raise MinibwaNotFoundError(NOT_FOUND_MESSAGE)
