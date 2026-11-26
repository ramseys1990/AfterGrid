#!/usr/bin/env python3
"""Keep the host CLI/import path while shipping update tools in the worker."""
import sys
from worker import core_update_tools as _implementation

if __name__ == "__main__":
    _implementation.main()
else:
    # Imports and monkeypatches refer to the actual implementation module.
    sys.modules[__name__] = _implementation

