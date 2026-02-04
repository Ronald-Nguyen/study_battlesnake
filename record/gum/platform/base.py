from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Dict, Any


class WindowManagerBase(ABC):
    """Abstract interface for window management operations."""

    @property
    def capabilities(self) -> Dict[str, bool]:
        """Advertise supported features (e.g., supports_overlay, supports_tab_title)."""
        return {}

    @abstractmethod
    def get_display_bounds(self) -> Tuple[float, float, float, float]:
        """
        Return normalized (min_x, min_y, max_x, max_y) in logical pixels across all displays.
        Coordinate system origin is top-left of primary display; include DPI scaling in bounds metadata when available.
        """

    @abstractmethod
    def get_visible_windows(self) -> List[Dict[str, Any]]:
        """
        Return list of visible windows with bounds, scale, and metadata.
        Each window dict should include an opaque native id and a stable string id.
        """

    @abstractmethod
    def get_window_by_name(self, name: str) -> Optional[Tuple[Any, Dict[str, Any]]]:
        """Get window ID and bounds by application/window name."""

    @abstractmethod
    def get_window_bounds_by_id(self, window_id: Any) -> Optional[Dict[str, Any]]:
        """Get current bounds for a window by its ID."""

    def get_window_title_by_id(self, window_id: Any) -> Optional[str]:
        """Get window title by window ID. Optional - returns None if not supported."""
        return None

    def get_window_at_point(self, x: float, y: float) -> Optional[Any]:
        """
        Get the window ID of the topmost window at the given screen coordinates.

        Returns the platform-specific window ID (kCGWindowNumber on macOS, HWND on Windows,
        X11 window ID on Linux), or None if not supported or no window found.

        This is used to verify that a click is actually on the tracked window,
        not on another window that happens to be at the same coordinates.
        """
        return None

    @abstractmethod
    def list_available_windows(self) -> List[str]:
        """List names of all available windows."""


class ClipboardBase(ABC):
    """Abstract interface for clipboard operations."""

    @abstractmethod
    def get_text(self) -> Optional[str]:
        """Get current clipboard text content; returns None when unsupported/unavailable."""


class ActiveAppDetectorBase(ABC):
    """Abstract interface for detecting active application."""

    @abstractmethod
    def get_active_app_name(self) -> str:
        """Get name of currently focused application."""

    @abstractmethod
    def get_active_window_title(self, app_name: str) -> Optional[str]:
        """Get title of the active window for the given application."""

    @abstractmethod
    def get_browser_tab_title(self, browser_name: str) -> Optional[str]:
        """Best-effort active tab title; return None when unsupported."""

    @abstractmethod
    def get_browser_tab_url(self, browser_name: str) -> Optional[str]:
        """Best-effort active tab URL; return None when unsupported."""


class RegionSelectorBase(ABC):
    """Abstract interface for interactive region selection."""

    @abstractmethod
    def select_regions(self) -> Tuple[List[Dict[str, Any]], List[Optional[Any]]]:
        """
        Show overlay for user to select windows/regions.
        Returns (list of region dicts, list of window IDs).
        """
