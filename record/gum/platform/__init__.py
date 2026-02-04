import sys
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import WindowManagerBase, ClipboardBase, ActiveAppDetectorBase, RegionSelectorBase

logger = logging.getLogger("PlatformFactory")


def get_platform() -> str:
    """Detect current platform."""
    if sys.platform == "darwin":
        return "macos"
    elif sys.platform == "win32":
        return "windows"
    elif sys.platform.startswith("linux"):
        return "linux"
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")


def get_window_manager() -> "WindowManagerBase":
    """Get platform-specific window manager."""
    platform = get_platform()
    try:
        if platform == "macos":
            from .macos.window_manager import MacOSWindowManager

            return MacOSWindowManager()
        elif platform == "windows":
            from .windows.window_manager import WindowsWindowManager

            return WindowsWindowManager()
        elif platform == "linux":
            from .linux.window_manager import LinuxWindowManager

            return LinuxWindowManager()
    except ImportError as e:
        logger.error(f"Failed to import window manager for {platform}: {e}")
        raise


def get_clipboard() -> "ClipboardBase":
    """Get platform-specific clipboard."""
    platform = get_platform()
    try:
        if platform == "macos":
            from .macos.clipboard import MacOSClipboard

            return MacOSClipboard()
        elif platform == "windows":
            from .windows.clipboard import WindowsClipboard

            return WindowsClipboard()
        elif platform == "linux":
            from .linux.clipboard import LinuxClipboard

            return LinuxClipboard()
    except ImportError as e:
        logger.error(f"Failed to import clipboard for {platform}: {e}")
        raise


def get_active_app_detector() -> "ActiveAppDetectorBase":
    """Get platform-specific active app detector."""
    platform = get_platform()
    try:
        if platform == "macos":
            from .macos.active_app import MacOSActiveAppDetector

            return MacOSActiveAppDetector()
        elif platform == "windows":
            from .windows.active_app import WindowsActiveAppDetector

            return WindowsActiveAppDetector()
        elif platform == "linux":
            from .linux.active_app import LinuxActiveAppDetector

            return LinuxActiveAppDetector()
    except ImportError as e:
        logger.error(f"Failed to import active app detector for {platform}: {e}")
        raise


def get_region_selector() -> "RegionSelectorBase":
    """Get platform-specific region selector."""
    platform = get_platform()
    try:
        if platform == "macos":
            from .macos.overlay import MacOSRegionSelector

            return MacOSRegionSelector()
        elif platform == "windows":
            from .windows.overlay import WindowsRegionSelector

            return WindowsRegionSelector()
        elif platform == "linux":
            from .linux.overlay import LinuxRegionSelector

            return LinuxRegionSelector()
    except ImportError as e:
        logger.error(f"Failed to import region selector for {platform}: {e}")
        raise


class ThreadSafeScreenCapture:
    """
    Thread-safe wrapper for MSS screen capture on Windows.

    MSS on Windows uses thread-local storage (srcdc device context), which
    can't be shared across threads. This wrapper creates a new MSS instance
    for each .grab() call, ensuring thread safety.
    """

    def grab(self, region, window_id=None):
        """Capture a region of the screen. Creates a new MSS instance per call.

        Args:
            region: Dict with 'left', 'top', 'width', 'height'
            window_id: Ignored on Windows (only used on Linux for window-specific capture)
        """
        import mss

        # Note: window_id is ignored on Windows - we always do region capture
        # Windows mss doesn't support window-specific capture like Linux maim does
        with mss.mss() as sct:
            return sct.grab(region)


class MacOSScreenCapture:
    """
    Wrapper for MSS screen capture on macOS.

    Accepts optional window_id parameter for API compatibility with Linux,
    but always performs region-based capture.
    """

    def __init__(self):
        import mss
        self._sct = mss.mss()

    def grab(self, region, window_id=None):
        """Capture a region of the screen.

        Args:
            region: Dict with 'left', 'top', 'width', 'height'
            window_id: Ignored on macOS (only used on Linux for window-specific capture)
        """
        return self._sct.grab(region)

    def close(self):
        """Clean up resources."""
        if hasattr(self, '_sct'):
            self._sct.close()


def get_screen_capturer():
    """
    Get platform-specific screen capturer.

    Returns an object with a .grab(region, window_id=None) method.
    On Linux/Wayland, this uses grim/gnome-screenshot/maim instead of mss.
    On Windows, uses a thread-safe wrapper around MSS.
    On macOS, uses a wrapper around MSS for API compatibility.

    The window_id parameter is only used on Linux for window-specific capture.
    """
    platform = get_platform()
    if platform == "linux":
        from .linux.screen_capture import LinuxScreenCapture

        return LinuxScreenCapture()
    elif platform == "windows":
        # Windows needs thread-safe wrapper due to MSS thread-local storage
        return ThreadSafeScreenCapture()
    else:
        # macOS uses wrapper for API compatibility
        return MacOSScreenCapture()
