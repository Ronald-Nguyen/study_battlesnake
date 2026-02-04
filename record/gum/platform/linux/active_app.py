import logging
import os
import subprocess
from typing import Optional

from ..base import ActiveAppDetectorBase
from .wayland_portal import get_active_window_title_wayland

logger = logging.getLogger(__name__)

# X11 libraries
X11_AVAILABLE = False
try:
    from ewmh import EWMH

    X11_AVAILABLE = True
except ImportError:
    pass


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


class LinuxActiveAppDetector(ActiveAppDetectorBase):
    """
    Linux active app detector supporting both X11 and Wayland.

    X11: Full support via EWMH
    Wayland: Limited support via compositor-specific tools
    """

    def __init__(self):
        self._wayland = _is_wayland()
        self._x11_available = X11_AVAILABLE and not self._wayland

        if self._x11_available:
            try:
                self.ewmh = EWMH()
            except Exception as e:
                logger.warning("Failed to initialize EWMH: %s", e)
                self._x11_available = False
                self.ewmh = None
        else:
            self.ewmh = None

    def get_active_app_name(self) -> str:
        """Get active application name."""
        if self._wayland:
            return self._get_active_app_wayland()
        return self._get_active_app_x11()

    def _get_active_app_wayland(self) -> str:
        """Get active app on Wayland."""
        # Try to get window title and extract app name
        title = get_active_window_title_wayland()
        if title:
            # Often the app name is the last part after " - " or " -- "
            for sep in [" -- ", " - ", " - "]:
                if sep in title:
                    return title.split(sep)[-1].strip()
            return title
        return ""

    def _get_active_app_x11(self) -> str:
        """Get active app on X11."""
        if not self._x11_available:
            return ""
        try:
            active = self.ewmh.getActiveWindow()
            if active:
                wm_class = active.get_wm_class()
                if wm_class:
                    return wm_class[1]  # Instance name
        except Exception as e:
            logger.debug("Failed to get active app: %s", e)
        return ""

    def get_active_window_title(self, app_name: str) -> Optional[str]:
        """Get active window title."""
        if self._wayland:
            return get_active_window_title_wayland()

        if not self._x11_available:
            return None
        try:
            active = self.ewmh.getActiveWindow()
            if active:
                return self.ewmh.getWmName(active)
        except Exception as e:
            logger.debug("Failed to get window title: %s", e)
        return None

    def get_browser_tab_title(self, browser_name: str) -> Optional[str]:
        """Get browser tab title (falls back to window title)."""
        if self._wayland:
            title = get_active_window_title_wayland()
            if title:
                return title
            return None

        # X11: use xdotool
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug("xdotool failed: %s", e)

        return None

    def get_browser_tab_url(self, browser_name: str) -> Optional[str]:
        """
        Get browser tab URL.

        Not reliably available on Linux without browser extensions.
        """
        # This would require:
        # - Browser extension
        # - Accessibility API (AT-SPI2, but limited browser support)
        # - DBus interface (browser-specific)
        return None
