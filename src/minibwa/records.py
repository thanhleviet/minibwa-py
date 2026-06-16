"""Parsed SAM and PAF records.

Two frozen dataclasses with explicit ``__slots__`` (the class-attribute form,
NOT ``@dataclass(slots=True)``, because that decorator argument is 3.10+ only).
Optional tags are parsed lazily on first ``.tags`` access and cached into an
immutable mapping so the frozen record stays immutable while staying cheap when
tags are never read.

Coordinate conventions are kept faithful to each format and never silently
normalized: :attr:`Alignment.pos` is 1-based (with :attr:`Alignment.pos0` as a
0-based helper); PAF coordinates are 0-based half-open.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from ._tags import TagValue, parse_tags
from .errors import MinibwaParseError

__all__ = ["Alignment", "PafRecord"]

# SAM FLAG bit masks.
_FLAG_PAIRED = 0x1
_FLAG_PROPER_PAIR = 0x2
_FLAG_UNMAPPED = 0x4
_FLAG_MATE_UNMAPPED = 0x8
_FLAG_REVERSE = 0x10
_FLAG_MATE_REVERSE = 0x20
_FLAG_READ1 = 0x40
_FLAG_READ2 = 0x80
_FLAG_SECONDARY = 0x100
_FLAG_QCFAIL = 0x200
_FLAG_DUPLICATE = 0x400
_FLAG_SUPPLEMENTARY = 0x800


class _AlignmentSlots:
    """Carry ``__slots__`` for :class:`Alignment` on a base class.

    A frozen dataclass that declares ``__slots__`` in its own body *and* gives a
    field a default collides (the default becomes a class attribute named like
    the slot). Hoisting the slots here keeps the record ``__dict__``-free and
    3.9-compatible.
    """

    __slots__ = (
        "_lineno",
        "_tag_fields",
        "_tags_cache",
        "cigar",
        "flag",
        "mapq",
        "pnext",
        "pos",
        "qname",
        "qual",
        "rname",
        "rnext",
        "seq",
        "tlen",
    )


@dataclass(frozen=True)
class Alignment(_AlignmentSlots):
    """A single parsed SAM alignment record.

    The 11 mandatory columns are stored with correct types. The literal ``*``
    placeholder is preserved for the string columns; mapping status is derived
    from the FLAG, never from ``rname``.

    :meth:`from_sam_line` is the only supported constructor: it validates the
    columns and populates the leading-underscore private fields
    (``_tag_fields``, ``_tags_cache``, ``_lineno``). Calling the generated
    ``__init__`` directly with those is unsupported.
    """

    qname: str
    flag: int
    rname: str
    pos: int
    mapq: int
    cigar: str
    rnext: str
    pnext: int
    tlen: int
    seq: str
    qual: str
    _tag_fields: tuple[str, ...]
    _tags_cache: Mapping[str, TagValue] | None = field(default=None, compare=False)
    _lineno: int | None = field(default=None, compare=False)

    @classmethod
    def from_sam_line(cls, line: str, *, lineno: int | None = None) -> Alignment:
        """Parse one SAM data line into an :class:`Alignment`.

        Args:
            line: A single SAM line (header lines must be filtered by the
                caller -- the iterator handles ``@`` lines).
            lineno: Optional 1-based source line number for error reporting.

        Raises:
            MinibwaParseError: If there are fewer than 11 columns or a numeric
                field is non-numeric.
        """
        columns = line.rstrip("\n").split("\t")
        if len(columns) < 11:
            raise MinibwaParseError(line, lineno)
        try:
            flag = int(columns[1])
            pos = int(columns[3])
            mapq = int(columns[4])
            pnext = int(columns[7])
            tlen = int(columns[8])
        except ValueError as exc:
            raise MinibwaParseError(line, lineno) from exc
        return cls(
            qname=columns[0],
            flag=flag,
            rname=columns[2],
            pos=pos,
            mapq=mapq,
            cigar=columns[5],
            rnext=columns[6],
            pnext=pnext,
            tlen=tlen,
            seq=columns[9],
            qual=columns[10],
            _tag_fields=tuple(columns[11:]),
            _lineno=lineno,
        )

    @property
    def tags(self) -> Mapping[str, TagValue]:
        """The optional SAM tags, parsed lazily and cached on first access.

        A malformed optional tag raises :class:`MinibwaParseError` carrying the
        same 1-based ``lineno`` the mandatory columns would have reported.
        """
        cached = self._tags_cache
        if cached is None:
            cached = parse_tags(self._tag_fields, lineno=self._lineno)
            object.__setattr__(self, "_tags_cache", cached)
        return cached

    @property
    def pos0(self) -> int:
        """The 0-based start position (``pos - 1``)."""
        return self.pos - 1

    @property
    def is_paired(self) -> bool:
        return bool(self.flag & _FLAG_PAIRED)

    @property
    def is_proper_pair(self) -> bool:
        return bool(self.flag & _FLAG_PROPER_PAIR)

    @property
    def is_unmapped(self) -> bool:
        return bool(self.flag & _FLAG_UNMAPPED)

    @property
    def is_mapped(self) -> bool:
        return not self.flag & _FLAG_UNMAPPED

    @property
    def mate_is_unmapped(self) -> bool:
        return bool(self.flag & _FLAG_MATE_UNMAPPED)

    @property
    def is_reverse(self) -> bool:
        return bool(self.flag & _FLAG_REVERSE)

    @property
    def mate_is_reverse(self) -> bool:
        return bool(self.flag & _FLAG_MATE_REVERSE)

    @property
    def is_read1(self) -> bool:
        return bool(self.flag & _FLAG_READ1)

    @property
    def is_read2(self) -> bool:
        return bool(self.flag & _FLAG_READ2)

    @property
    def is_secondary(self) -> bool:
        return bool(self.flag & _FLAG_SECONDARY)

    @property
    def is_qcfail(self) -> bool:
        return bool(self.flag & _FLAG_QCFAIL)

    @property
    def is_duplicate(self) -> bool:
        return bool(self.flag & _FLAG_DUPLICATE)

    @property
    def is_supplementary(self) -> bool:
        return bool(self.flag & _FLAG_SUPPLEMENTARY)

    def __repr__(self) -> str:
        return (
            f"Alignment(qname={self.qname!r}, {self.rname}:{self.pos}, "
            f"flag={self.flag}, mapq={self.mapq})"
        )


class _PafRecordSlots:
    """Carry ``__slots__`` for :class:`PafRecord` on a base class.

    Same rationale as :class:`_AlignmentSlots`: keeps the frozen dataclass slim
    and 3.9-compatible without the ``__slots__``/default collision.
    """

    __slots__ = (
        "_lineno",
        "_tag_fields",
        "_tags_cache",
        "aln_len",
        "mapq",
        "matches",
        "qend",
        "qlen",
        "qname",
        "qstart",
        "strand",
        "tend",
        "tlen",
        "tname",
        "tstart",
    )


@dataclass(frozen=True)
class PafRecord(_PafRecordSlots):
    """A single parsed PAF record.

    The 12 mandatory columns are stored with correct types. Coordinates are
    0-based half-open as PAF defines; ``strand`` is constrained to ``'+'``/``'-'``
    (anything else makes :meth:`from_paf_line` raise); ``mapq`` ranges 0-255
    (255 means missing).

    :meth:`from_paf_line` is the only supported constructor: it validates the
    columns and populates the leading-underscore private fields
    (``_tag_fields``, ``_tags_cache``, ``_lineno``). Calling the generated
    ``__init__`` directly with those is unsupported.
    """

    qname: str
    qlen: int
    qstart: int
    qend: int
    strand: Literal["+", "-"]
    tname: str
    tlen: int
    tstart: int
    tend: int
    matches: int
    aln_len: int
    mapq: int
    _tag_fields: tuple[str, ...]
    _tags_cache: Mapping[str, TagValue] | None = field(default=None, compare=False)
    _lineno: int | None = field(default=None, compare=False)

    @classmethod
    def from_paf_line(cls, line: str, *, lineno: int | None = None) -> PafRecord:
        """Parse one PAF line into a :class:`PafRecord`.

        Raises:
            MinibwaParseError: If there are fewer than 12 columns, a numeric
                field is non-numeric, or ``strand`` is not ``'+'`` or ``'-'``.
        """
        columns = line.rstrip("\n").split("\t")
        if len(columns) < 12:
            raise MinibwaParseError(line, lineno)
        try:
            qlen = int(columns[1])
            qstart = int(columns[2])
            qend = int(columns[3])
            tlen = int(columns[6])
            tstart = int(columns[7])
            tend = int(columns[8])
            matches = int(columns[9])
            aln_len = int(columns[10])
            mapq = int(columns[11])
        except ValueError as exc:
            raise MinibwaParseError(line, lineno) from exc
        strand = columns[4]
        if strand not in ("+", "-"):
            raise MinibwaParseError(line, lineno)
        return cls(
            qname=columns[0],
            qlen=qlen,
            qstart=qstart,
            qend=qend,
            strand=strand,
            tname=columns[5],
            tlen=tlen,
            tstart=tstart,
            tend=tend,
            matches=matches,
            aln_len=aln_len,
            mapq=mapq,
            _tag_fields=tuple(columns[12:]),
            _lineno=lineno,
        )

    @property
    def tags(self) -> Mapping[str, TagValue]:
        """The optional PAF tags, parsed lazily and cached on first access.

        A malformed optional tag raises :class:`MinibwaParseError` carrying the
        same 1-based ``lineno`` the mandatory columns would have reported.
        """
        cached = self._tags_cache
        if cached is None:
            cached = parse_tags(self._tag_fields, lineno=self._lineno)
            object.__setattr__(self, "_tags_cache", cached)
        return cached

    @property
    def is_reverse(self) -> bool:
        """``True`` when the strand is ``'-'``."""
        return self.strand == "-"

    @property
    def identity(self) -> float | None:
        """Residue-match identity (``matches / aln_len``) or ``None``."""
        if self.aln_len > 0:
            return self.matches / self.aln_len
        return None

    def __repr__(self) -> str:
        return (
            f"PafRecord(qname={self.qname!r}, {self.tname}:"
            f"{self.tstart}-{self.tend}, strand={self.strand!r}, mapq={self.mapq})"
        )
