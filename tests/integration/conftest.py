"""Shared pytest fixtures for OHB integration tests.

This module provides fixtures consumed by all test modules in the
``tests/integration/`` directory.  Fixtures defined here are automatically
discovered by pytest's conftest mechanism — no explicit import is needed.

Prerequisites:
    A running OHB Docker container reachable at the URL specified by the
    ``OHB_TEST_HOST`` environment variable.  When the variable is unset,
    all integration tests are automatically skipped via ``pytestmark`` in
    each test module.

See Also:
    ``tests/TEST_README.md`` — Tier 6 (Integration Tests) for the full
    lifecycle documentation.
"""

import os

import pytest


@pytest.fixture
def base_url():
    """Return the base URL of the running OHB test container.

    The URL is read from the ``OHB_TEST_HOST`` environment variable.
    Falls back to ``http://localhost:8080`` when unset, although every
    integration test module independently skips itself if the variable
    is absent.

    Yields:
        str: Fully-qualified HTTP base URL (e.g., ``http://localhost:8085``).
    """
    return os.environ.get("OHB_TEST_HOST", "http://localhost:8080")
