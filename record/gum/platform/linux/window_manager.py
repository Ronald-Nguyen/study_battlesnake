import logging
import os
from typing import List, Optional, Tuple, Dict, Any

from ..base import WindowManagerBase

logger = logging.getLogger(__name__)

# X11 libraries
X11_AVAILABLE = False
try:
    from ewmh import EWMH
    from Xlib import display
    from Xlib.ext import randr

    X11_AVAILABLE = True
except ImportError:
    logger.debug("python-xlib/ewmh not available")

# Wayland Portal
from .wayland_portal import get_active_window_title_wayland  # noqa: E402


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


class LinuxWindowManager(WindowManagerBase):
    """
    Linux window manager supporting both X11 and Wayland.

    X11: Full support via EWMH/Xlib
    Wayland: Limited support - window enumeration is restricted by design
    """

    def __init__(self):
        self._wayland = _is_wayland()
        self._x11_available = X11_AVAILABLE and not self._wayland

        if self._x11_available:
            try:
                # Create a single display connection and share it with EWMH
                # This ensures consistent window state across all operations
                self.display = display.Display()
                self.ewmh = EWMH(display=self.display)
            except Exception as e:
                logger.warning("Failed to initialize X11: %s", e)
                self._x11_available = False
                self.ewmh = None
                self.display = None
        else:
            self.ewmh = None
            self.display = None

        if self._wayland:
            logger.info(
                "Wayland session detected. Window enumeration is limited. "
                "Some features may not be available."
            )

    @property
    def capabilities(self) -> Dict[str, bool]:
        if self._wayland:
            return {
                "supports_overlay": False,  # Wayland overlay requires layer-shell
                "supports_tab_title": False,
                "supports_clipboard": True,  # Via wl-clipboard
                "supports_window_enum": False,  # Wayland restricts this
                "coordinate_space": "logical",
            }
        return {
            "supports_overlay": True,
            "supports_tab_title": False,
            "supports_clipboard": True,
            "supports_window_enum": True,
            "coordinate_space": "logical",
        }

    def get_display_bounds(self) -> Tuple[float, float, float, float]:
        """Get combined bounds of all screens."""
        if self._wayland:
            return self._get_display_bounds_wayland()
        return self._get_display_bounds_x11()

    def _get_display_bounds_wayland(self) -> Tuple[float, float, float, float]:
        """Get display bounds on Wayland using various methods."""
        import subprocess
        import json
        import re

        # Try wlr-randr (wlroots compositors)
        try:
            result = subprocess.run(
                ["wlr-randr", "--json"], capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                min_x = min_y = 0
                max_x = max_y = 0
                for output in data:
                    if output.get("enabled"):
                        x = output.get("position", {}).get("x", 0)
                        y = output.get("position", {}).get("y", 0)
                        mode = output.get("current_mode", {})
                        w = mode.get("width", 1920)
                        h = mode.get("height", 1080)
                        max_x = max(max_x, x + w)
                        max_y = max(max_y, y + h)
                if max_x > 0:
                    logger.debug(
                        f"Display bounds from wlr-randr: ({min_x}, {min_y}, {max_x}, {max_y})"
                    )
                    return (min_x, min_y, max_x, max_y)
        except Exception as e:
            logger.debug("wlr-randr failed: %s", e)

        # Try gnome-monitor-config via dbus (GNOME specific)
        try:
            result = subprocess.run(
                [
                    "gdbus",
                    "call",
                    "--session",
                    "--dest",
                    "org.gnome.Mutter.DisplayConfig",
                    "--object-path",
                    "/org/gnome/Mutter/DisplayConfig",
                    "--method",
                    "org.gnome.Mutter.DisplayConfig.GetCurrentState",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                # Parse the complex output - just look for numbers that look like dimensions
                output = result.stdout
                # Look for monitor configurations
                dimensions = re.findall(r"\((\d{3,5}), (\d{3,5})\)", output)
                if dimensions:
                    max_x = max(int(w) for w, h in dimensions)
                    max_y = max(int(h) for w, h in dimensions)
                    if max_x > 0 and max_y > 0:
                        logger.debug(f"Display bounds from GNOME Mutter: (0, 0, {max_x}, {max_y})")
                        return (0, 0, max_x, max_y)
        except Exception as e:
            logger.debug("GNOME Mutter DisplayConfig failed: %s", e)

        # Try xrandr via XWayland
        try:
            result = subprocess.run(
                ["xrandr", "--current"], capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                max_x = max_y = 0
                # Look for lines like "1920x1080+0+0" or "primary 1920x1080+0+0"
                for line in result.stdout.split("\n"):
                    # Match both "WxH+X+Y" and just "WxH" patterns
                    match = re.search(r"(\d+)x(\d+)(?:\+(\d+)\+(\d+))?", line)
                    if match and "connected" in line:
                        w, h = int(match.group(1)), int(match.group(2))
                        x = int(match.group(3)) if match.group(3) else 0
                        y = int(match.group(4)) if match.group(4) else 0
                        max_x = max(max_x, x + w)
                        max_y = max(max_y, y + h)
                if max_x > 0:
                    logger.debug(f"Display bounds from xrandr: (0, 0, {max_x}, {max_y})")
                    return (0, 0, max_x, max_y)
        except Exception as e:
            logger.debug("xrandr fallback failed: %s", e)

        # Try reading from /sys/class/drm (last resort)
        try:
            import glob

            for mode_file in glob.glob("/sys/class/drm/card*/card*/modes"):
                try:
                    with open(mode_file, "r") as f:
                        first_line = f.readline().strip()
                        match = re.match(r"(\d+)x(\d+)", first_line)
                        if match:
                            w, h = int(match.group(1)), int(match.group(2))
                            logger.debug(f"Display bounds from /sys/class/drm: (0, 0, {w}, {h})")
                            return (0, 0, w, h)
                except Exception:
                    continue
        except Exception as e:
            logger.debug("DRM sysfs read failed: %s", e)

        # Default fallback
        logger.warning("Could not detect display bounds on Wayland, using default 1920x1080")
        return (0.0, 0.0, 1920.0, 1080.0)

    def _get_display_bounds_x11(self) -> Tuple[float, float, float, float]:
        """Get display bounds on X11."""
        if not self._x11_available:
            return (0.0, 0.0, 1920.0, 1080.0)

        screen = self.display.screen()
        root = screen.root

        try:
            resources = randr.get_screen_resources(root)
            min_x = min_y = float("inf")
            max_x = max_y = -float("inf")

            for crtc in resources.crtcs:
                info = randr.get_crtc_info(root.display, crtc, resources.config_timestamp)
                if info.width > 0 and info.height > 0:
                    x0, y0 = info.x, info.y
                    x1, y1 = x0 + info.width, y0 + info.height
                    min_x, min_y = min(min_x, x0), min(min_y, y0)
                    max_x, max_y = max(max_x, x1), max(max_y, y1)

            if min_x != float("inf"):
                return (min_x, min_y, max_x, max_y)
        except Exception as e:
            logger.debug("RandR failed: %s", e)

        # Fallback to screen dimensions
        return (0, 0, screen.width_in_pixels, screen.height_in_pixels)

    def get_visible_windows(self) -> List[Dict[str, Any]]:
        """Get list of visible windows."""
        if self._wayland:
            return self._get_visible_windows_wayland()
        return self._get_visible_windows_x11()

    def _get_visible_windows_wayland(self) -> List[Dict[str, Any]]:
        """
        Get visible windows on Wayland.

        This is severely limited by Wayland's security model.
        We can only get the active window on some compositors.
        """
        windows = []

        # Try to get at least the active window
        title = get_active_window_title_wayland()
        if title:
            # We don't have bounds information on Wayland
            bounds = self.get_display_bounds()
            windows.append(
                {
                    "id": "active",
                    "stable_id": "active",
                    "title": title,
                    "bounds": {
                        "left": 0,
                        "top": 0,
                        "width": int(bounds[2] - bounds[0]),
                        "height": int(bounds[3] - bounds[1]),
                    },
                    "scale": 1.0,
                    "metadata": {"wayland": True, "active": True},
                }
            )

        return windows

    def _get_visible_windows_x11(self) -> List[Dict[str, Any]]:
        """Get visible windows on X11."""
        if not self._x11_available:
            return []

        windows = []

        # First try EWMH (preferred method)
        try:
            root = self.display.screen().root
            client_list = self.ewmh.getClientList()
            if client_list:
                for win in client_list:
                    try:
                        geom = win.get_geometry()
                        name = self.ewmh.getWmName(win) or ""

                        # translate_coords converts window-relative coords to root (absolute) coords
                        coords = root.translate_coords(win, 0, 0)
                        abs_x = coords.x
                        abs_y = coords.y

                        # Log raw coordinates for debugging
                        logger.debug(
                            f"EWMH window {win.id} '{name[:30]}': "
                            f"translate_coords=({abs_x}, {abs_y}), "
                            f"geometry={geom.width}x{geom.height}"
                        )

                        bounds = {
                            "left": abs_x,
                            "top": abs_y,
                            "width": geom.width,
                            "height": geom.height,
                        }
                        if bounds["width"] <= 0 or bounds["height"] <= 0:
                            continue
                        windows.append(
                            {
                                "id": win.id,
                                "stable_id": str(win.id),
                                "title": name,
                                "bounds": bounds,
                                "scale": 1.0,
                                "metadata": {"wm_class": win.get_wm_class(), "source": "ewmh"},
                            }
                        )
                    except Exception as e:
                        logger.debug("Failed window read: %s", e)
        except Exception as e:
            logger.debug("EWMH enumeration failed: %s", e)

        # Fallback to wmctrl if EWMH returned nothing
        if not windows:
            logger.info("EWMH returned no windows, falling back to wmctrl")
            windows = self._get_windows_via_wmctrl()
        else:
            logger.debug(f"EWMH returned {len(windows)} windows")

        return windows

    def _get_windows_via_wmctrl(self) -> List[Dict[str, Any]]:
        """Fallback: Get windows using wmctrl command."""
        import subprocess

        windows = []
        try:
            result = subprocess.run(
                ["wmctrl", "-l", "-G"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split(None, 8)
                    if len(parts) >= 8:
                        try:
                            win_id = int(parts[0], 16)
                            x, y = int(parts[2]), int(parts[3])
                            w, h = int(parts[4]), int(parts[5])
                            title = parts[7] if len(parts) > 7 else ""

                            if w < 50 or h < 50:
                                continue
                            if parts[1] == "-1":  # Sticky window
                                continue

                            # Log raw wmctrl coordinates
                            logger.debug(
                                f"wmctrl window {win_id} '{title[:30]}': "
                                f"raw=({x}, {y}, {w}x{h})"
                            )

                            # Try to get frame extents to adjust coordinates
                            # wmctrl returns outer frame coords, we need client area
                            frame_left, frame_right, frame_top, frame_bottom = (
                                self._get_frame_extents(win_id)
                            )

                            if (
                                frame_left > 0
                                or frame_top > 0
                                or frame_right > 0
                                or frame_bottom > 0
                            ):
                                logger.debug(
                                    f"  Frame extents: left={frame_left}, right={frame_right}, "
                                    f"top={frame_top}, bottom={frame_bottom}"
                                )
                                adjusted_x = x + frame_left
                                adjusted_y = y + frame_top
                                adjusted_w = w - frame_left - frame_right
                                adjusted_h = h - frame_top - frame_bottom

                                # Use adjusted coords if they make sense
                                if adjusted_w > 50 and adjusted_h > 50:
                                    logger.debug(
                                        f"  Adjusted: ({adjusted_x}, {adjusted_y}, {adjusted_w}x{adjusted_h})"
                                    )
                                    x, y, w, h = adjusted_x, adjusted_y, adjusted_w, adjusted_h
                                else:
                                    logger.debug(
                                        "  Adjustment would result in invalid size, using raw coords"
                                    )
                            else:
                                logger.debug(
                                    "  No frame extents detected, using raw wmctrl coords"
                                )

                            windows.append(
                                {
                                    "id": win_id,
                                    "stable_id": str(win_id),
                                    "title": title,
                                    "bounds": {"left": x, "top": y, "width": w, "height": h},
                                    "scale": 1.0,
                                    "metadata": {"source": "wmctrl"},
                                }
                            )
                        except (ValueError, IndexError):
                            continue
                logger.info(f"Got {len(windows)} windows from wmctrl")
        except FileNotFoundError:
            logger.debug("wmctrl not found")
        except Exception as e:
            logger.debug(f"wmctrl failed: {e}")

        return windows

    def _get_frame_extents(self, window_id: int) -> Tuple[int, int, int, int]:
        """Get window frame extents (border sizes) for a window.

        Returns (left, right, top, bottom) border sizes in pixels.
        """
        if not self._x11_available:
            return (0, 0, 0, 0)

        try:
            from Xlib import X

            win = self.display.create_resource_object("window", window_id)

            # Query _NET_FRAME_EXTENTS property
            atom = self.display.intern_atom("_NET_FRAME_EXTENTS")
            prop = win.get_full_property(atom, X.AnyPropertyType)

            if prop and prop.value and len(prop.value) >= 4:
                # Format: left, right, top, bottom
                left, right, top, bottom = prop.value[:4]
                logger.debug(
                    f"Frame extents for {window_id}: left={left}, right={right}, top={top}, bottom={bottom}"
                )
                return (int(left), int(right), int(top), int(bottom))
        except Exception as e:
            logger.debug(f"Could not get frame extents for {window_id}: {e}")

        # Return 0s if we can't determine - safer than guessing
        return (0, 0, 0, 0)

    def get_window_by_name(self, name: str) -> Optional[Tuple[Any, Dict[str, Any]]]:
        """Get window by name."""
        for win in self.get_visible_windows():
            if win.get("title") == name:
                return win["id"], win["bounds"]
        return None

    def get_window_bounds_by_id(self, window_id: Any) -> Optional[Dict[str, Any]]:
        """Get window bounds by ID."""
        if self._wayland:
            # On Wayland, we can't track specific windows
            windows = self.get_visible_windows()
            if windows:
                return windows[0]["bounds"]
            return None

        if not self._x11_available:
            return None

        # Sync display to get fresh window state
        try:
            self.display.sync()
        except Exception:
            pass

        # First, try to find the window in the current client list
        # This is more reliable than create_resource_object for some window managers
        try:
            client_list = self.ewmh.getClientList()
            available_ids = [w.id for w in client_list] if client_list else []
            for win in client_list or []:
                if win.id == window_id:
                    geom = win.get_geometry()
                    root = self.display.screen().root
                    coords = root.translate_coords(win, 0, 0)
                    bounds = {
                        "left": coords.x,
                        "top": coords.y,
                        "width": geom.width,
                        "height": geom.height,
                    }
                    logger.debug(
                        f"get_window_bounds_by_id({window_id}): "
                        f"EWMH client list -> ({coords.x}, {coords.y}, {geom.width}x{geom.height})"
                    )
                    return bounds
            # Window not in list - log available IDs for debugging
            logger.debug(
                f"Window {window_id} not in EWMH client list. Available: {available_ids[:5]}..."
            )
        except Exception as e:
            logger.debug(f"EWMH client list lookup failed for {window_id}: {e}")

        # Fallback: try create_resource_object
        try:
            win = self.display.create_resource_object("window", window_id)
            geom = win.get_geometry()
            root = self.display.screen().root
            coords = root.translate_coords(win, 0, 0)
            bounds = {
                "left": coords.x,
                "top": coords.y,
                "width": geom.width,
                "height": geom.height,
            }
            logger.debug(
                f"get_window_bounds_by_id({window_id}): "
                f"create_resource_object -> ({coords.x}, {coords.y}, {geom.width}x{geom.height})"
            )
            return bounds
        except Exception as e:
            logger.debug(f"Window {window_id} X11 lookup failed: {e}")

        # Final fallback: try wmctrl
        try:
            for win in self._get_windows_via_wmctrl():
                if win["id"] == window_id:
                    logger.debug(
                        f"get_window_bounds_by_id({window_id}): "
                        f"wmctrl fallback -> {win['bounds']}"
                    )
                    return win["bounds"]
        except Exception as e:
            logger.debug(f"Window {window_id} wmctrl lookup failed: {e}")

        logger.warning(f"get_window_bounds_by_id({window_id}): window not found via any method")
        return None

    def list_available_windows(self) -> List[str]:
        """List available window names."""
        return [w.get("title", "") for w in self.get_visible_windows() if w.get("title")]

    def get_window_at_point(self, x: float, y: float) -> Optional[int]:
        """
        Get the window ID of the topmost window at the given screen coordinates.

        Returns the X11 window ID, or None if no window found or on Wayland.
        This is used to verify that a click is actually on the tracked window,
        not on another window that happens to be at the same coordinates.
        """
        if self._wayland:
            # Wayland doesn't allow querying windows at arbitrary points
            return None

        if not self._x11_available:
            return None

        try:
            from Xlib import X

            root = self.display.screen().root

            # Get all windows and check which one contains the point (front-to-back)
            # Using _NET_CLIENT_LIST_STACKING for proper stacking order
            window_ids = []
            try:
                stacking = root.get_full_property(
                    self.display.intern_atom("_NET_CLIENT_LIST_STACKING"), X.AnyPropertyType
                )
                if stacking and stacking.value:
                    # Windows are in bottom-to-top order, reverse for top-to-bottom
                    window_ids = list(reversed(stacking.value))
            except Exception as e:
                logger.debug(f"_NET_CLIENT_LIST_STACKING failed: {e}")

            # Fallback to regular client list if stacking didn't work
            if not window_ids:
                try:
                    window_ids = [w.id for w in self.ewmh.getClientList()]
                except Exception as e:
                    logger.debug(f"getClientList failed: {e}")
                    return None

            for wid in window_ids:
                try:
                    win = self.display.create_resource_object("window", wid)
                    geom = win.get_geometry()

                    # Get absolute coordinates
                    coords = root.translate_coords(win, 0, 0)
                    abs_x = coords.x
                    abs_y = coords.y

                    # Check if point is inside this window
                    if abs_x <= x < abs_x + geom.width and abs_y <= y < abs_y + geom.height:
                        return wid
                except Exception:
                    continue

            return None
        except Exception as e:
            logger.debug("Failed to get window at point (%s, %s): %s", x, y, e)
            return None

    def debug_list_windows(self) -> None:
        """Debug helper: print all currently visible windows and their IDs."""
        if not self._x11_available:
            logger.info("X11 not available")
            return

        try:
            windows = self.get_visible_windows()
            logger.info(f"Currently visible windows ({len(windows)}):")
            for w in windows:
                logger.info(f"  ID={w['id']} title='{w.get('title', '')}' bounds={w['bounds']}")
        except Exception as e:
            logger.error(f"Failed to list windows: {e}")
