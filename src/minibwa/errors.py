"""Exception hierarchy for minibwa-py.

Every failure surfaces through one of these so callers can catch ``MinibwaError``
broadly or a specific subclass narrowly. The engine's own diagnostics (stderr,
return code) and the raw offending line are always preserved on the exception
instead of being swallowed.
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = [
    "MinibwaError",
    "MinibwaNotFoundError",
    "MinibwaParseError",
    "MinibwaRunError",
]

#: Guidance shown when the engine binary cannot be located. The literal
#: ``conda install -c bioconda minibwa`` substring is part of the public
#: contract and is asserted by the test suite.
NOT_FOUND_MESSAGE = (
    'minibwa binary not found; install with "conda install -c bioconda minibwa", '
    "set MINIBWA_BIN, or pass binary="
)


class MinibwaError(Exception):
    """Base class for every error raised by minibwa-py."""


class MinibwaNotFoundError(MinibwaError):
    """Raised when the ``minibwa`` engine binary cannot be located.

    The default message tells the user exactly how to install the engine.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message if message is not None else NOT_FOUND_MESSAGE)


class MinibwaRunError(MinibwaError):
    """Raised when the engine exits with a nonzero status.

    The full command line, return code, and captured stderr are retained so the
    engine's diagnostics are never lost.
    """

    def __init__(self, argv: Sequence[str], returncode: int, stderr: str) -> None:
        self.argv: list[str] = list(argv)
        self.returncode = returncode
        self.stderr = stderr or ""
        command = " ".join(self.argv)
        tail = self.stderr.strip()
        if tail:
            message = f"minibwa command failed (exit {returncode}): {command}\nstderr:\n{tail}"
        else:
            message = f"minibwa command failed (exit {returncode}): {command}"
        super().__init__(message)


class MinibwaParseError(MinibwaError, ValueError):
    """Raised when a SAM or PAF line cannot be parsed.

    Subclasses :class:`ValueError` so existing ``except ValueError`` handlers
    still catch malformed-line errors. The raw line and (when raised from a
    stream) its 1-based line number are retained for debugging.
    """

    def __init__(self, line: str, lineno: int | None = None) -> None:
        self.line = line
        self.lineno = lineno
        location = f" at line {lineno}" if lineno is not None else ""
        super().__init__(f"could not parse record{location}: {line!r}")
