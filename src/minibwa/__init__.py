"""minibwa-py: a pure-Python subprocess wrapper for the ``minibwa`` aligner.

This package shells out to the user-installed ``minibwa`` engine binary; it
bundles and links no engine code. The wrapper itself is MIT-licensed. The
``minibwa`` engine is licensed separately (GPL-2.0-or-later for the default
build) and must be installed by the user (e.g. ``conda install -c bioconda
minibwa``).

Quickstart::

    import minibwa

    idx = minibwa.index("ref.fa")
    for aln in minibwa.map(idx, "reads.fq", preset="sr", threads=8):
        print(aln.qname, aln.flag, aln.rname, aln.pos, aln.mapq)

    minibwa.version()  # -> "0.1-r363"
"""

from __future__ import annotations

import logging

from ._api import PafIterator, SamIterator, index, map, version
from .errors import (
    MinibwaError,
    MinibwaNotFoundError,
    MinibwaParseError,
    MinibwaRunError,
)
from .index import Index
from .records import Alignment, PafRecord

# Library logging convention: attach a NullHandler so the package stays silent
# unless the application configures logging.
logging.getLogger("minibwa").addHandler(logging.NullHandler())

__version__ = "0.1.0"

__all__ = [
    "Alignment",
    "Index",
    "MinibwaError",
    "MinibwaNotFoundError",
    "MinibwaParseError",
    "MinibwaRunError",
    "PafIterator",
    "PafRecord",
    "SamIterator",
    "__version__",
    "index",
    "map",
    "version",
]
