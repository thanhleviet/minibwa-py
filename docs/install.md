# Installation

## Install the wrapper

```bash
pip install minibwa-py
```

`minibwa-py` is pure Python with **no runtime dependencies**.

## Install the engine

`minibwa-py` does **not** ship the aligner. Install the engine separately:

```bash
conda install -c bioconda minibwa
```

If the binary cannot be found you get a
[`MinibwaNotFoundError`](api/errors.md) whose message is:

```text
minibwa binary not found; install with "conda install -c bioconda minibwa", set MINIBWA_BIN, or pass binary=
```

## Binary discovery

The engine is located in this order:

1. an explicit `binary=` argument,
2. the `MINIBWA_BIN` environment variable,
3. `shutil.which("minibwa")` (i.e. your `PATH`).

```python
import minibwa

minibwa.version(binary="/opt/minibwa/bin/minibwa")
```

## Platform

Linux and macOS only (the engine is POSIX/conda-only). Windows is out of scope.

## Licensing

The Python wrapper code in this repository is licensed under the **MIT License**.

The `minibwa` engine is a **separate work** with its **own license**
(GPL-2.0-or-later for the default build). This package does not include, bundle,
or statically link any engine code — it only invokes the engine binary that you
install yourself. Your use of the engine is governed by the engine's own
license.
