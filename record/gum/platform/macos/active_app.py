import subprocess
from AppKit import NSWorkspace
from typing import Optional
from ..base import ActiveAppDetectorBase


class MacOSActiveAppDetector(ActiveAppDetectorBase):

    def get_active_app_name(self) -> str:
        """Get name of currently focused application."""
        try:
            workspace = NSWorkspace.sharedWorkspace()
            active_app = workspace.activeApplication()
            return active_app.get("NSApplicationName", "")
        except Exception:
            return ""

    def get_active_window_title(self, app_name: str) -> Optional[str]:
        """Get window title for desktop apps using AppleScript."""
        try:
            script = f'tell application "{app_name}" to get name of front window'
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=1
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def get_browser_tab_title(self, browser_name: str) -> Optional[str]:
        """Get active tab title from browser using AppleScript."""
        scripts = {
            "Google Chrome": 'tell application "Google Chrome" to get title of active tab of front window',
            "Safari": 'tell application "Safari" to get name of current tab of front window',
            "Brave Browser": 'tell application "Brave Browser" to get title of active tab of front window',
            "Firefox": 'tell application "Firefox" to get name of current tab of front window',
            "Microsoft Edge": 'tell application "Microsoft Edge" to get title of active tab of front window',
        }

        script = scripts.get(browser_name)
        if not script:
            return None

        # We can't use async in this synchronous interface directly,
        # so we use subprocess.run directly.
        # Note: The original implementation used asyncio.to_thread wrapped around subprocess.run
        # but here we are in a synchronous method.
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=1
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def get_browser_tab_url(self, browser_name: str) -> Optional[str]:
        """Get active tab URL from browser using AppleScript."""
        scripts = {
            "Google Chrome": 'tell application "Google Chrome" to get URL of active tab of front window',
            "Safari": 'tell application "Safari" to get URL of current tab of front window',
            "Brave Browser": 'tell application "Brave Browser" to get URL of active tab of front window',
            "Firefox": 'tell application "Firefox" to get URL of current tab of front window',
            "Microsoft Edge": 'tell application "Microsoft Edge" to get URL of active tab of front window',
        }

        script = scripts.get(browser_name)
        if not script:
            return None

        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=1
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None
