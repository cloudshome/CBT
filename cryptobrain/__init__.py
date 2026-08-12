"""CryptoBrain — installable package facade.

The engine itself lives at the repo root (``main.py``, ``brain/``,
``engine/``). This package exists so ``pip install .`` exposes
``import cryptobrain`` and the ``cryptobrain`` console script — the
smoke-test contract of the P9 wheel-gate.
"""
from config import VERSION

__version__ = VERSION
