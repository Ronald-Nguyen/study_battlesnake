"""
AI Activity Detector Observer

Monitors AI tool usage through a hybrid approach:
1. Window title detection (which AI tool is active)
2. Clipboard monitoring (what was copied from AI)
3. OCR sampling (periodic text extraction from screenshots)

Supports:
- Web UIs: ChatGPT, Claude, Gemini
- Desktop apps: Claude Desktop, Cursor
"""

from __future__ import annotations
import asyncio
import logging
import time
from datetime import datetime
from typing import Optional
from pathlib import Path

from .observer import Observer
from ..schemas import Update
from ..platform import get_active_app_detector, get_clipboard


class AIActivityDetector(Observer):
    """
    Hybrid AI activity monitoring combining:
    - Window/app detection for identifying AI tools
    - Clipboard monitoring for copy-paste tracking
    - Periodic OCR for capturing conversation content
    """

    # AI tools to detect
    AI_TOOLS = {
        # Desktop applications
        "cursor": "Cursor",
        "claude": "Claude Desktop",
        # Browser-based (detected via tab title)
        "chatgpt": "ChatGPT Web",
        "openai": "ChatGPT Web",
        "claude.ai": "Claude Web",
        "gemini": "Gemini",
        "copilot": "Copilot",
    }

    # Browsers to monitor for web AI tools
    BROWSERS = ["Google Chrome", "Safari", "Brave Browser", "Firefox", "Microsoft Edge"]

    def __init__(
        self,
        screenshots_dir: str = "data/screenshots",
        poll_interval: float = 0.5,
        debug: bool = False,
        data_directory: str = "data",
    ):
        """
        Initialize AI activity detector.

        Parameters
        ----------
        screenshots_dir : str
            Directory where screenshots are saved
        poll_interval : float
            How often to check window/clipboard (seconds)
        debug : bool
            Enable debug logging
        data_directory : str
            Directory to save conversation log file
        """
        self.screenshots_dir = Path(screenshots_dir).expanduser()
        self.poll_interval = poll_interval
        self.debug = debug

        # Conversation log file
        self.data_dir = Path(data_directory).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.conversations_file = self.data_dir / "ai_conversations.jsonl"

        # Platform adapters
        self._app_detector = get_active_app_detector()
        self._clipboard = get_clipboard()

        # State tracking
        self._current_ai_tool: Optional[str] = None
        self._last_clipboard: str = ""
        self._ai_session_start: Optional[float] = None
        self._ai_session_start_time: Optional[str] = None  # ISO timestamp
        self._current_window_title: Optional[str] = None
        self._current_url: Optional[str] = None
        self._last_window_check: float = 0
        self._window_check_interval: float = 2.0  # Check window title every 2 seconds

        super().__init__()

    async def _worker(self):
        """Main monitoring loop."""
        log = logging.getLogger("AIActivity")
        if self.debug:
            log.setLevel(logging.INFO)
        else:
            log.addHandler(logging.NullHandler())

        log.info("AI Activity Detector started")

        while self._running:
            try:
                current_time = time.time()

                # 1. Check active application/window
                # Note: get_active_app_name is blocking but typically fast
                app_name = self._app_detector.get_active_app_name()

                detected_tool = await self._detect_ai_tool(app_name)

                # Handle AI tool transitions
                if detected_tool != self._current_ai_tool:
                    if detected_tool:
                        # Started using an AI tool
                        await self._on_ai_tool_activated(detected_tool, log)
                    elif self._current_ai_tool:
                        # Stopped using AI tool
                        await self._on_ai_tool_deactivated(log)

                    self._current_ai_tool = detected_tool

                # 2. Monitor clipboard when AI tool is active
                if self._current_ai_tool:
                    await self._check_clipboard(log)

                    # 3. Periodically capture window title and URL
                    if current_time - self._last_window_check >= self._window_check_interval:
                        await self._capture_window_metadata(app_name, log)
                        self._last_window_check = current_time

                    # 4. Count keystrokes (approximate from database observations)
                    # This is handled by checking database during deactivation

            except Exception as e:
                log.error(f"Error in AI activity detector: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    async def _detect_ai_tool(self, app_name: str) -> Optional[str]:
        """Detect if current window is an AI tool."""
        app_lower = app_name.lower()

        # Check desktop apps first (non-browser apps)
        # Desktop app keywords that are NOT browser-based
        desktop_keywords = ["cursor", "claude"]
        for keyword in desktop_keywords:
            if keyword in app_lower:
                tool_name = self.AI_TOOLS.get(keyword)
                if tool_name:
                    return tool_name

        # Check if it's a browser
        if app_name in self.BROWSERS:
            # Get browser tab title
            # Run in thread pool to avoid blocking async loop
            tab_title = await asyncio.to_thread(self._app_detector.get_browser_tab_title, app_name)
            if tab_title:
                tab_lower = tab_title.lower()
                # Check browser-based AI tools
                browser_keywords = ["chatgpt", "openai", "claude.ai", "gemini", "copilot"]
                for keyword in browser_keywords:
                    if keyword in tab_lower:
                        tool_name = self.AI_TOOLS.get(keyword)
                        if tool_name:
                            return tool_name

        return None

    async def _capture_window_metadata(self, app_name: str, log):
        """Capture window title and URL for AI tools."""
        try:
            window_title = None
            url = None

            # Get window title and URL based on app type
            if app_name in self.BROWSERS:
                # Browser - get tab title and URL
                window_title = await asyncio.to_thread(
                    self._app_detector.get_browser_tab_title, app_name
                )
                url = await asyncio.to_thread(self._app_detector.get_browser_tab_url, app_name)
            else:
                # Desktop app - get window title
                window_title = await asyncio.to_thread(
                    self._app_detector.get_active_window_title, app_name
                )

            # Only log if changed
            title_changed = window_title and window_title != self._current_window_title
            url_changed = url and url != self._current_url

            if title_changed or url_changed:
                # Create readable content
                content_parts = [f"AI Window Metadata - {self._current_ai_tool}"]
                if window_title:
                    content_parts.append(f"Title: {window_title}")
                if url:
                    content_parts.append(f"URL: {url}")

                await self.update_queue.put(
                    Update(content="\n".join(content_parts), content_type="ai_activity")
                )

                log.info(f"Window metadata: {window_title or 'No title'}")

                self._current_window_title = window_title
                self._current_url = url

        except Exception as e:
            log.error(f"Error capturing window metadata: {e}")

    async def _on_ai_tool_activated(self, tool_name: str, log):
        """Called when user switches to an AI tool."""
        self._ai_session_start = time.time()
        self._ai_session_start_time = datetime.now().isoformat()
        self._current_window_title = None
        self._current_url = None

        await self.update_queue.put(
            Update(content=f"Activated AI tool: {tool_name}", content_type="ai_activity")
        )
        log.info(f"User switched to {tool_name}")

    async def _on_ai_tool_deactivated(self, log):
        """Called when user switches away from AI tool."""
        if self._ai_session_start:
            duration = time.time() - self._ai_session_start

            # Create detailed session summary
            summary_parts = [
                f"Deactivated AI tool: {self._current_ai_tool}",
                f"Duration: {duration:.1f}s",
            ]

            if self._current_window_title:
                summary_parts.append(f"Last Title: {self._current_window_title}")
            if self._current_url:
                summary_parts.append(f"Last URL: {self._current_url}")

            await self.update_queue.put(
                Update(content="\n".join(summary_parts), content_type="ai_activity")
            )
            log.info(f"User left {self._current_ai_tool} after {duration:.1f}s")

        self._ai_session_start = None
        self._ai_session_start_time = None
        self._current_window_title = None
        self._current_url = None

    async def _check_clipboard(self, log):
        """Check if clipboard content changed (potential copy from AI)."""
        try:
            # Run in thread pool as clipboard access might be slow/blocking
            clipboard_content = await asyncio.to_thread(self._clipboard.get_text)

            if clipboard_content and clipboard_content != self._last_clipboard:
                # Content changed while AI tool is active
                content_preview = clipboard_content[:200]
                if len(clipboard_content) > 200:
                    content_preview += "..."

                await self.update_queue.put(
                    Update(
                        content=f"[COPIED from {self._current_ai_tool}]:\n{clipboard_content}",
                        content_type="ai_clipboard",
                    )
                )

                log.info(
                    f"Clipboard content copied from {self._current_ai_tool}: {content_preview}"
                )
                self._last_clipboard = clipboard_content

        except Exception as e:
            log.error(f"Error checking clipboard: {e}")
