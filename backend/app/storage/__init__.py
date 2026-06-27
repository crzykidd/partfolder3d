"""Storage layer — key generation, path derivation, sidecar I/O, file inventory,
and the atomic-move/journal engine.

All filesystem operations that change on-disk structure must go through the
journaled-operation helper in `journal.py`; never mutate the filesystem directly.
"""
