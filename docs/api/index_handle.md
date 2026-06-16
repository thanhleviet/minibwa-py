# Index handle

An immutable handle to a built index, returned by {func}`minibwa.index`. It
knows its sidecar files, can check whether they exist, and implements
`os.PathLike` so it can be passed straight back to {func}`minibwa.map`.

```{eval-rst}
.. currentmodule:: minibwa

.. autoclass:: Index
   :members:
```
