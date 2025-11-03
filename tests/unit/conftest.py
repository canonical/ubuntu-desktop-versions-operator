# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Pytest configuration for unit tests."""

import sys
from unittest.mock import MagicMock

# Mock opentelemetry modules before any imports that depend on them
sys.modules["opentelemetry"] = MagicMock()
sys.modules["opentelemetry.trace"] = MagicMock()
