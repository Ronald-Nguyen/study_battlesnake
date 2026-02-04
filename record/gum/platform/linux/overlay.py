"""
Linux region selection overlay.

X11: Window-based selection overlay (click windows to select)
Wayland: Uses slurp or falls back to full-screen capture
"""

import os
import subprocess
import logging
from typing import List, Dict, Optional, Any, Tuple

from ..base import RegionSelectorBase

logger = logging.getLogger(__name__)


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


class LinuxRegionSelector(RegionSelectorBase):
    """
    Linux region selector supporting both X11 and Wayland.
    """

    def select_regions(self) -> Tuple[List[Dict[str, Any]], List[Optional[int]]]:
        if _is_wayland():
            return self._select_regions_wayland()
        return self._select_regions_x11()

    def _select_regions_wayland(self) -> Tuple[List[Dict[str, Any]], List[Optional[int]]]:
        """
        Select region on Wayland using slurp or similar tools.
        """
        # Try slurp first (wlroots compositors)
        try:
            result = subprocess.run(
                ["slurp", "-f", "%x %y %w %h"], capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                x, y, w, h = map(int, result.stdout.strip().split())
                return ([{"left": x, "top": y, "width": w, "height": h}], [None])
            elif result.returncode == 1:
                raise RuntimeError("Selection cancelled")
        except FileNotFoundError:
            logger.info("slurp not found, trying alternatives...")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Selection timed out")
        except ValueError as e:
            logger.error("Failed to parse slurp output: %s", e)

        # Fallback: offer full screen capture
        print("\n" + "=" * 70)
        print("REGION SELECTION UNAVAILABLE")
        print("=" * 70)
        print("\nNo Wayland region selector tool found.")
        print("\nTo enable interactive region selection, install 'slurp':")
        print("  sudo apt install slurp  # or your package manager")
        print("\nOr use command-line options:")
        print("  gum --region 0,0,1920,1080    # Specify coordinates")
        print("  gum --fullscreen              # Use full screen")
        print("\nFalling back to FULL-SCREEN capture for now...")
        print("=" * 70)
        input("\nPress Enter to continue with full-screen capture, or Ctrl+C to abort...")

        from .window_manager import LinuxWindowManager

        wm = LinuxWindowManager()
        bounds = wm.get_display_bounds()

        region = {
            "left": int(bounds[0]),
            "top": int(bounds[1]),
            "width": int(bounds[2] - bounds[0]),
            "height": int(bounds[3] - bounds[1]),
        }

        print(f"\nUsing full screen: {region['width']}x{region['height']}")

        return ([region], [None])

    def _select_regions_x11(self) -> Tuple[List[Dict[str, Any]], List[Optional[int]]]:
        """Select windows on X11 using a window list dialog (VM-compatible)."""

        # Check if DISPLAY is available
        display = os.environ.get("DISPLAY")
        if not display:
            logger.warning("No DISPLAY environment variable set.")
            return self._fallback_to_fullscreen()

        # Get window list using wmctrl or xdotool
        windows = self._get_x11_windows()
        if not windows:
            logger.warning("Could not enumerate windows.")
            return self._fallback_to_fullscreen()

        # Use terminal-based selection (most reliable in VMs)
        return self._select_windows_terminal(windows)

    def _select_windows_terminal(
        self, windows: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Optional[int]]]:
        """Select windows using terminal-based menu (works in VMs)."""

        print("\n" + "=" * 70)
        print("WINDOW SELECTION")
        print("=" * 70)
        print("\nAvailable windows:\n")

        for i, win in enumerate(windows, 1):
            title = win.get("title", "Unknown")[:50]
            size = f"{win['width']}x{win['height']}"
            pos = f"at ({win['left']}, {win['top']})"
            source = win.get("source", "unknown")
            print(f"  [{i}] {title}")
            print(f"      Size: {size} {pos} [coords: {source}]")
            print()

        print("  [A] Select ALL windows")
        print("  [F] Use FULLSCREEN")
        print("  [Q] Quit/Cancel")
        print()
        print("=" * 70)

        selected_windows: List[Dict[str, Any]] = []
        selected_ids: List[Optional[int]] = []

        while True:
            try:
                choice = (
                    input("\nEnter window number(s) to record (comma-separated, e.g., '1,2,3'): ")
                    .strip()
                    .upper()
                )

                if choice == "Q":
                    raise RuntimeError("Selection cancelled by user")

                if choice == "F":
                    return self._fallback_to_fullscreen()

                if choice == "A":
                    # Select all windows
                    for win in windows:
                        selected_windows.append(
                            {
                                "left": win["left"],
                                "top": win["top"],
                                "width": win["width"],
                                "height": win["height"],
                            }
                        )
                        selected_ids.append(win.get("window_id"))
                    print(f"\nSelected ALL {len(windows)} windows")
                    break

                # Parse comma-separated numbers
                indices = []
                for part in choice.split(","):
                    part = part.strip()
                    if part.isdigit():
                        idx = int(part)
                        if 1 <= idx <= len(windows):
                            indices.append(idx - 1)
                        else:
                            print(f"Invalid number: {idx}. Must be between 1 and {len(windows)}")
                            continue

                if not indices:
                    print("No valid windows selected. Try again.")
                    continue

                # Add selected windows
                for idx in indices:
                    win = windows[idx]
                    selected_windows.append(
                        {
                            "left": win["left"],
                            "top": win["top"],
                            "width": win["width"],
                            "height": win["height"],
                        }
                    )
                    selected_ids.append(win.get("window_id"))
                    print(f"  + Selected: {win.get('title', 'Unknown')[:40]}")

                break

            except KeyboardInterrupt:
                raise RuntimeError("Selection cancelled by user")
            except EOFError:
                raise RuntimeError("Selection cancelled")

        if not selected_windows:
            return self._fallback_to_fullscreen()

        print(f"\n{len(selected_windows)} window(s) selected for recording.")
        print("=" * 70 + "\n")

        return selected_windows, selected_ids

    def _get_x11_windows(self) -> List[Dict[str, Any]]:
        """Get list of visible windows using X11 directly for accurate coordinates."""
        windows = []

        # First try using the window manager directly (most accurate coordinates)
        try:
            from .window_manager import LinuxWindowManager

            wm = LinuxWindowManager()
            if wm._x11_available:
                for win_info in wm.get_visible_windows():
                    bounds = win_info.get("bounds", {})
                    w = bounds.get("width", 0)
                    h = bounds.get("height", 0)

                    # Skip tiny windows
                    if w < 100 or h < 100:
                        continue

                    source = win_info.get("metadata", {}).get("source", "unknown")
                    windows.append(
                        {
                            "window_id": win_info.get("id"),
                            "left": bounds.get("left", 0),
                            "top": bounds.get("top", 0),
                            "width": w,
                            "height": h,
                            "title": win_info.get("title", ""),
                            "source": source,  # Track coordinate source for debugging
                        }
                    )

                if windows:
                    logger.info(f"Got {len(windows)} windows from X11 window manager")
                    # Log detailed coordinate info for debugging
                    for win in windows:
                        logger.debug(
                            f"  Window {win['window_id']} '{win.get('title', '')[:20]}': "
                            f"({win['left']}, {win['top']}, {win['width']}x{win['height']}) "
                            f"[source: {win.get('source', 'unknown')}]"
                        )
                    return windows
        except Exception as e:
            logger.debug(f"X11 window manager failed: {e}")

        # Fallback: Try wmctrl (may have coordinate offset issues with decorations)
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
                            # parts: id, desktop, x, y, width, height, client, title
                            x, y = int(parts[2]), int(parts[3])
                            w, h = int(parts[4]), int(parts[5])
                            title = parts[7] if len(parts) > 7 else ""

                            # Skip tiny windows and desktop
                            if w < 100 or h < 100:
                                continue
                            if parts[1] == "-1":  # Sticky window (often desktop)
                                continue

                            windows.append(
                                {
                                    "window_id": win_id,
                                    "left": x,
                                    "top": y,
                                    "width": w,
                                    "height": h,
                                    "title": title,
                                }
                            )
                        except (ValueError, IndexError):
                            continue
                if windows:
                    logger.warning(
                        "Using wmctrl coordinates - may be offset from actual window content"
                    )
                    return windows
        except FileNotFoundError:
            logger.debug("wmctrl not found, trying xdotool")
        except Exception as e:
            logger.debug(f"wmctrl failed: {e}")

        # Fallback to xdotool
        try:
            # Get list of window IDs
            result = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--name", ""],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for win_id_str in result.stdout.strip().split("\n"):
                    if not win_id_str:
                        continue
                    try:
                        win_id = int(win_id_str)
                        # Get window geometry
                        geom_result = subprocess.run(
                            ["xdotool", "getwindowgeometry", "--shell", str(win_id)],
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )
                        if geom_result.returncode == 0:
                            geom = {}
                            for line in geom_result.stdout.split("\n"):
                                if "=" in line:
                                    key, val = line.split("=", 1)
                                    geom[key] = int(val) if val.isdigit() else val

                            x = geom.get("X", 0)
                            y = geom.get("Y", 0)
                            w = geom.get("WIDTH", 0)
                            h = geom.get("HEIGHT", 0)

                            if w >= 100 and h >= 100:
                                windows.append(
                                    {
                                        "window_id": win_id,
                                        "left": x,
                                        "top": y,
                                        "width": w,
                                        "height": h,
                                    }
                                )
                    except (ValueError, subprocess.TimeoutExpired):
                        continue
        except FileNotFoundError:
            logger.debug("xdotool not found")
        except Exception as e:
            logger.debug(f"xdotool failed: {e}")

        return windows

    def _fallback_to_fullscreen(self) -> Tuple[List[Dict[str, Any]], List[Optional[int]]]:
        """Fallback to full screen capture."""
        from .window_manager import LinuxWindowManager

        wm = LinuxWindowManager()
        try:
            bounds = wm.get_display_bounds()
        except Exception as e:
            logger.error(f"Failed to get display bounds: {e}")
            bounds = (0, 0, 1920, 1080)

        return (
            [
                {
                    "left": int(bounds[0]),
                    "top": int(bounds[1]),
                    "width": int(bounds[2] - bounds[0]),
                    "height": int(bounds[3] - bounds[1]),
                }
            ],
            [None],
        )

    def _prompt_fullscreen_fallback(self) -> Tuple[List[Dict[str, Any]], List[Optional[int]]]:
        """Prompt user for fullscreen fallback after failed selection."""
        print("\n" + "=" * 70)
        print("REGION SELECTION CANCELLED OR FAILED")
        print("=" * 70)
        print("\nOptions:")
        print("  1. Press Enter to use FULL-SCREEN capture")
        print("  2. Press Ctrl+C to abort and try with --region flag")
        print("\nExample: python -m gum --region 0,0,1920,1080")
        print("=" * 70)

        try:
            input("\nPress Enter for fullscreen, or Ctrl+C to abort: ")
            return self._fallback_to_fullscreen()
        except KeyboardInterrupt:
            raise RuntimeError("Selection cancelled by user")
