import logging
from typing import List, Optional, Tuple, Dict, Any

try:
    import win32gui
    import win32api
    import win32con
    import win32process

    WIN_AVAILABLE = True
except ImportError:
    WIN_AVAILABLE = False

from ..base import WindowManagerBase

logger = logging.getLogger(__name__)


class WindowsWindowManager(WindowManagerBase):

    @property
    def capabilities(self) -> Dict[str, bool]:
        return {
            "supports_overlay": True,
            "supports_tab_title": False,  # basic fallback only via window title
            "supports_clipboard": True,
            "coordinate_space": "logical",
        }

    def _ensure_available(self):
        if not WIN_AVAILABLE:
            raise RuntimeError("pywin32 is required on Windows for window management")

    def get_display_bounds(self) -> Tuple[float, float, float, float]:
        self._ensure_available()
        left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        width = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
        height = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
        return (left, top, left + width, top + height)

    def get_visible_windows(self) -> List[Dict[str, Any]]:
        self._ensure_available()
        windows: List[Dict[str, Any]] = []

        def enum_callback(hwnd, results):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                rect = win32gui.GetWindowRect(hwnd)
                title = win32gui.GetWindowText(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                bounds = {
                    "left": rect[0],
                    "top": rect[1],
                    "width": rect[2] - rect[0],
                    "height": rect[3] - rect[1],
                }
                if bounds["width"] <= 0 or bounds["height"] <= 0:
                    return True
                results.append(
                    {
                        "id": hwnd,
                        "stable_id": str(hwnd),
                        "title": title,
                        "bounds": bounds,
                        "scale": 1.0,
                        "metadata": {"pid": pid},
                    }
                )
            except Exception as e:
                logger.debug("Failed to inspect window %s: %s", hwnd, e)
            return True

        win32gui.EnumWindows(enum_callback, windows)
        return windows

    def get_window_by_name(self, name: str) -> Optional[Tuple[Any, Dict[str, Any]]]:
        self._ensure_available()
        for win in self.get_visible_windows():
            if win.get("title") == name:
                return win["id"], win["bounds"]
        return None

    def get_window_bounds_by_id(self, window_id: Any) -> Optional[Dict[str, Any]]:
        self._ensure_available()
        try:
            rect = win32gui.GetWindowRect(window_id)
            return {
                "left": rect[0],
                "top": rect[1],
                "width": rect[2] - rect[0],
                "height": rect[3] - rect[1],
            }
        except Exception:
            return None

    def get_window_title_by_id(self, window_id: Any) -> Optional[str]:
        """Get window title by window ID."""
        self._ensure_available()
        try:
            return win32gui.GetWindowText(window_id)
        except Exception:
            return None

    def list_available_windows(self) -> List[str]:
        self._ensure_available()
        return [w.get("title", "") for w in self.get_visible_windows() if w.get("title")]

    def get_window_at_point(self, x: float, y: float) -> Optional[int]:
        """
        Get the window handle (HWND) of the topmost window at the given screen coordinates.

        Returns the HWND of the window, or None if no window found.
        This is used to verify that a click is actually on the tracked window,
        not on another window that happens to be at the same coordinates.
        """
        self._ensure_available()
        try:
            # WindowFromPoint returns the handle of the window at the specified point
            hwnd = win32gui.WindowFromPoint((int(x), int(y)))
            if hwnd:
                # Get the root owner window (for child windows like Chrome tabs)
                root_hwnd = win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
                return root_hwnd if root_hwnd else hwnd
            return None
        except Exception as e:
            logger.debug("Failed to get window at point (%s, %s): %s", x, y, e)
            return None
