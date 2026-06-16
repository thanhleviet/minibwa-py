"""Tests for :func:`minibwa._locate.resolve_binary`."""

from __future__ import annotations

import os
import stat

import pytest

from minibwa import MinibwaNotFoundError
from minibwa._locate import resolve_binary


def _make_exe(path) -> str:
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def test_explicit_binary_takes_precedence(tmp_path, monkeypatch):
    explicit = _make_exe(tmp_path / "explicit")
    env_bin = _make_exe(tmp_path / "env")
    monkeypatch.setenv("MINIBWA_BIN", env_bin)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/minibwa")

    assert resolve_binary(explicit) == os.path.abspath(explicit)


def test_env_var_takes_precedence_over_path(tmp_path, monkeypatch):
    env_bin = _make_exe(tmp_path / "env")
    monkeypatch.setenv("MINIBWA_BIN", env_bin)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/minibwa")

    assert resolve_binary() == os.path.abspath(env_bin)


def test_falls_back_to_which(monkeypatch):
    monkeypatch.delenv("MINIBWA_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/minibwa")

    assert resolve_binary() == os.path.abspath("/usr/bin/minibwa")


def test_missing_explicit_path_raises(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(MinibwaNotFoundError):
        resolve_binary(str(missing))


def test_non_executable_explicit_path_raises(tmp_path):
    not_exec = tmp_path / "plain"
    not_exec.write_text("not executable")
    not_exec.chmod(stat.S_IRUSR | stat.S_IWUSR)
    with pytest.raises(MinibwaNotFoundError):
        resolve_binary(str(not_exec))


def test_not_found_message_mentions_conda(monkeypatch):
    monkeypatch.delenv("MINIBWA_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)

    with pytest.raises(MinibwaNotFoundError) as excinfo:
        resolve_binary()
    assert "conda install -c bioconda minibwa" in str(excinfo.value)
    assert "MINIBWA_BIN" in str(excinfo.value)
