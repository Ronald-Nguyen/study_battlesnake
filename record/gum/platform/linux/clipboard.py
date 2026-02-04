import subprocess
import os
from typing import Optional
import logging

from ..base import ClipboardBase

logger = logging.getLogger(__name__)


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


class LinuxClipboard(ClipboardBase):
    """
    Linux clipboard implementation supporting both X11 and Wayland.

    X11: Uses xclip or xsel
    Wayland: Uses wl-paste from wl-clipboard package
    """

    def get_text(self) -> Optional[str]:
        if _is_wayland():
            return self._get_text_wayland()
        else:
            return self._get_text_x11()

    def _get_text_wayland(self) -> Optional[str]:
        """Get clipboard text on Wayland using wl-paste."""
        try:
            result = subprocess.run(
                ["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                return result.stdout
            else:
                logger.debug("wl-paste failed: %s", result.stderr)
                return None
        except FileNotFoundError:
            logger.warning(
                "wl-paste not found. Install wl-clipboard: " "sudo apt install wl-clipboard"
            )
            return None
        except subprocess.TimeoutExpired:
            logger.debug("wl-paste timed out")
            return None
        except Exception as e:
            logger.debug("Wayland clipboard error: %s", e)
            return None

    def _get_text_x11(self) -> Optional[str]:
        """Get clipboard text on X11 using xclip or xsel."""
        # Try xclip first
        for cmd in (
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
        ):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=1)
                if result.returncode == 0:
                    return result.stdout
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                logger.debug("Clipboard command timed out: %s", cmd[0])
            except Exception as e:
                logger.debug("X11 clipboard error with %s: %s", cmd[0], e)

        return None
