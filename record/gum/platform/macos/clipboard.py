from AppKit import NSPasteboard
from typing import Optional
from ..base import ClipboardBase


class MacOSClipboard(ClipboardBase):

    def get_text(self) -> Optional[str]:
        """Get current clipboard text content."""
        try:
            pasteboard = NSPasteboard.generalPasteboard()
            return pasteboard.stringForType_("public.utf8-plain-text")
        except Exception:
            return None
