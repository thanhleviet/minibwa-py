"""Public functions ``index`` / ``map`` / ``version`` plus streaming iterators.

This module orchestrates the pieces: :mod:`._locate` finds the binary,
:mod:`._cli` builds the argv, :mod:`._backend` / :mod:`._run` run it, and
:mod:`.records` parses the output.

The iterators are launched *eagerly* in ``__init__`` so a missing binary or a
malformed argument surfaces when :func:`map` is *called*, not lazily on the
first ``next()``.
"""

from __future__ import annotations

import contextlib
import logging
import os
import pathlib
from collections.abc import Iterator, Sequence
from typing import Literal, Union, overload

from . import _backend
from ._cli import build_index_argv, build_map_argv
from ._run import StreamProcess
from .errors import MinibwaError
from .index import Index
from .records import Alignment, PafRecord

__all__ = ["PafIterator", "SamIterator", "index", "map", "version"]

logger = logging.getLogger("minibwa")

PathLike = Union[str, "os.PathLike[str]"]


def version(*, binary: PathLike | None = None, timeout: float | None = None) -> str:
    """Return the engine version string (e.g. ``"0.1-r363"``).

    Args:
        binary: Optional explicit engine path.
        timeout: Optional wall-clock timeout in seconds.

    Returns:
        The trimmed version string.

    Raises:
        MinibwaNotFoundError: If the engine cannot be located.
        MinibwaRunError: If the engine exits with a nonzero status.
    """
    backend = _backend.get_default_backend()
    resolved = backend.resolve(binary)
    argv = [resolved, "version"]
    out = backend.run_capture(argv, timeout=timeout)
    return out.strip()


def index(
    fasta: PathLike,
    prefix: PathLike | None = None,
    *,
    seed: int | None = None,
    sa_sample_rate: int | None = None,
    low_memory: bool = False,
    block_size: str | None = None,
    threads: int | None = None,
    meth: bool = False,
    binary: PathLike | None = None,
    timeout: float | None = None,
    extra_args: Sequence[str] | None = None,
) -> Index:
    """Build a minibwa index and return a handle to it.

    Runs ``minibwa index [options] <fasta> [prefix]`` to completion.

    Args:
        fasta: The reference FASTA to index.
        prefix: Output index prefix. When ``None`` the engine defaults it to the
            FASTA path; that default is mirrored in the returned handle.
        seed: ``-s`` random seed for ambiguous bases.
        sa_sample_rate: ``-u`` SA sample rate at ``1/(1<<INT)``.
        low_memory: ``-l`` low-memory BWT construction.
        block_size: ``-b`` block size (effective with ``low_memory``).
        threads: ``-t`` thread count (effective without ``low_memory``).
        meth: ``--meth`` build an FM-index for BS-seq mapping.
        binary: Optional explicit engine path.
        timeout: Optional wall-clock timeout in seconds.
        extra_args: Verbatim extra CLI arguments (escape hatch).

    Returns:
        An :class:`Index` whose ``prefix`` is usable as :func:`map`'s first arg.

    Raises:
        MinibwaNotFoundError: If the engine cannot be located.
        MinibwaRunError: If the engine exits with a nonzero status.
        MinibwaError: If the engine exits 0 but the expected sidecar files
            (``.l2b``/``.mbw``, plus ``.meth.mbw`` under ``meth``) are absent.
    """
    backend = _backend.get_default_backend()
    resolved = backend.resolve(binary)
    kwargs = {
        "seed": seed,
        "sa_sample_rate": sa_sample_rate,
        "low_memory": low_memory,
        "block_size": block_size,
        "threads": threads,
        "meth": meth,
    }
    argv = build_index_argv(resolved, fasta, prefix, kwargs, extra_args)
    backend.run_capture(argv, timeout=timeout)

    resolved_prefix = os.fspath(prefix) if prefix is not None else os.fspath(fasta)
    handle = Index(prefix=resolved_prefix, fasta=os.fspath(fasta), meth=meth)
    if not handle.exists():
        missing = [str(path) for path in handle.files if not path.exists()]
        raise MinibwaError(
            f"index() completed (engine exited 0) but expected sidecar files are missing: {missing}"
        )
    return handle


class _StreamIterator:
    """Common machinery for the SAM/PAF streaming iterators.

    Launches the engine eagerly, owns the :class:`StreamProcess`, and exposes
    context-manager / ``close`` / ``__del__`` cleanup so an abandoned iterator
    never leaks a process or a temp file.
    """

    __slots__ = ("_lineno", "_lines", "_process", "argv", "header", "reference_lengths")

    def __init__(self, argv: Sequence[str], *, timeout: float | None = None) -> None:
        self.argv: list[str] = list(argv)
        self.header: list[str] = []
        self.reference_lengths: dict[str, int] = {}
        self._lineno = 0
        # Eager launch: a bad binary/argv raises here, at map() call time.
        self._process: StreamProcess = _backend.get_default_backend().stream_lines(
            self.argv, timeout=timeout
        )
        self._lines: Iterator[str] = self._process.iter_lines()

    def _record_header(self, line: str) -> None:
        stripped = line.rstrip("\n")
        self.header.append(stripped)
        if stripped.startswith("@SQ"):
            fields = stripped.split("\t")
            name: str | None = None
            length: int | None = None
            for fieldval in fields[1:]:
                if fieldval.startswith("SN:"):
                    name = fieldval[3:]
                elif fieldval.startswith("LN:"):
                    try:
                        length = int(fieldval[3:])
                    except ValueError:
                        length = None
            if name is not None and length is not None:
                self.reference_lengths[name] = length

    def close(self) -> None:
        """Terminate the engine and clean up the stderr temp file."""
        self._process.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self._process.close()


class SamIterator(_StreamIterator, Iterator[Alignment]):
    """Streams :class:`Alignment` records from ``minibwa map`` (SAM mode).

    ``@`` header lines are consumed into :attr:`header` and parsed into
    :attr:`reference_lengths` (from ``@SQ SN:/LN:``); they are not yielded.
    """

    def __iter__(self) -> SamIterator:
        return self

    def __next__(self) -> Alignment:
        for line in self._lines:
            self._lineno += 1
            if not line.strip():
                continue
            if line.startswith("@"):
                self._record_header(line)
                continue
            try:
                return Alignment.from_sam_line(line, lineno=self._lineno)
            except BaseException:
                # The underlying generator is merely suspended here, so its
                # `finally` will not run -- reap the child and unlink the temp
                # file deterministically before the error propagates.
                self.close()
                raise
        raise StopIteration


class PafIterator(_StreamIterator, Iterator[PafRecord]):
    """Streams :class:`PafRecord` records from ``minibwa map -f`` (PAF mode)."""

    def __iter__(self) -> PafIterator:
        return self

    def __next__(self) -> PafRecord:
        for line in self._lines:
            self._lineno += 1
            if not line.strip():
                continue
            try:
                return PafRecord.from_paf_line(line, lineno=self._lineno)
            except BaseException:
                # See SamIterator.__next__: the suspended generator's `finally`
                # will not run, so clean up the child/temp file here.
                self.close()
                raise
        raise StopIteration


@overload
def map(
    index: Index | PathLike,
    reads: PathLike,
    reads2: PathLike | None = ...,
    *,
    paf: Literal[False] = ...,
    output: None = ...,
    preset: Literal["sr", "lr", "adap"] | None = ...,
    threads: int | None = ...,
    read_group: str | None = ...,
    base_tag: Literal["cs", "ds", "MD"] | None = ...,
    hic: bool = ...,
    meth: bool = ...,
    short_read_len: int | str | None = ...,
    min_seed_len: int | None = ...,
    max_seed_occ: int | str | None = ...,
    max_gap: int | str | None = ...,
    bandwidth: int | str | None = ...,
    long_bandwidth: int | str | None = ...,
    min_chain_score: int | None = ...,
    sec_ratio: float | None = ...,
    max_secondary: int | None = ...,
    chain_only: bool = ...,
    match_score: int | None = ...,
    mismatch_penalty: int | None = ...,
    gap_open: int | tuple[int, int] | None = ...,
    gap_extend: int | tuple[int, int] | None = ...,
    dp_score_cutoff: int | None = ...,
    skip_pairing: bool = ...,
    rescue: int | None = ...,
    no_unmapped: bool = ...,
    output_secondary: int | None = ...,
    copy_comments: bool = ...,
    soft_clip_supp: bool = ...,
    primary_smallest_qpos: bool = ...,
    batch_size: str | None = ...,
    binary: PathLike | None = ...,
    timeout: float | None = ...,
    extra_args: Sequence[str] | None = ...,
) -> SamIterator: ...


@overload
def map(
    index: Index | PathLike,
    reads: PathLike,
    reads2: PathLike | None = ...,
    *,
    paf: Literal[True],
    output: None = ...,
    preset: Literal["sr", "lr", "adap"] | None = ...,
    threads: int | None = ...,
    read_group: str | None = ...,
    base_tag: Literal["cs", "ds", "MD"] | None = ...,
    hic: bool = ...,
    meth: bool = ...,
    short_read_len: int | str | None = ...,
    min_seed_len: int | None = ...,
    max_seed_occ: int | str | None = ...,
    max_gap: int | str | None = ...,
    bandwidth: int | str | None = ...,
    long_bandwidth: int | str | None = ...,
    min_chain_score: int | None = ...,
    sec_ratio: float | None = ...,
    max_secondary: int | None = ...,
    chain_only: bool = ...,
    match_score: int | None = ...,
    mismatch_penalty: int | None = ...,
    gap_open: int | tuple[int, int] | None = ...,
    gap_extend: int | tuple[int, int] | None = ...,
    dp_score_cutoff: int | None = ...,
    skip_pairing: bool = ...,
    rescue: int | None = ...,
    no_unmapped: bool = ...,
    output_secondary: int | None = ...,
    copy_comments: bool = ...,
    soft_clip_supp: bool = ...,
    primary_smallest_qpos: bool = ...,
    batch_size: str | None = ...,
    binary: PathLike | None = ...,
    timeout: float | None = ...,
    extra_args: Sequence[str] | None = ...,
) -> PafIterator: ...


@overload
def map(
    index: Index | PathLike,
    reads: PathLike,
    reads2: PathLike | None = ...,
    *,
    output: PathLike,
    paf: bool = ...,
    preset: Literal["sr", "lr", "adap"] | None = ...,
    threads: int | None = ...,
    read_group: str | None = ...,
    base_tag: Literal["cs", "ds", "MD"] | None = ...,
    hic: bool = ...,
    meth: bool = ...,
    short_read_len: int | str | None = ...,
    min_seed_len: int | None = ...,
    max_seed_occ: int | str | None = ...,
    max_gap: int | str | None = ...,
    bandwidth: int | str | None = ...,
    long_bandwidth: int | str | None = ...,
    min_chain_score: int | None = ...,
    sec_ratio: float | None = ...,
    max_secondary: int | None = ...,
    chain_only: bool = ...,
    match_score: int | None = ...,
    mismatch_penalty: int | None = ...,
    gap_open: int | tuple[int, int] | None = ...,
    gap_extend: int | tuple[int, int] | None = ...,
    dp_score_cutoff: int | None = ...,
    skip_pairing: bool = ...,
    rescue: int | None = ...,
    no_unmapped: bool = ...,
    output_secondary: int | None = ...,
    copy_comments: bool = ...,
    soft_clip_supp: bool = ...,
    primary_smallest_qpos: bool = ...,
    batch_size: str | None = ...,
    binary: PathLike | None = ...,
    timeout: float | None = ...,
    extra_args: Sequence[str] | None = ...,
) -> pathlib.Path: ...


def map(
    index: Index | PathLike,
    reads: PathLike,
    reads2: PathLike | None = None,
    *,
    preset: Literal["sr", "lr", "adap"] | None = None,
    threads: int | None = None,
    paf: bool = False,
    output: PathLike | None = None,
    read_group: str | None = None,
    base_tag: Literal["cs", "ds", "MD"] | None = None,
    hic: bool = False,
    meth: bool = False,
    short_read_len: int | str | None = None,
    min_seed_len: int | None = None,
    max_seed_occ: int | str | None = None,
    max_gap: int | str | None = None,
    bandwidth: int | str | None = None,
    long_bandwidth: int | str | None = None,
    min_chain_score: int | None = None,
    sec_ratio: float | None = None,
    max_secondary: int | None = None,
    chain_only: bool = False,
    match_score: int | None = None,
    mismatch_penalty: int | None = None,
    gap_open: int | tuple[int, int] | None = None,
    gap_extend: int | tuple[int, int] | None = None,
    dp_score_cutoff: int | None = None,
    skip_pairing: bool = False,
    rescue: int | None = None,
    no_unmapped: bool = False,
    output_secondary: int | None = None,
    copy_comments: bool = False,
    soft_clip_supp: bool = False,
    primary_smallest_qpos: bool = False,
    batch_size: str | None = None,
    binary: PathLike | None = None,
    timeout: float | None = None,
    extra_args: Sequence[str] | None = None,
) -> SamIterator | PafIterator | pathlib.Path:
    """Run ``minibwa map`` and return parsed alignments, PAF records, or a path.

    With ``output=None`` (the default) the engine process is launched eagerly
    and a streaming iterator is returned: a :class:`SamIterator` of
    :class:`Alignment` records, or a :class:`PafIterator` of :class:`PafRecord`
    when ``paf=True`` (which renders ``-f``). Both iterators consume ``@`` header
    lines (exposed via ``.header`` / ``.reference_lengths``), are context
    managers, and raise :class:`MinibwaRunError` at end-of-stream if the engine
    exits nonzero.

    With ``output`` set, ``-o FILE`` is rendered, the command runs to
    completion (no iteration), and the output :class:`pathlib.Path` is returned.

    Args:
        index: An :class:`Index` handle or any path-like index prefix.
        reads: The (first) FASTQ.
        reads2: Optional second FASTQ for paired-end.
        preset: ``-x`` preset (``sr``/``lr``/``adap``).
        threads: ``-t`` worker threads.
        paf: ``-f`` emit PAF instead of SAM.
        output: ``-o`` output file; when given, returns its path.
        read_group: ``-R`` SAM read-group line.
        base_tag: ``-b`` base alignment tag (``cs``/``ds``/``MD``).
        hic: ``--hic`` Hi-C mode (engine-equivalent to ``-5P``).
        meth: ``--meth`` directional bisulfite mode.
        short_read_len: ``-l`` short-read threshold in adaptive mode.
        min_seed_len: ``-k`` minimum seed length.
        max_seed_occ: ``-c`` maximum seed occurrences.
        max_gap: ``-g`` maximum gap size.
        bandwidth: ``-w`` bandwidth.
        long_bandwidth: ``-W`` long bandwidth.
        min_chain_score: ``-m`` minimum chaining score.
        sec_ratio: ``-p`` secondary-to-primary score ratio.
        max_secondary: ``-N`` retained secondary alignments.
        chain_only: ``--chain-only`` chaining only, no base alignment.
        match_score: ``-A`` matching score.
        mismatch_penalty: ``-B`` mismatch penalty.
        gap_open: ``-O`` gap-open penalty; an ``int`` or ``(o1, o2)`` tuple.
        gap_extend: ``-E`` gap-extension penalty; an ``int`` or tuple.
        dp_score_cutoff: ``-s`` suppress alignments below ``INT*A``.
        skip_pairing: ``-P`` skip pairing and mate rescue.
        rescue: ``--rescue=INT`` mate-rescue candidate cap.
        no_unmapped: ``-u`` don't output unmapped reads.
        output_secondary: ``--outn=INT`` secondary alignments to output.
        copy_comments: ``-y`` copy FASTA/Q comments to output.
        soft_clip_supp: ``-Y`` soft-clip supplementary alignments.
        primary_smallest_qpos: ``-5`` smallest-query-position primary.
        batch_size: ``-K`` per-batch base count.
        binary: Optional explicit engine path.
        timeout: Optional wall-clock timeout in seconds. For the ``output=``
            path it bounds the run-to-completion call. For the streaming path it
            is a deadline checked while iterating (and a bounded wait at
            finalize), so a stalled engine raises :class:`MinibwaRunError`
            instead of hanging the caller forever.
        extra_args: Verbatim extra CLI arguments (escape hatch).

    Returns:
        A :class:`SamIterator`, a :class:`PafIterator`, or a
        :class:`pathlib.Path` depending on ``paf`` / ``output``.

    Raises:
        MinibwaNotFoundError: Eagerly, if the engine cannot be located.
        MinibwaRunError: On a nonzero engine exit or on ``timeout`` expiry.
    """
    backend = _backend.get_default_backend()
    resolved = backend.resolve(binary)

    kwargs = {
        "preset": preset,
        "threads": threads,
        "paf": paf,
        "read_group": read_group,
        "base_tag": base_tag,
        "hic": hic,
        "meth": meth,
        "short_read_len": short_read_len,
        "min_seed_len": min_seed_len,
        "max_seed_occ": max_seed_occ,
        "max_gap": max_gap,
        "bandwidth": bandwidth,
        "long_bandwidth": long_bandwidth,
        "min_chain_score": min_chain_score,
        "sec_ratio": sec_ratio,
        "max_secondary": max_secondary,
        "chain_only": chain_only,
        "match_score": match_score,
        "mismatch_penalty": mismatch_penalty,
        "gap_open": gap_open,
        "gap_extend": gap_extend,
        "dp_score_cutoff": dp_score_cutoff,
        "skip_pairing": skip_pairing,
        "rescue": rescue,
        "no_unmapped": no_unmapped,
        "output_secondary": output_secondary,
        "copy_comments": copy_comments,
        "soft_clip_supp": soft_clip_supp,
        "primary_smallest_qpos": primary_smallest_qpos,
        "batch_size": batch_size,
    }

    if output is not None:
        kwargs["output"] = os.fspath(output)
        argv = build_map_argv(resolved, index, reads, reads2, kwargs, extra_args)
        backend.run_to_file(argv, timeout=timeout)
        return pathlib.Path(os.fspath(output))

    argv = build_map_argv(resolved, index, reads, reads2, kwargs, extra_args)
    if paf:
        return PafIterator(argv, timeout=timeout)
    return SamIterator(argv, timeout=timeout)
