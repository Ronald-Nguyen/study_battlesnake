import Quartz
from typing import List, Optional, Tuple, Dict, Any
from ..base import WindowManagerBase
from shapely.geometry import box
from shapely.ops import unary_union


class MacOSWindowManager(WindowManagerBase):

    @property
    def capabilities(self) -> Dict[str, bool]:
        return {
            "supports_overlay": True,
            "supports_tab_title": True,  # Via AppleScript
            "supports_clipboard": True,
            "coordinate_space": "logical",
        }

    def get_display_bounds(self) -> Tuple[float, float, float, float]:
        """Return a bounding box enclosing **all** physical displays."""
        err, ids, cnt = Quartz.CGGetActiveDisplayList(16, None, None)
        if err != Quartz.kCGErrorSuccess:
            raise OSError(f"CGGetActiveDisplayList failed: {err}")

        min_x = min_y = float("inf")
        max_x = max_y = -float("inf")
        for did in ids[:cnt]:
            r = Quartz.CGDisplayBounds(did)
            x0, y0 = r.origin.x, r.origin.y
            x1, y1 = x0 + r.size.width, y0 + r.size.height
            min_x, min_y = min(min_x, x0), min(min_y, y0)
            max_x, max_y = max(max_x, x1), max(max_y, y1)
        return min_x, min_y, max_x, max_y

    def get_visible_windows(self) -> List[Dict[str, Any]]:
        """List *onscreen* windows with their visible-area ratio."""
        _, _, _, gmax_y = self.get_display_bounds()

        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListOptionIncludingWindow
        wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)

        occupied = None
        result = []

        for info in wins:
            owner = info.get("kCGWindowOwnerName", "")
            if owner in ("Dock", "WindowServer", "Window Server"):
                continue

            bounds = info.get("kCGWindowBounds", {})
            x, y, w, h = (
                bounds.get("X", 0),
                bounds.get("Y", 0),
                bounds.get("Width", 0),
                bounds.get("Height", 0),
            )
            if w <= 0 or h <= 0:
                continue

            inv_y = gmax_y - y - h  # Quartz->Shapely Y-flip
            poly = box(x, inv_y, x + w, inv_y + h)
            if poly.is_empty:
                continue

            visible = poly if occupied is None else poly.difference(occupied)
            if not visible.is_empty:
                # We return the raw info dict wrapped in our structure
                # Note: The original implementation returned (info, ratio)
                # Here we conform to the interface but can include extra metadata
                window_id = info.get("kCGWindowNumber")
                result.append(
                    {
                        "id": window_id,
                        "stable_id": str(window_id),
                        "title": owner,  # Using owner as title for now as kCGWindowName is often empty
                        "bounds": {"left": x, "top": y, "width": w, "height": h},
                        "scale": 1.0,  # Quartz logical pixels
                        "metadata": {
                            "owner": owner,
                            "layer": info.get("kCGWindowLayer", 0),
                            "visible_ratio": visible.area / poly.area,
                        },
                    }
                )
                occupied = poly if occupied is None else unary_union([occupied, poly])

        return result

    def get_window_by_name(self, name: str) -> Optional[Tuple[Any, Dict[str, Any]]]:
        """Get window ID and bounds by owner name."""
        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListOptionIncludingWindow
        wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)

        for info in wins:
            owner = info.get("kCGWindowOwnerName", "")
            if owner == name:
                window_id = info.get("kCGWindowNumber")
                if window_id is None:
                    continue

                bounds = info.get("kCGWindowBounds", {})
                x = int(bounds.get("X", 0))
                y = int(bounds.get("Y", 0))
                w = int(bounds.get("Width", 0))
                h = int(bounds.get("Height", 0))
                if w > 0 and h > 0:
                    bounds_dict = {"left": x, "top": y, "width": w, "height": h}
                    return (window_id, bounds_dict)
        return None

    def get_window_bounds_by_id(self, window_id: Any) -> Optional[Dict[str, Any]]:
        """Get window bounds by window ID."""
        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListOptionIncludingWindow
        wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)

        for info in wins:
            wid = info.get("kCGWindowNumber")
            if wid == window_id:
                bounds = info.get("kCGWindowBounds", {})
                x = int(bounds.get("X", 0))
                y = int(bounds.get("Y", 0))
                w = int(bounds.get("Width", 0))
                h = int(bounds.get("Height", 0))
                if w > 0 and h > 0:
                    return {"left": x, "top": y, "width": w, "height": h}
        return None

    def list_available_windows(self) -> List[str]:
        """List all available window names that can be tracked."""
        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListOptionIncludingWindow
        wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)

        window_names = set()
        for info in wins:
            owner = info.get("kCGWindowOwnerName", "")
            if owner and owner not in ("Dock", "WindowServer", "Window Server"):
                bounds = info.get("kCGWindowBounds", {})
                w = bounds.get("Width", 0)
                h = bounds.get("Height", 0)
                if w > 0 and h > 0:
                    window_names.add(owner)

        return sorted(window_names)

    def get_window_at_point(self, x: float, y: float) -> Optional[int]:
        """
        Get the window ID of the topmost window at the given screen coordinates.

        Returns the kCGWindowNumber of the window, or None if no window found.
        This is used to verify that a click is actually on the tracked window,
        not on another window that happens to be at the same coordinates.
        """
        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)

        if not wins:
            return None

        # Windows are returned in front-to-back order, so iterate to find the first match
        for info in wins:
            owner = info.get("kCGWindowOwnerName", "")
            if owner in ("Dock", "WindowServer", "Window Server"):
                continue

            layer = info.get("kCGWindowLayer", 0)
            # Skip floating windows and overlays
            if layer < 0:  # Normal windows have layer 0, floating > 0, desktop elements < 0
                continue

            bounds = info.get("kCGWindowBounds", {})
            wx = bounds.get("X", 0)
            wy = bounds.get("Y", 0)
            ww = bounds.get("Width", 0)
            wh = bounds.get("Height", 0)

            if ww <= 0 or wh <= 0:
                continue

            # Check if point is inside this window
            if wx <= x < wx + ww and wy <= y < wy + wh:
                return info.get("kCGWindowNumber")

        return None
