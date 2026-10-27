"""Weekly office and programme performance pipeline package.

Submodules are imported explicitly. In particular, the HTTP-facing modules
(``queries``, ``status``, ``triggers``, ``schema``) must remain importable
without loading Prefect flow code, so this package intentionally does not
re-export the flow or task objects.
"""
