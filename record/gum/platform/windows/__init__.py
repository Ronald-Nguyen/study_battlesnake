"""
Windows platform implementations.

This module can only be imported on Windows. Use the factory functions in
gum.platform (get_window_manager, get_clipboard, etc.) for cross-platform code.
"""

import sys

if sys.platform != "win32":
    raise ImportError(
        f"The 'gum.platform.windows' module can only be imported on Windows, "
        f"not on '{sys.platform}'. Use gum.platform.get_window_manager() and "
        f"other factory functions for cross-platform code."
    )
