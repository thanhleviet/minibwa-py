"""Tests for the low-level subprocess primitives in :mod:`minibwa._run`.

These drive real ``python -c`` children so no engine is needed.
"""

from __future__ import annotations

import gc
import os
import sys
import time

import pytest

from minibwa import MinibwaRunError
from minibwa._run import StreamProcess, run_capture, run_to_file


def test_run_capture_returns_stdout():
    argv = [sys.executable, "-c", "print('hello')"]
    assert run_capture(argv).strip() == "hello"


def test_run_capture_nonzero_raises_with_stderr_and_argv():
    argv = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('boom diagnostics'); sys.exit(7)",
    ]
    with pytest.raises(MinibwaRunError) as excinfo:
        run_capture(argv)
    err = excinfo.value
    assert err.returncode == 7
    assert err.argv == argv
    assert "boom diagnostics" in err.stderr
    assert "boom diagnostics" in str(err)


def test_stream_does_not_deadlock_on_large_stdout_and_stderr():
    # Write many stdout lines AND a large stderr payload. A naive pipe+pipe
    # design would deadlock; the temp-file stderr design must not.
    program = (
        "import sys\n"
        "sys.stderr.write('E' * 500000)\n"
        "for i in range(20000):\n"
        "    sys.stdout.write(f'line{i}\\n')\n"
    )
    argv = [sys.executable, "-c", program]
    proc = StreamProcess(argv)
    count = sum(1 for _ in proc.iter_lines())
    assert count == 20000


def test_stream_nonzero_exit_raises_at_end_of_stream():
    program = (
        "import sys\nprint('one')\nprint('two')\nsys.stderr.write('engine failed')\nsys.exit(5)\n"
    )
    argv = [sys.executable, "-c", program]
    proc = StreamProcess(argv)
    lines = []
    with pytest.raises(MinibwaRunError) as excinfo:
        for line in proc.iter_lines():
            lines.append(line.rstrip("\n"))
    assert lines == ["one", "two"]
    assert excinfo.value.returncode == 5
    assert "engine failed" in excinfo.value.stderr


def test_stream_close_after_partial_consumption_cleans_up():
    # A long-lived child; consume one line then close early.
    program = (
        "import sys, time\n"
        "for i in range(100000):\n"
        "    sys.stdout.write(f'line{i}\\n')\n"
        "    sys.stdout.flush()\n"
        "    time.sleep(0.001)\n"
    )
    argv = [sys.executable, "-c", program]
    proc = StreamProcess(argv)
    stderr_path = proc._stderr_path
    assert stderr_path is not None and os.path.exists(stderr_path)

    iterator = proc.iter_lines()
    first = next(iterator)
    assert first.startswith("line")

    proc.close()
    # Child reaped and temp file removed.
    assert proc._process is not None
    assert proc._process.poll() is not None
    assert not os.path.exists(stderr_path)


def test_stream_context_manager_cleans_up():
    argv = [sys.executable, "-c", "print('x')"]
    with StreamProcess(argv) as proc:
        stderr_path = proc._stderr_path
        assert stderr_path is not None and os.path.exists(stderr_path)
    assert not os.path.exists(stderr_path)


def test_run_to_file_writes_and_checks_exit(tmp_path):
    out = tmp_path / "out.txt"
    # Simulate an engine that writes its own -o file.
    argv = [
        sys.executable,
        "-c",
        f"open({str(out)!r}, 'w').write('written')",
    ]
    run_to_file(argv)
    assert out.read_text() == "written"


def test_run_to_file_nonzero_raises(tmp_path):
    argv = [sys.executable, "-c", "import sys; sys.stderr.write('no'); sys.exit(2)"]
    with pytest.raises(MinibwaRunError) as excinfo:
        run_to_file(argv)
    assert excinfo.value.returncode == 2
    assert "no" in excinfo.value.stderr


def test_argv_is_a_list_not_shell_string():
    # Special characters must be passed literally, not interpreted by a shell.
    argv = [sys.executable, "-c", "print('a;b|c')"]
    assert run_capture(argv).strip() == "a;b|c"


def test_stream_timeout_raises_on_silent_stall():
    # Child writes one line then stalls forever producing no further output.
    # A plain `for line in stdout` would block; the deadline must fire instead.
    program = "import sys, time\nsys.stdout.write('one\\n')\nsys.stdout.flush()\ntime.sleep(60)\n"
    argv = [sys.executable, "-c", program]
    proc = StreamProcess(argv, timeout=1.0)
    started = time.monotonic()
    lines = []
    with pytest.raises(MinibwaRunError) as excinfo:
        for line in proc.iter_lines():
            lines.append(line.rstrip("\n"))
    elapsed = time.monotonic() - started
    assert lines == ["one"]
    assert "timed out" in excinfo.value.stderr
    assert elapsed < 10, f"timeout took too long: {elapsed:.1f}s"
    # The stalled child was reaped, not left running.
    assert proc._process is not None
    assert proc._process.poll() is not None


def test_stream_finishes_normally_within_generous_timeout():
    program = "for i in range(5):\n    print(i)\n"
    proc = StreamProcess([sys.executable, "-c", program], timeout=30.0)
    assert [line.strip() for line in proc.iter_lines()] == ["0", "1", "2", "3", "4"]


def test_finalize_does_not_block_on_partial_read_via_gc():
    # Consume one line from a long-lived child, then drop the iterator without
    # close(). GC throws GeneratorExit; finalize must reap with a bounded wait
    # and NOT block the interpreter or raise from the unraisable hook.
    program = (
        "import sys, time\n"
        "for i in range(100000):\n"
        "    sys.stdout.write(f'line{i}\\n')\n"
        "    sys.stdout.flush()\n"
        "    time.sleep(0.001)\n"
    )
    proc = StreamProcess([sys.executable, "-c", program])
    stderr_path = proc._stderr_path
    iterator = proc.iter_lines()
    assert next(iterator).startswith("line")
    started = time.monotonic()
    del iterator
    gc.collect()
    elapsed = time.monotonic() - started
    assert elapsed < 10, f"GC finalize blocked too long: {elapsed:.1f}s"
    assert proc._process is not None
    assert proc._process.poll() is not None
    assert stderr_path is not None and not os.path.exists(stderr_path)


def test_partial_read_then_gc_does_not_raise_runerror(recwarn):
    # The child exits nonzero after its stdout pipe is closed early, but because
    # the consumer abandoned iteration this must be treated as a deliberate
    # close: no MinibwaRunError surfaces from generator finalization.
    program = (
        "import sys, time\n"
        "for i in range(100000):\n"
        "    sys.stdout.write(f'line{i}\\n')\n"
        "    sys.stdout.flush()\n"
        "    time.sleep(0.001)\n"
        "sys.exit(7)\n"
    )
    proc = StreamProcess([sys.executable, "-c", program])
    iterator = proc.iter_lines()
    assert next(iterator).startswith("line")
    # Dropping the only reference triggers GeneratorExit-driven finalize.
    del iterator
    gc.collect()
    # No assertion error or unraisable: if finalize raised, pytest would report
    # an "Exception ignored in" via the unraisable hook.
    assert proc._process is not None
    assert proc._process.poll() is not None
