"""Smoke tests: the package imports and exposes a version and CLI entrypoint."""

import astrocyte
from astrocyte.cli.main import main


def test_package_has_version() -> None:
    assert isinstance(astrocyte.__version__, str)
    assert astrocyte.__version__


def test_cli_runs() -> None:
    assert main([]) == 0
