"""
XDG Desktop Portal integration for Wayland.

Provides screen capture and limited window information on Wayland
using the Portal D-Bus APIs.

Requires: dbus-python or pydbus, and a Portal implementation (xdg-desktop-portal-gnome, etc.)
"""

import logging
import subprocess
import tempfile
import json
import re
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import D-Bus bindings
DBUS_AVAILABLE = False
try:
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop

    DBUS_AVAILABLE = True
except ImportError:
    logger.debug("dbus-python not available for Portal integration")

# Portal constants
PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
SCREENSHOT_INTERFACE = "org.freedesktop.portal.Screenshot"
SCREENCAST_INTERFACE = "org.freedesktop.portal.ScreenCast"


def is_portal_available() -> bool:
    """Check if XDG Desktop Portal is available."""
    if not DBUS_AVAILABLE:
        return False
    try:
        bus = dbus.SessionBus()
        bus.get_object(PORTAL_BUS_NAME, PORTAL_OBJECT_PATH)
        return True
    except Exception as e:
        logger.debug("Portal not available: %s", e)
        return False


class PortalScreenshot:
    """
    Take screenshots via XDG Desktop Portal.

    This works on Wayland without special permissions because
    the Portal shows a user consent dialog.
    """

    def __init__(self):
        if not DBUS_AVAILABLE:
            raise RuntimeError("dbus-python required for Portal screenshot")

        DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SessionBus()
        self.portal = self.bus.get_object(PORTAL_BUS_NAME, PORTAL_OBJECT_PATH)
        self.screenshot_iface = dbus.Interface(self.portal, SCREENSHOT_INTERFACE)

    def capture(self, interactive: bool = False) -> Optional[str]:
        """
        Capture a screenshot via Portal.

        Args:
            interactive: If True, let user select area. If False, capture full screen.

        Returns:
            Path to the captured image file, or None on failure.
        """
        try:
            # Request screenshot
            options = {
                "modal": dbus.Boolean(True),
                "interactive": dbus.Boolean(interactive),
            }

            # The Portal returns a request handle
            self.screenshot_iface.Screenshot("", options)

            # For now, use a simpler approach with gnome-screenshot or grim
            return self._fallback_capture()

        except Exception as e:
            logger.error("Portal screenshot failed: %s", e)
            return self._fallback_capture()

    def _fallback_capture(self) -> Optional[str]:
        """Fallback to command-line screenshot tools."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            output_path = f.name

        # Try grim (Wayland-native)
        try:
            result = subprocess.run(["grim", output_path], capture_output=True, timeout=5)
            if result.returncode == 0 and Path(output_path).exists():
                return output_path
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug("grim failed: %s", e)

        # Try gnome-screenshot (works on GNOME Wayland)
        try:
            result = subprocess.run(
                ["gnome-screenshot", "-f", output_path], capture_output=True, timeout=5
            )
            if result.returncode == 0 and Path(output_path).exists():
                return output_path
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug("gnome-screenshot failed: %s", e)

        # Try spectacle (KDE)
        try:
            result = subprocess.run(
                ["spectacle", "-b", "-n", "-o", output_path], capture_output=True, timeout=5
            )
            if result.returncode == 0 and Path(output_path).exists():
                return output_path
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug("spectacle failed: %s", e)

        logger.warning(
            "No Wayland screenshot tool found. Install one of: " "grim, gnome-screenshot, spectacle"
        )
        return None


class PortalScreenCast:
    """
    Screen recording via XDG Desktop Portal and PipeWire.

    This is more complex and requires PipeWire integration.
    For MVP, we provide a simpler approach using wf-recorder or OBS.
    """

    @staticmethod
    def is_available() -> bool:
        """Check if ScreenCast portal is available."""
        if not DBUS_AVAILABLE:
            return False
        try:
            bus = dbus.SessionBus()
            portal = bus.get_object(PORTAL_BUS_NAME, PORTAL_OBJECT_PATH)
            dbus.Interface(portal, SCREENCAST_INTERFACE)
            # Check version
            props = dbus.Interface(portal, "org.freedesktop.DBus.Properties")
            version = props.Get(SCREENCAST_INTERFACE, "version")
            return version >= 1
        except Exception:
            return False

    @staticmethod
    def get_pipewire_fd() -> Optional[int]:
        """
        Get a PipeWire file descriptor for screen capture.

        This is the proper way to capture on Wayland but requires
        PipeWire/GStreamer integration which is complex.

        Returns:
            PipeWire node file descriptor, or None.
        """
        # This requires a full Portal session flow:
        # 1. CreateSession
        # 2. SelectSources
        # 3. Start
        # 4. Get PipeWire fd from response
        #
        # For now, return None and let callers use fallback methods
        logger.info(
            "PipeWire screen capture not yet implemented. " "Using fallback screenshot methods."
        )
        return None


def get_active_window_title_wayland() -> Optional[str]:
    """
    Get active window title on Wayland.

    This is compositor-specific and limited. We try several approaches.
    """
    # Try hyprctl (Hyprland)
    try:
        result = subprocess.run(
            ["hyprctl", "activewindow", "-j"], capture_output=True, text=True, timeout=1
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("title")
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    except Exception as e:
        logger.debug("hyprctl failed: %s", e)

    # Try swaymsg (Sway)
    try:
        result = subprocess.run(
            ["swaymsg", "-t", "get_tree"], capture_output=True, text=True, timeout=1
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Find focused window in tree
            return _find_focused_window_sway(data)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    except Exception as e:
        logger.debug("swaymsg failed: %s", e)

    # Try kdotool (KDE Plasma Wayland)
    try:
        result = subprocess.run(
            ["kdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("kdotool failed: %s", e)

    # Try gdbus for GNOME (limited)
    try:
        result = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.gnome.Shell",
                "--object-path",
                "/org/gnome/Shell",
                "--method",
                "org.gnome.Shell.Eval",
                'global.display.focus_window ? global.display.focus_window.title : ""',
            ],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0 and "true" in result.stdout:
            # Parse the output: (true, 'Window Title')
            match = re.search(r"'([^']*)'", result.stdout)
            if match:
                return match.group(1)
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.debug("GNOME Shell Eval failed: %s", e)

    return None


def _find_focused_window_sway(node: dict) -> Optional[str]:
    """Recursively find focused window in Sway tree."""
    if node.get("focused") and node.get("type") == "con":
        return node.get("name")

    for child in node.get("nodes", []) + node.get("floating_nodes", []):
        result = _find_focused_window_sway(child)
        if result:
            return result

    return None
