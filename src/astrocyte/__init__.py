"""Astrocyte — a Self-Hosted AI Operating System managed by agents.

The package version is derived from the git tag at build time (see ADR-008);
at runtime it is read back from installed package metadata.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("astrocyte")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    __version__ = "0.0.0"

__all__ = ["__version__"]
