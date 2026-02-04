import logging
from typing import Optional

try:
    import win32gui
    import win32process

    WIN_APP_AVAILABLE = True
except ImportError:
    WIN_APP_AVAILABLE = False

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import uiautomation as auto

    UIA_AVAILABLE = True
except ImportError:
    UIA_AVAILABLE = False

from ..base import ActiveAppDetectorBase

logger = logging.getLogger(__name__)


class WindowsActiveAppDetector(ActiveAppDetectorBase):
    def get_active_app_name(self) -> str:
        if not WIN_APP_AVAILABLE or not PSUTIL_AVAILABLE:
            return ""
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            return process.name() or ""
        except Exception as e:
            logger.debug("Failed to get active app: %s", e)
            return ""

    def get_active_window_title(self, app_name: str) -> Optional[str]:
        if not WIN_APP_AVAILABLE:
            return None
        try:
            hwnd = win32gui.GetForegroundWindow()
            return win32gui.GetWindowText(hwnd)
        except Exception as e:
            logger.debug("Failed to get window title: %s", e)
            return None

    def get_browser_tab_title(self, browser_name: str) -> Optional[str]:
        # Baseline fallback to window title
        title = self.get_active_window_title(browser_name)
        if title:
            return title

        # Optional: try UIAutomation to inspect address bar/title if available
        if UIA_AVAILABLE:
            try:
                ctrl = auto.GetFocusedControl()
                if ctrl:
                    return ctrl.Name
            except Exception as e:
                logger.debug("UIAutomation failed: %s", e)
        return None

    def get_browser_tab_url(self, browser_name: str) -> Optional[str]:
        # Best-effort: UIAutomation can sometimes read the address bar value
        if UIA_AVAILABLE:
            try:
                ctrl = auto.GetFocusedControl()
                if ctrl:
                    # Heuristic: search for edit controls in the ancestor chain
                    parent = ctrl
                    for _ in range(5):
                        if not parent:
                            break
                        edit = (
                            parent.GetFirstChildControl()
                            if hasattr(parent, "GetFirstChildControl")
                            else None
                        )
                        while edit:
                            if (
                                edit.ControlTypeName == "Edit"
                                and edit.ValuePattern
                                and edit.ValuePattern.Value
                            ):
                                return edit.ValuePattern.Value
                            edit = edit.GetNextSiblingControl()
                        parent = parent.GetParentControl()
            except Exception as e:
                logger.debug("UIAutomation URL extraction failed: %s", e)
        return None
