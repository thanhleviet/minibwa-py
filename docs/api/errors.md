# Exceptions

Every failure surfaces through one of these. Catch {exc}`~minibwa.MinibwaError`
broadly or a specific subclass narrowly. The engine's own diagnostics (stderr,
return code) and the raw offending line are always preserved on the exception.

```{eval-rst}
.. currentmodule:: minibwa

.. autoexception:: MinibwaError
   :members:

.. autoexception:: MinibwaNotFoundError
   :members:

.. autoexception:: MinibwaRunError
   :members:

.. autoexception:: MinibwaParseError
   :members:
```
