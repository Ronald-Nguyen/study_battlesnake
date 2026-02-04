"""
Linux platform implementations.

This module can only be imported on Linux. Use the factory functions in
gum.platform (get_window_manager, get_clipboard, etc.) for cross-platform code.
"""

import sys

if not sys.platform.startswith("linux"):
    raise ImportError(
        f"The 'gum.platform.linux' module can only be imported on Linux, "
        f"not on '{sys.platform}'. Use gum.platform.get_window_manager() and "
        f"other factory functions for cross-platform code."
    )
