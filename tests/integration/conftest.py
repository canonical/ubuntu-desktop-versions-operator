# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Integration test fixtures and configuration."""

import subprocess
from pathlib import Path

import jubilant
from pytest import fixture


@fixture(scope="module")
def juju():
    """Provide a temporary Juju model for testing."""
    with jubilant.temp_model() as juju:
        yield juju


@fixture(scope="module")
def ubuntu_desktop_versions_charm():
    """Ubuntu desktop versions charm used for integration testing."""
    subprocess.run(
        ["/snap/bin/charmcraft", "pack", "--verbose"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return next(Path.glob(Path("."), "*.charm")).absolute()
