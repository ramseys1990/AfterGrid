#!/usr/bin/env python3
"""Compatibility entry point for the worker-bundled recovery asset tools."""
import sys
from worker import recovery_assets as _implementation

if __name__ == "__main__":
    _implementation.main()
else:
    sys.modules[__name__] = _implementation

