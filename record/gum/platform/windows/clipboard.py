from typing import Optional
import logging

try:
    import win32clipboard

    WIN_CLIP_AVAILABLE = True
except ImportError:
    WIN_CLIP_AVAILABLE = False

from ..base import ClipboardBase

logger = logging.getLogger(__name__)


class WindowsClipboard(ClipboardBase):
    def get_text(self) -> Optional[str]:
        if not WIN_CLIP_AVAILABLE:
            logger.debug("win32clipboard not available")
            return None
        try:
            win32clipboard.OpenClipboard()
            data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            return data
        except Exception as e:
            logger.debug("Clipboard access failed: %s", e)
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
            return None
