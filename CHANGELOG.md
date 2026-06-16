# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-16

### Added

- Initial release.
- `index()`, `map()`, and `version()` subprocess wrappers for the `minibwa`
  aligner.
- SAM parsing into typed `Alignment` records and PAF parsing into typed
  `PafRecord` records, with lazily-parsed optional tags.
- Streaming `SamIterator` / `PafIterator` with header capture
  (`.header` / `.reference_lengths`), context-manager cleanup, and
  end-of-stream error checking.
- `Index` handle implementing `os.PathLike`, with sidecar-file listing,
  `exists()`, and `from_prefix()`.
- Clear error hierarchy: `MinibwaError`, `MinibwaNotFoundError`,
  `MinibwaRunError` (carries argv/returncode/stderr), `MinibwaParseError`
  (carries line/lineno).
- Full type hints and a PEP 561 `py.typed` marker.

### Notes

- The kwarg-to-flag translation tables target the `minibwa` CLI revision
  `0.1-r363`. If a future engine changes flag spellings or the `version`
  output, the single-table design in `_cli.py` localizes the adjustment.
