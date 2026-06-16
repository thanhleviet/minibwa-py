"""Sphinx configuration for the minibwa-py documentation.

The version is single-sourced from the installed package metadata so the docs
never drift from the released version. ``autodoc`` imports ``minibwa`` directly
(it is stdlib-only and importing it never touches the engine binary), so no
``autodoc_mock_imports`` is required.
"""

from __future__ import annotations

from importlib.metadata import version as _dist_version

# -- Project information -----------------------------------------------------

project = "minibwa-py"
author = "minibwa-py contributors"
copyright = "2026, minibwa-py contributors"

release = _dist_version("minibwa-py")
version = ".".join(release.split(".")[:2])

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "myst_parser",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "superpowers/**"]

# -- HTML output -------------------------------------------------------------

html_theme = "furo"
html_static_path = ["_static"]
html_title = f"minibwa-py {release}"

# -- autodoc / autosummary ---------------------------------------------------

# Summary tables on the API overview page link to the hand-written reference
# pages below, so stub generation is intentionally disabled (it would document
# each object twice and trip the warnings-as-errors build).
autosummary_generate = False

autodoc_member_order = "bysource"
autodoc_typehints = "description"
# Keep the generated constructor signature off the class header. The record
# types' real constructors are the ``from_*_line`` classmethods; their dataclass
# ``__init__`` takes private fields and is documented as unsupported.
autodoc_class_signature = "separated"
autodoc_default_options = {
    "members": True,
}
# ``undoc-members`` is enabled per-directive only on the records page, where the
# self-documenting flag properties (is_secondary, is_reverse, ...) carry no
# docstrings. Enabling it globally would also re-document the Index dataclass
# fields that napoleon already describes via the class ``Attributes:`` section,
# producing duplicate object descriptions.

# -- napoleon (Google-style docstrings) --------------------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_rtype = False

# -- intersphinx -------------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- MyST --------------------------------------------------------------------

myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 2
