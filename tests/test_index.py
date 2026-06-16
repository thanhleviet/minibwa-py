"""Tests for the :class:`minibwa.Index` handle."""

from __future__ import annotations

import os
import pathlib

import pytest

import minibwa
import minibwa._backend as _backend
from minibwa import Index, MinibwaError


def test_from_prefix_wraps_without_touching_disk(tmp_path):
    prefix = str(tmp_path / "myidx")
    idx = Index.from_prefix(prefix)
    assert idx.prefix == prefix
    assert idx.fasta is None
    assert idx.meth is False
    # No files created.
    assert not idx.exists()


def test_fspath_returns_prefix(tmp_path):
    prefix = str(tmp_path / "myidx")
    idx = Index.from_prefix(prefix)
    assert idx.__fspath__() == prefix
    assert os.fspath(idx) == prefix


def test_files_lists_standard_sidecars(tmp_path):
    prefix = str(tmp_path / "myidx")
    idx = Index.from_prefix(prefix)
    names = [path.name for path in idx.files]
    assert names == ["myidx.l2b", "myidx.mbw"]


def test_files_includes_meth_sidecar_when_meth(tmp_path):
    prefix = str(tmp_path / "myidx")
    idx = Index.from_prefix(prefix, meth=True)
    names = [path.name for path in idx.files]
    assert names == ["myidx.l2b", "myidx.mbw", "myidx.meth.mbw"]


def test_exists_true_only_when_all_present(tmp_path):
    prefix = str(tmp_path / "myidx")
    idx = Index.from_prefix(prefix)
    assert not idx.exists()
    pathlib.Path(prefix + ".l2b").write_text("")
    assert not idx.exists()
    pathlib.Path(prefix + ".mbw").write_text("")
    assert idx.exists()


def test_repr_mentions_present_files(tmp_path):
    prefix = str(tmp_path / "myidx")
    pathlib.Path(prefix + ".l2b").write_text("")
    pathlib.Path(prefix + ".mbw").write_text("")
    idx = Index.from_prefix(prefix)
    text = repr(idx)
    assert "myidx.l2b" in text
    assert "myidx.mbw" in text


def test_index_is_frozen(tmp_path):
    idx = Index.from_prefix(str(tmp_path / "x"))
    import dataclasses

    try:
        idx.prefix = "other"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover
        raise AssertionError("Index should be frozen")


def test_index_prefix_mirrors_fasta_when_prefix_omitted(fake_minibwa, tmp_path):
    fasta = tmp_path / "ref.fa"
    fasta.write_text(">chr1\nACGT\n")
    idx = minibwa.index(str(fasta))
    assert idx.prefix == str(fasta)
    assert idx.fasta == str(fasta)
    # The stub created <fasta>.l2b/.mbw alongside the fasta.
    assert idx.exists()


def test_index_uses_explicit_prefix(fake_minibwa, tmp_path):
    fasta = tmp_path / "ref.fa"
    fasta.write_text(">chr1\nACGT\n")
    prefix = tmp_path / "out"
    idx = minibwa.index(str(fasta), str(prefix), meth=True)
    assert idx.prefix == str(prefix)
    assert idx.meth is True
    assert idx.exists()


def test_index_raises_when_sidecars_missing(tmp_path):
    # Engine "exits 0" (no-op backend) but writes no sidecar files: index()
    # must fail loudly with the missing files, not return a phantom handle.
    class _NoOpBackend:
        def resolve(self, binary):
            return "/bin/true"

        def run_capture(self, argv, *, timeout=None):
            return ""

        def stream_lines(self, argv, *, timeout=None):  # pragma: no cover
            raise AssertionError("not used")

        def run_to_file(self, argv, *, timeout=None):  # pragma: no cover
            raise AssertionError("not used")

    original = _backend.get_default_backend()
    _backend.set_default_backend(_NoOpBackend())
    try:
        fasta = tmp_path / "ref.fa"
        fasta.write_text(">chr1\nACGT\n")
        with pytest.raises(MinibwaError) as excinfo:
            minibwa.index(str(fasta), str(tmp_path / "idx"))
        assert "missing" in str(excinfo.value)
        assert "idx.l2b" in str(excinfo.value)
    finally:
        _backend.set_default_backend(original)
