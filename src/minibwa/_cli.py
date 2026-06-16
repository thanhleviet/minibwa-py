"""Declarative kwarg-to-flag translation for the ``index`` and ``map`` commands.

All CLI knowledge lives in one table per subcommand. Adding or auditing a flag
is a one-line edit, and the resulting argv is trivially unit-testable. Nothing
here touches the filesystem or spawns a process -- these are pure functions.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple, Union

__all__ = ["INDEX_SPEC", "MAP_SPEC", "FlagSpec", "build_index_argv", "build_map_argv"]

PathLike = Union[str, "os.PathLike[str]"]


class FlagSpec(NamedTuple):
    """One row of the translation table.

    Attributes:
        flag: The literal CLI flag (e.g. ``-t`` or ``--meth``).
        kind: How the value renders:

            * ``store_true`` -- emit the bare flag when the value is truthy.
            * ``value`` -- emit ``[flag, str(value)]``.
            * ``pair`` -- emit ``[flag, "a,b"]`` for a 2-tuple, else
              ``[flag, str(value)]``.
            * ``equals`` -- emit ``["{flag}={value}"]`` (the engine's
              ``--rescue=INT`` / ``--outn=INT`` style).
    """

    flag: str
    kind: str


INDEX_SPEC: dict[str, FlagSpec] = {
    "seed": FlagSpec("-s", "value"),
    "sa_sample_rate": FlagSpec("-u", "value"),
    "low_memory": FlagSpec("-l", "store_true"),
    "block_size": FlagSpec("-b", "value"),
    "threads": FlagSpec("-t", "value"),
    "meth": FlagSpec("--meth", "store_true"),
}

MAP_SPEC: dict[str, FlagSpec] = {
    # Common
    "paf": FlagSpec("-f", "store_true"),
    "threads": FlagSpec("-t", "value"),
    "short_read_len": FlagSpec("-l", "value"),
    "read_group": FlagSpec("-R", "value"),
    "base_tag": FlagSpec("-b", "value"),
    "hic": FlagSpec("--hic", "store_true"),
    "meth": FlagSpec("--meth", "store_true"),
    # Mapping
    "min_seed_len": FlagSpec("-k", "value"),
    "max_seed_occ": FlagSpec("-c", "value"),
    "max_gap": FlagSpec("-g", "value"),
    "bandwidth": FlagSpec("-w", "value"),
    "long_bandwidth": FlagSpec("-W", "value"),
    "min_chain_score": FlagSpec("-m", "value"),
    "sec_ratio": FlagSpec("-p", "value"),
    "max_secondary": FlagSpec("-N", "value"),
    "chain_only": FlagSpec("--chain-only", "store_true"),
    "preset": FlagSpec("-x", "value"),
    # Alignment
    "match_score": FlagSpec("-A", "value"),
    "mismatch_penalty": FlagSpec("-B", "value"),
    "gap_open": FlagSpec("-O", "pair"),
    "gap_extend": FlagSpec("-E", "pair"),
    "dp_score_cutoff": FlagSpec("-s", "value"),
    # Paired-end
    "skip_pairing": FlagSpec("-P", "store_true"),
    "rescue": FlagSpec("--rescue", "equals"),
    # Input/Output
    "output": FlagSpec("-o", "value"),
    "no_unmapped": FlagSpec("-u", "store_true"),
    "output_secondary": FlagSpec("--outn", "equals"),
    "copy_comments": FlagSpec("-y", "store_true"),
    "soft_clip_supp": FlagSpec("-Y", "store_true"),
    "primary_smallest_qpos": FlagSpec("-5", "store_true"),
    "batch_size": FlagSpec("-K", "value"),
}


def _render(spec: FlagSpec, value: Any) -> list[str]:
    """Render a single flag/value pair into argv tokens."""
    if spec.kind == "store_true":
        return [spec.flag] if value else []
    if spec.kind == "value":
        return [spec.flag, str(value)]
    if spec.kind == "pair":
        if isinstance(value, tuple):
            return [spec.flag, ",".join(str(part) for part in value)]
        return [spec.flag, str(value)]
    if spec.kind == "equals":
        return [f"{spec.flag}={value}"]
    raise ValueError(f"unknown flag kind: {spec.kind!r}")  # pragma: no cover


def _flags_from(spec_table: Mapping[str, FlagSpec], kwargs: Mapping[str, Any]) -> list[str]:
    """Translate a kwargs mapping into argv tokens using *spec_table*.

    Values that are ``None`` (or falsy booleans for ``store_true`` flags) are
    skipped, so unset options never appear on the command line.
    """
    argv: list[str] = []
    for name, value in kwargs.items():
        if value is None:
            continue
        spec = spec_table[name]
        if spec.kind == "store_true" and not value:
            continue
        argv.extend(_render(spec, value))
    return argv


def build_index_argv(
    binary: str,
    fasta: PathLike,
    prefix: PathLike | None,
    kwargs: Mapping[str, Any],
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    """Build the argv for ``minibwa index``.

    Layout: ``[binary, "index", *flags, <fasta>, <prefix?>, *extra_args]``.
    """
    argv = [binary, "index", *_flags_from(INDEX_SPEC, kwargs), os.fspath(fasta)]
    if prefix is not None:
        argv.append(os.fspath(prefix))
    if extra_args:
        argv.extend(extra_args)
    return argv


def build_map_argv(
    binary: str,
    index: PathLike,
    reads: PathLike,
    reads2: PathLike | None,
    kwargs: Mapping[str, Any],
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    """Build the argv for ``minibwa map``.

    Layout:
    ``[binary, "map", *flags, <index>, <reads>, <reads2?>, *extra_args]``.
    """
    argv = [
        binary,
        "map",
        *_flags_from(MAP_SPEC, kwargs),
        os.fspath(index),
        os.fspath(reads),
    ]
    if reads2 is not None:
        argv.append(os.fspath(reads2))
    if extra_args:
        argv.extend(extra_args)
    return argv
