"""The :class:`Index` handle returned by :func:`minibwa.index`.

A rich, immutable handle rather than a bare prefix string. It knows its sidecar
files, can check whether they exist, and implements :class:`os.PathLike` so it
can be handed straight back to :func:`minibwa.map` (``__fspath__`` returns the
prefix).
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass
from typing import Union

__all__ = ["Index"]

PathLike = Union[str, "os.PathLike[str]"]


def _expected_files(prefix: str, meth: bool) -> list[pathlib.Path]:
    """Return the sidecar files an index of *prefix* is expected to produce."""
    files = [
        pathlib.Path(f"{prefix}.l2b"),
        pathlib.Path(f"{prefix}.mbw"),
    ]
    if meth:
        files.append(pathlib.Path(f"{prefix}.meth.mbw"))
    return files


class _IndexSlots:
    """Carry ``__slots__`` on a base class.

    Declaring ``__slots__`` directly in a dataclass body that also gives fields
    defaults raises ``'<name>' in __slots__ conflicts with class variable`` (the
    default becomes a class attribute that collides with the slot). Hoisting the
    slots to a base class sidesteps that while keeping the records allocation-
    light and ``__dict__``-free on Python 3.9+.
    """

    __slots__ = ("fasta", "meth", "prefix")


@dataclass(frozen=True)
class Index(_IndexSlots):
    """An immutable handle to a built minibwa index.

    Attributes:
        prefix: The index prefix -- the ``<in.idx>`` argument ``map`` loads.
        fasta: The source FASTA path, if known.
        meth: Whether the index was built for bisulfite (``--meth``) mapping.
    """

    prefix: str
    fasta: str | None = None
    meth: bool = False

    def __fspath__(self) -> str:
        """Return the prefix so the handle is usable anywhere a path is."""
        return self.prefix

    @property
    def files(self) -> list[pathlib.Path]:
        """The sidecar files this index is expected to have produced."""
        return _expected_files(self.prefix, self.meth)

    def exists(self) -> bool:
        """``True`` only when every expected sidecar file is present."""
        return all(path.exists() for path in self.files)

    @classmethod
    def from_prefix(cls, prefix: PathLike, *, meth: bool = False) -> Index:
        """Wrap a pre-built index at *prefix* without rebuilding it."""
        return cls(prefix=os.fspath(prefix), fasta=None, meth=meth)

    def __repr__(self) -> str:
        present = [path.name for path in self.files if path.exists()]
        return f"Index(prefix={self.prefix!r}, meth={self.meth}, present={present})"
