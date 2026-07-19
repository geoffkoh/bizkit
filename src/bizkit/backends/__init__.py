"""Target-database adapters for the seven supported technologies.

One adapter per technology (Percona rides the MySQL dialect, spec D4).
Drivers are optional extras and lazy-imported (D3): ``import bizkit``
must succeed with zero drivers installed.
"""

from bizkit.backends.base import BaseBackend
from bizkit.backends.registry import available_backends, get_backend_class

__all__ = ["BaseBackend", "available_backends", "get_backend_class"]
