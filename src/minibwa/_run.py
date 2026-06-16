"""Low-level subprocess primitives.

Three building blocks, all of which obey two non-negotiable rules: ``shell`` is
never ``True`` and the argument vector is always an explicit ``list[str]``.

* :func:`run_capture` -- run to completion and return stdout.
* :func:`run_to_file` -- run to completion; the engine writes its own output
  file (``-o``), so we only watch stderr/return code.
* :class:`StreamProcess` -- stream stdout line by line while stderr is
  redirected to a temporary file. Redirecting stderr to a file (rather than a
  second pipe) is what makes large WGS-sized SAM streams immune to pipe-buffer
  deadlock without spinning up a reader thread.
"""

from __future__ import annotations

import contextlib
import logging
import os
import select
import subprocess
import tempfile
import time
from collections.abc import Iterator, Sequence
from typing import IO

from .errors import MinibwaRunError

__all__ = ["StreamProcess", "run_capture", "run_to_file"]

logger = logging.getLogger("minibwa")

#: Grace period (seconds) for a terminate() to take effect in the finalize/close
#: ladder before escalating to kill().
_TERMINATE_GRACE = 5.0


def run_capture(argv: Sequence[str], *, timeout: float | None = None) -> str:
    """Run *argv* to completion and return its captured stdout.

    Args:
        argv: The full command vector (engine path first).
        timeout: Optional wall-clock timeout in seconds.

    Returns:
        The process's stdout as text.

    Raises:
        MinibwaRunError: If the process exits with a nonzero status.
    """
    args = list(argv)
    logger.debug("run_capture: %s", args)
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise MinibwaRunError(args, completed.returncode, completed.stderr)
    return completed.stdout


def run_to_file(argv: Sequence[str], *, timeout: float | None = None) -> None:
    """Run *argv* whose own ``-o`` flag directs output to a file.

    Stdout is discarded (the engine writes the file itself); only stderr is
    captured so a failure still surfaces the engine's diagnostics.

    Raises:
        MinibwaRunError: If the process exits with a nonzero status.
    """
    args = list(argv)
    logger.debug("run_to_file: %s", args)
    completed = subprocess.run(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise MinibwaRunError(args, completed.returncode, completed.stderr)


class StreamProcess:
    """Stream stdout from a launched engine process, line by line.

    The child is spawned eagerly in ``__init__`` so launch failures surface at
    construction time rather than on the first iteration. Stderr is redirected
    to a :class:`tempfile.NamedTemporaryFile`; it is read back only at
    end-of-stream (or on error) and fed into :class:`MinibwaRunError`.

    Always usable as a context manager. :meth:`close`, ``__del__`` and
    ``__exit__`` all terminate the child and unlink the stderr temp file so an
    abandoned iterator never leaks a process or file descriptor.
    """

    def __init__(self, argv: Sequence[str], *, timeout: float | None = None) -> None:
        self.argv: list[str] = list(argv)
        self._closed = False
        self._terminated = False
        self._timed_out = False
        self._stderr_file: IO[str] | None = None
        self._stderr_path: str | None = None
        self._process: subprocess.Popen[str] | None = None
        # Wall-clock deadline for the whole stream, computed at launch. Checked
        # while iterating and enforced as a bounded wait at finalize time so a
        # stalled engine raises instead of hanging the caller forever.
        self._timeout = timeout
        self._deadline = time.monotonic() + timeout if timeout is not None else None

        logger.debug("StreamProcess launch: %s", self.argv)
        # Keep the temp file open for the child to write into; we read it back
        # by path after the child exits.
        self._stderr_file = tempfile.NamedTemporaryFile(  # noqa: SIM115
            mode="w+",
            encoding="utf-8",
            prefix="minibwa-stderr-",
            suffix=".log",
            delete=False,
        )
        self._stderr_path = self._stderr_file.name
        try:
            self._process = subprocess.Popen(
                self.argv,
                stdout=subprocess.PIPE,
                stderr=self._stderr_file,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except BaseException:
            # Launch failed (e.g. file vanished between resolve and exec):
            # clean up the temp file before propagating.
            self._cleanup_stderr_file()
            raise

    @property
    def returncode(self) -> int | None:
        """The child's return code, or ``None`` while it is still running."""
        return self._process.returncode if self._process is not None else None

    def __iter__(self) -> Iterator[str]:
        return self.iter_lines()

    def iter_lines(self) -> Iterator[str]:
        """Yield decoded stdout lines (newline retained), then finalize.

        On exhaustion the child is reaped; a nonzero exit raises
        :class:`MinibwaRunError` carrying the captured stderr.

        When a ``timeout`` was supplied at launch, reads are bounded by the
        wall-clock deadline via :func:`select.select` on the stdout pipe, so a
        *silent* stalled engine (one producing no output, where a plain
        ``for line in stdout`` would block forever) raises
        :class:`MinibwaRunError` rather than hanging the caller.

        When the consumer abandons iteration early (``break`` then drops the
        reference), Python throws ``GeneratorExit`` into this generator during
        GC. That is treated exactly like :meth:`close`: the child is reaped via
        the bounded terminate/kill ladder and no error is raised, so nothing
        surfaces from the unraisable hook.
        """
        if self._process is None or self._process.stdout is None:
            return
        try:
            yield from self._iter_raw()
        except GeneratorExit:
            # Consumer abandoned iteration (or interpreter/generator GC). Treat
            # as a deliberate close so finalize does not raise.
            self._terminated = True
            self._finalize()
            raise
        self._finalize()

    def _iter_raw(self) -> Iterator[str]:
        """Yield stdout lines, enforcing the wall-clock deadline if one is set.

        ``iter_lines`` only calls this after guarding that the process and its
        stdout pipe are not ``None``.
        """
        stdout = self._process.stdout
        if stdout is None:
            return
        if self._deadline is None:
            yield from stdout
            return
        fileno = stdout.fileno()
        while True:
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                self._timed_out = True
                return
            ready, _, _ = select.select([fileno], [], [], remaining)
            if not ready:
                # No data within the deadline: the engine has stalled.
                self._timed_out = True
                return
            line = stdout.readline()
            if line == "":
                # Real EOF: the child closed stdout (it has finished/exited).
                return
            yield line

    def _read_stderr(self) -> str:
        if self._stderr_path is None:
            return ""
        try:
            with open(self._stderr_path, encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except OSError:
            return ""

    def _reap(self) -> int | None:
        """Reap the child with a bounded terminate/kill ladder.

        Closing stdout sends EOF/SIGPIPE, but an engine deep in an alignment
        phase may not observe the closed pipe until it next writes, so a plain
        ``wait()`` can block for minutes (or forever on a stalled child). We
        therefore wait only briefly, then escalate to ``terminate()`` and
        finally ``kill()`` -- the same ladder used by :meth:`close` -- so
        finalize never hangs the interpreter (notably during generator GC).

        On a timeout the deadline has already elapsed, so we skip the initial
        grace wait and terminate immediately.

        Returns the child's return code, or ``None`` if there is no child.
        """
        process = self._process
        if process is None:
            return None
        if process.stdout is not None:
            with contextlib.suppress(OSError):
                process.stdout.close()
        if not self._timed_out:
            try:
                return process.wait(timeout=_TERMINATE_GRACE)
            except subprocess.TimeoutExpired:
                pass
        process.terminate()
        try:
            return process.wait(timeout=_TERMINATE_GRACE)
        except subprocess.TimeoutExpired:
            process.kill()
            return process.wait()

    def _finalize(self) -> None:
        """Reap the child after stdout is exhausted and check its status.

        If the stream was deliberately closed -- the consumer broke out of the
        loop early (:meth:`close` sent SIGTERM) or abandoned the generator so
        ``GeneratorExit`` propagated during GC -- the nonzero return code is
        expected and must *not* raise; otherwise the exception would surface
        from the unraisable hook. We only raise when the stream finished on its
        own terms. A timeout raises regardless, since the caller is owed a
        diagnostic for a stalled engine.
        """
        if self._process is None:
            self._cleanup_stderr_file()
            return
        returncode = self._reap()
        stderr_text = self._read_stderr()
        self._cleanup_stderr_file()
        if self._timed_out:
            self._closed = True
            self._terminated = True
            raise MinibwaRunError(
                self.argv,
                returncode if returncode is not None else -1,
                f"minibwa timed out after {self._timeout}s\n{stderr_text}",
            )
        if self._terminated or self._closed:
            self._closed = True
            return
        self._closed = True
        if returncode != 0:
            raise MinibwaRunError(self.argv, returncode, stderr_text)

    def _cleanup_stderr_file(self) -> None:
        if self._stderr_file is not None:
            with contextlib.suppress(OSError):
                self._stderr_file.close()
            self._stderr_file = None
        if self._stderr_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(self._stderr_path)
            self._stderr_path = None

    def close(self) -> None:
        """Terminate the child (if running) and remove the stderr temp file.

        Safe to call multiple times and from ``__del__``.
        """
        if self._closed:
            self._cleanup_stderr_file()
            return
        self._closed = True
        self._terminated = True
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=_TERMINATE_GRACE)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if process is not None and process.stdout is not None:
            with contextlib.suppress(OSError):
                process.stdout.close()
        self._cleanup_stderr_file()

    def __enter__(self) -> StreamProcess:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()
