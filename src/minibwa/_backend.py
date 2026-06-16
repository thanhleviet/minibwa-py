"""The single internal extensibility seam.

There is exactly one shipped backend, :class:`SubprocessBackend`, consumed
through a module-level default. The seam is deliberately *internal*: there is no
public ``backend=`` keyword on the public functions. It exists only so a future
native backend could be a drop-in replacement without leaking complexity into
the user-facing API.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Protocol, Union, runtime_checkable

from . import _run
from ._locate import resolve_binary

__all__ = [
    "Backend",
    "SubprocessBackend",
    "get_default_backend",
    "set_default_backend",
]

logger = logging.getLogger("minibwa")

PathLike = Union[str, "os.PathLike[str]"]


@runtime_checkable
class Backend(Protocol):
    """The internal engine-execution contract.

    A backend knows how to locate the engine and how to run a prepared argv in
    three modes: capture-all, stream-stdout, and run-to-file.
    """

    def resolve(self, binary: PathLike | None) -> str:
        """Return the absolute path to the engine binary."""
        ...

    def run_capture(self, argv: Sequence[str], *, timeout: float | None = None) -> str:
        """Run *argv* and return captured stdout (raise on nonzero exit)."""
        ...

    def stream_lines(
        self, argv: Sequence[str], *, timeout: float | None = None
    ) -> _run.StreamProcess:
        """Launch *argv* and return a streaming stdout handle."""
        ...

    def run_to_file(self, argv: Sequence[str], *, timeout: float | None = None) -> None:
        """Run *argv* whose ``-o`` flag writes the output file."""
        ...


class SubprocessBackend:
    """The default backend: shells out via :mod:`subprocess`.

    Every method delegates to :mod:`minibwa._run` and
    :func:`minibwa._locate.resolve_binary`.
    """

    def resolve(self, binary: PathLike | None) -> str:
        return resolve_binary(binary)

    def run_capture(self, argv: Sequence[str], *, timeout: float | None = None) -> str:
        return _run.run_capture(argv, timeout=timeout)

    def stream_lines(
        self, argv: Sequence[str], *, timeout: float | None = None
    ) -> _run.StreamProcess:
        return _run.StreamProcess(argv, timeout=timeout)

    def run_to_file(self, argv: Sequence[str], *, timeout: float | None = None) -> None:
        _run.run_to_file(argv, timeout=timeout)


_default_backend: Backend = SubprocessBackend()


def get_default_backend() -> Backend:
    """Return the module-level default backend."""
    return _default_backend


def set_default_backend(backend: Backend) -> None:
    """Replace the default backend (internal/testing use only)."""
    global _default_backend
    logger.debug("default backend replaced with %r", backend)
    _default_backend = backend
