from __future__ import annotations

###############################################################################
# Imports                                                                     #
###############################################################################

# - Standard library -
import gc
import logging
import os
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import asyncio

# - Third-party -
from PIL import Image, ImageDraw

# - Local -
from .observer import Observer
from ..schemas import Update
from ..platform import get_window_manager, get_region_selector, get_screen_capturer
from .input import InputListener
from pathlib import Path

###############################################################################
# Screen observer                                                             #
###############################################################################


class Screen(Observer):
    """
    Capture before/after screenshots around user interactions.
    Blocking work (mss, Pillow, etc.) is executed in background threads.
    """

    _CAPTURE_FPS: int = 10  # Screenshots per second during capture
    _PERIODIC_SEC: int = 30  # Interval for periodic actions
    _DEBOUNCE_SEC: int = 1  # Minimum time between consecutive events
    _MON_START: int = 1  # First real display in mss (0 is virtual)
    _MEMORY_CLEANUP_INTERVAL: int = 30  # Frames between garbage collection
    _MAX_WORKERS: int = 4  # Thread pool size limit to prevent exhaustion

    # Scroll filtering constants
    _SCROLL_DEBOUNCE_SEC: float = 0.8  # Minimum time between scroll events
    _SCROLL_MIN_DISTANCE: float = 8.0  # Minimum scroll distance to log
    _SCROLL_MAX_FREQUENCY: int = 8  # Max scroll events per second
    _SCROLL_SESSION_TIMEOUT: float = 3.0  # Timeout for scroll sessions

    # -------------------------------- construction
    def __init__(
        self,
        screenshots_dir: str = "~/Downloads/records/screenshots",
        skip_when_visible: Optional[str | list[str]] = None,
        history_k: int = 10,
        debug: bool = False,
        keyboard_timeout: float = 2.0,
        scroll_debounce_sec: float = 0.5,
        scroll_min_distance: float = 5.0,
        scroll_max_frequency: int = 10,
        scroll_session_timeout: float = 2.0,
        upload_to_gdrive: bool = False,
        target_coordinates: Optional[tuple[int, int, int, int]] = None,
        track_window: Optional[str] = None,
        inactivity_timeout: float = 45 * 60,  # 45 minutes in seconds
    ) -> None:

        self.screens_dir = os.path.abspath(os.path.expanduser(screenshots_dir))
        os.makedirs(self.screens_dir, exist_ok=True)

        self._guard = (
            {skip_when_visible}
            if isinstance(skip_when_visible, str)
            else set(skip_when_visible or [])
        )

        self.debug = debug

        # Initialize platform window manager
        self._window_manager = get_window_manager()

        # Custom thread pool to prevent exhaustion
        self._thread_pool = ThreadPoolExecutor(max_workers=self._MAX_WORKERS)

        # Scroll filtering configuration
        self._scroll_debounce_sec = scroll_debounce_sec
        self._scroll_min_distance = scroll_min_distance
        self._scroll_max_frequency = scroll_max_frequency
        self._scroll_session_timeout = scroll_session_timeout

        # state shared with worker
        self._frames: Dict[int, Any] = {}
        self._frame_lock = asyncio.Lock()

        self._history: deque[str] = deque(maxlen=max(0, history_k))
        self._pending_event: Optional[dict] = None
        self._debounce_handle: Optional[asyncio.TimerHandle] = None

        # keyboard activity tracking
        self._key_activity_start: Optional[float] = None
        self._key_activity_timeout: float = (
            keyboard_timeout  # seconds of inactivity to consider session ended
        )
        self._key_screenshots: List[str] = []  # track intermediate screenshots for cleanup
        self._key_activity_lock = asyncio.Lock()

        # scroll activity tracking
        self._scroll_last_time: Optional[float] = None
        self._scroll_last_position: Optional[tuple[float, float]] = None
        self._scroll_session_start: Optional[float] = None
        self._scroll_event_count: int = 0
        self._scroll_lock = asyncio.Lock()

        # Inactivity timeout tracking
        self._inactivity_timeout = inactivity_timeout
        self._last_activity_time: Optional[float] = None
        self._inactivity_lock = asyncio.Lock()

        # Window tracking configuration (support for multiple windows)
        self._track_window = track_window  # Keep for backward compatibility
        self._tracked_windows: List[dict] = (
            []
        )  # List of {"id": window_id, "region": {...}, "last_title": "..."}
        self._last_window_titles: Dict[Any, str] = {}  # Track window titles to detect tab changes
        self._current_region_lock = asyncio.Lock()

        # Set target region from coordinates, window tracking, or mouse selection
        if track_window:
            # Will track window dynamically - get initial bounds and window ID
            result = self._window_manager.get_window_by_name(track_window)
            if result is None:
                raise ValueError(f"Window '{track_window}' not found")
            window_id, region = result
            self._tracked_windows.append({"id": window_id, "region": region})
            if self.debug:
                print(f"Tracking window '{track_window}' (ID: {window_id}): {region}")
        elif target_coordinates:
            # target_coordinates should be (left, top, width, height)
            left, top, width, height = target_coordinates
            region = {"left": left, "top": top, "width": width, "height": height}
            self._tracked_windows.append({"id": None, "region": region})
            if self.debug:
                print(f"Using target coordinates: {region}")
        else:
            # User selects region(s)/window(s) with mouse
            selector = get_region_selector()
            regions, window_ids = selector.select_regions()
            has_window_ids = False
            for region, window_id in zip(regions, window_ids):
                self._tracked_windows.append({"id": window_id, "region": region})
                if window_id is not None:
                    has_window_ids = True
                    print(
                        f"  Window ID {window_id}: {region['width']}x{region['height']} at ({region['left']}, {region['top']})"
                    )
                else:
                    print(
                        f"  Fixed region: {region['width']}x{region['height']} at ({region['left']}, {region['top']})"
                    )

            print(f"\nTotal: {len(self._tracked_windows)} window(s)/region(s)")
            if has_window_ids:
                print("Window verification: ENABLED (only captures when tracked window is on top)")
                # Debug: verify tracked window IDs are still valid and compare coordinates
                for tracked in self._tracked_windows:
                    if tracked["id"] is not None:
                        bounds = self._window_manager.get_window_bounds_by_id(tracked["id"])
                        if bounds:
                            print(f"  [OK] Window {tracked['id']} found")
                            # Compare selection coords with lookup coords
                            sel = tracked["region"]
                            print(
                                f"       Selection: ({sel['left']}, {sel['top']}, {sel['width']}x{sel['height']})"
                            )
                            print(
                                f"       Lookup:    ({bounds['left']}, {bounds['top']}, {bounds['width']}x{bounds['height']})"
                            )
                            # Check for mismatch
                            dx = abs(sel["left"] - bounds["left"])
                            dy = abs(sel["top"] - bounds["top"])
                            dw = abs(sel["width"] - bounds["width"])
                            dh = abs(sel["height"] - bounds["height"])
                            if dx > 5 or dy > 5 or dw > 5 or dh > 5:
                                print(
                                    "       [WARNING] Coordinate mismatch detected! "
                                    "Using lookup coords."
                                )
                                tracked["region"] = bounds  # Use fresh bounds from lookup
                            else:
                                print(
                                    f"       Coordinates match (delta: x={dx}, y={dy}, w={dw}, h={dh})"
                                )
                        else:
                            print(f"  [WARNING] Window {tracked['id']} NOT FOUND")
                            # Show what windows ARE available
                            try:
                                available = self._window_manager.get_visible_windows()
                                print(f"  Available windows ({len(available)}):")
                                for w in available[:5]:
                                    print(
                                        f"    ID={w['id']} '{w.get('title', '')[:30]}' {w['bounds']}"
                                    )
                            except Exception as e:
                                print(f"  Could not list available windows: {e}")
            else:
                print(
                    "Window verification: DISABLED (no window IDs - captures all activity in region)"
                )

        # call parent
        super().__init__()

        # Detect and store high-DPI status
        self._is_high_dpi = self._detect_high_dpi()

        # Adjust settings for high-DPI displays
        if self._is_high_dpi:
            self._CAPTURE_FPS = 3  # Even lower FPS for high-DPI displays
            self._MEMORY_CLEANUP_INTERVAL = 20  # More frequent cleanup
            if self.debug:
                logging.getLogger("Screen").info(
                    "High-DPI display detected, using conservative settings"
                )

    @staticmethod
    def _mon_for(x: float, y: float, mons: list[dict]) -> Optional[int]:
        for idx, m in enumerate(mons, 1):
            if m["left"] <= x < m["left"] + m["width"] and m["top"] <= y < m["top"] + m["height"]:
                return idx
        return None

    async def _update_tracked_regions(self) -> None:
        """
        Update the capture regions for all tracked windows and detect title changes (tab switches).
        Returns True if any window title changed (indicating tab switch).
        """
        title_changed = False

        async with self._current_region_lock:
            for tracked in self._tracked_windows:
                if tracked["id"] is not None:  # Only update tracked windows (not fixed regions)
                    new_region = await self._run_in_thread(
                        self._window_manager.get_window_bounds_by_id, tracked["id"]
                    )
                    if new_region:
                        old_region = tracked["region"]
                        tracked["region"] = new_region
                        # Log if region changed significantly
                        if old_region:
                            changed = (
                                abs(old_region["left"] - new_region["left"]) > 10
                                or abs(old_region["top"] - new_region["top"]) > 10
                                or abs(old_region["width"] - new_region["width"]) > 10
                                or abs(old_region["height"] - new_region["height"]) > 10
                            )
                            if changed:
                                logging.getLogger("Screen").info(
                                    f"Window (ID: {tracked['id']}) moved/resized: {new_region}"
                                )

                        # Check for window title changes (tab switches)
                        try:
                            current_title = await self._run_in_thread(
                                self._window_manager.get_window_title_by_id, tracked["id"]
                            )
                            if current_title:
                                last_title = tracked.get("last_title", "")
                                if last_title and current_title != last_title:
                                    title_changed = True
                                    tracked["last_title"] = current_title
                                    logging.getLogger("Screen").info(
                                        f"Window title changed (tab switch detected): '{last_title}' -> '{current_title}'"
                                    )
                                elif not last_title:
                                    # First time seeing this window, store title
                                    tracked["last_title"] = current_title
                        except Exception as e:
                            # Window manager might not support title retrieval
                            if self.debug:
                                logging.getLogger("Screen").debug(
                                    f"Could not get window title: {e}"
                                )
                    else:
                        # Window/region not found
                        if self.debug:
                            logging.getLogger("Screen").warning(
                                f"Tracked window (ID: {tracked['id']}) not found"
                            )

        return title_changed

    def _is_point_in_region(self, x: float, y: float, region: dict) -> bool:
        """Check if a point (in global coordinates) is inside a region."""
        return (
            region["left"] <= x < region["left"] + region["width"]
            and region["top"] <= y < region["top"] + region["height"]
        )

    def _find_region_for_point(
        self, x: float, y: float, verify_window: bool = True
    ) -> Optional[dict]:
        """Find which tracked window/region contains this point.

        Args:
            x: Screen X coordinate
            y: Screen Y coordinate
            verify_window: If True, verify that the topmost window at this point
                          matches our tracked window ID (prevents capturing unrelated
                          windows that happen to be at the same coordinates)

        Returns the tracked window dict {"id": ..., "region": ...} or None if not found
        or if the point is on a different window.
        """
        log = logging.getLogger("Screen")

        for tracked in self._tracked_windows:
            if self._is_point_in_region(x, y, tracked["region"]):
                # If we have a window ID and verification is enabled, check that
                # the topmost window at this point is actually our tracked window
                if verify_window and tracked["id"] is not None:
                    window_at_point = self._window_manager.get_window_at_point(x, y)
                    if window_at_point is not None and window_at_point != tracked["id"]:
                        # A different window is on top at this point - skip
                        log.info(
                            f"BLOCKED: Point ({x:.0f}, {y:.0f}) is in tracked region but window "
                            f"{window_at_point} is on top (expected {tracked['id']})"
                        )
                        continue
                    elif window_at_point is None and self.debug:
                        log.debug(f"Could not determine window at point ({x:.0f}, {y:.0f})")
                return tracked

        if self.debug:
            log.debug(f"Point ({x:.0f}, {y:.0f}) not in any tracked region")
        return None

    async def _update_activity_time(self) -> None:
        """Update the last activity timestamp."""
        async with self._inactivity_lock:
            self._last_activity_time = time.time()

    async def _run_in_thread(self, func, *args, **kwargs):
        """Run a function in the custom thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._thread_pool, lambda: func(*args, **kwargs))

    def _detect_high_dpi(self) -> bool:
        """Detect if running on a high-DPI display and adjust settings."""
        try:
            # Check display bounds from window manager
            bounds = self._window_manager.get_display_bounds()
            width = bounds[2] - bounds[0]
            height = bounds[3] - bounds[1]
            if width > 2560 or height > 1600:
                return True
        except Exception:
            pass
        return False

    def _should_log_scroll(self, x: float, y: float, dx: float, dy: float) -> bool:
        """
        Determine if a scroll event should be logged based on filtering criteria.

        Returns True if the scroll event should be logged, False otherwise.
        """
        current_time = time.time()
        scroll_magnitude = (dx**2 + dy**2) ** 0.5

        # Check if this is a new scroll session
        if (
            self._scroll_session_start is None
            or current_time - self._scroll_session_start > self._scroll_session_timeout
        ):
            # Start new session
            self._scroll_session_start = current_time
            self._scroll_event_count = 0
            self._scroll_last_position = (x, y)
            self._scroll_last_time = current_time
            return True

        # Check debounce time
        if (
            self._scroll_last_time is not None
            and current_time - self._scroll_last_time < self._scroll_debounce_sec
        ):
            return False

        # Check minimum distance
        if self._scroll_last_position is not None:
            distance = (
                (x - self._scroll_last_position[0]) ** 2 + (y - self._scroll_last_position[1]) ** 2
            ) ** 0.5
            # If the pointer hasn't moved much, still allow if the scroll magnitude is meaningful
            if (
                distance < self._scroll_min_distance
                and scroll_magnitude < self._scroll_min_distance
            ):
                return False

        # Check frequency limit
        self._scroll_event_count += 1
        session_duration = current_time - self._scroll_session_start
        if session_duration > 0:
            frequency = self._scroll_event_count / session_duration
            if frequency > self._scroll_max_frequency:
                return False

        # Update tracking state
        self._scroll_last_position = (x, y)
        self._scroll_last_time = current_time

        return True

    async def _cleanup_key_screenshots(self) -> None:
        """Clean up intermediate keyboard screenshots, keeping only first and last."""
        if len(self._key_screenshots) <= 2:
            return

        # Keep first and last, delete the rest
        to_delete = self._key_screenshots[1:-1]
        self._key_screenshots = [self._key_screenshots[0], self._key_screenshots[-1]]

        for path in to_delete:
            try:
                await self._run_in_thread(os.remove, path)
                if self.debug:
                    logging.getLogger("Screen").info(f"Deleted intermediate screenshot: {path}")
            except OSError:
                pass  # File might already be deleted

    # -------------------------------- I/O helpers
    async def _save_frame(
        self, frame, monitor_rect: dict, x, y, tag: str, box_color: str = "red", box_width: int = 10
    ) -> str:
        """
        Save a frame with bounding box and crosshair at the given position.
        """
        if frame is None:
            raise ValueError(f"Cannot save None frame for {tag}")
        ts = f"{time.time():.5f}"
        path = os.path.join(self.screens_dir, f"{ts}_{tag}.jpg")
        image = Image.frombytes("RGB", (frame.width, frame.height), frame.rgb)
        draw = ImageDraw.Draw(image)

        # Compute actual scale factor from frame vs monitor dimensions
        # This handles any DPI (1.0x, 1.5x, 2.0x, 2.5x, etc.) correctly
        scale_x = frame.width / monitor_rect["width"]
        scale_y = frame.height / monitor_rect["height"]

        # Convert logical point coordinates to physical pixel coordinates
        x_pixel = int(x * scale_x)
        y_pixel = int(y * scale_y)

        # Ensure coordinates are within bounds
        x_pixel = max(0, min(frame.width - 1, x_pixel))
        y_pixel = max(0, min(frame.height - 1, y_pixel))

        # Calculate bounding box with smaller, more precise padding
        # Use average scale for box size to handle non-uniform scaling
        avg_scale = (scale_x + scale_y) / 2.0
        box_size = int(30 * avg_scale)  # 30 logical points
        x1 = max(0, x_pixel - box_size)
        x2 = min(frame.width, x_pixel + box_size)
        y1 = max(0, y_pixel - box_size)
        y2 = min(frame.height, y_pixel + box_size)

        # Draw the bounding box if coordinates are valid
        if x1 < x2 and y1 < y2:
            draw.rectangle([x1, y1, x2, y2], outline=box_color, width=box_width)

        # Draw a crosshair at the exact mouse position
        crosshair_size = int(15 * avg_scale)  # 15 logical points
        crosshair_width = max(2, int(3 * avg_scale))

        # Horizontal line
        h_x1 = max(0, x_pixel - crosshair_size)
        h_x2 = min(frame.width, x_pixel + crosshair_size)
        draw.line([(h_x1, y_pixel), (h_x2, y_pixel)], fill=box_color, width=crosshair_width)

        # Vertical line
        v_y1 = max(0, y_pixel - crosshair_size)
        v_y2 = min(frame.height, y_pixel + crosshair_size)
        draw.line([(x_pixel, v_y1), (x_pixel, v_y2)], fill=box_color, width=crosshair_width)

        # Save with lower quality to reduce memory usage
        await self._run_in_thread(
            image.save,
            path,
            "JPEG",
            quality=70,  # Reduced from 90 to 70
            optimize=True,  # Enable optimization
        )

        # Explicitly delete image objects to free memory
        del draw
        del image

        return path

    async def _process_and_emit(
        self,
        before_path: str,
        after_path: str | None,
        action: str | None,
        ev: dict | None,
    ) -> None:
        if "scroll" in action:
            # Include scroll delta information
            scroll_info = ev.get("scroll", (0, 0))
            step = f"scroll({ev['position'][0]:.1f}, {ev['position'][1]:.1f}, dx={scroll_info[0]:.2f}, dy={scroll_info[1]:.2f})"
            await self.update_queue.put(Update(content=step, content_type="input_text"))
        elif "click" in action:
            step = f"{action}({ev['position'][0]:.1f}, {ev['position'][1]:.1f})"
            await self.update_queue.put(Update(content=step, content_type="input_text"))
        else:
            step = f"{action}({ev['text']})"
            await self.update_queue.put(Update(content=step, content_type="input_text"))

    async def stop(self) -> None:
        """Stop the observer and clean up resources."""
        await super().stop()

        # Clean up frame objects
        async with self._frame_lock:
            for frame in self._frames.values():
                if frame is not None:
                    del frame
            self._frames.clear()

        # Force garbage collection
        await self._run_in_thread(gc.collect)

        # Shutdown thread pool
        if hasattr(self, "_thread_pool"):
            self._thread_pool.shutdown(wait=True)

    # -------------------------------- skip guard
    def _skip(self) -> bool:
        if not self._guard:
            return False

        # Check if any guard window is visible
        try:
            return any(
                win.get("metadata", {}).get("owner", "") in self._guard
                and win.get("metadata", {}).get("visible_ratio", 0) > 0
                for win in self._window_manager.get_visible_windows()
            )
        except Exception:
            return False

    # -------------------------------- main async worker
    async def _worker(self) -> None:  # overrides base class
        log = logging.getLogger("Screen")
        if self.debug:
            logging.basicConfig(
                level=logging.INFO, format="%(asctime)s [Screen] %(message)s", datefmt="%H:%M:%S"
            )
        else:
            log.addHandler(logging.NullHandler())
            log.propagate = False

        CAP_FPS = self._CAPTURE_FPS
        PERIOD = self._PERIODIC_SEC
        self._DEBOUNCE_SEC

        loop = asyncio.get_running_loop()

        # ------------------------------------------------------------------
        # Use platform-specific screen capturer (supports X11 and Wayland)
        # ------------------------------------------------------------------
        sct = get_screen_capturer()

        # Test capture to verify screen capture works
        if self._tracked_windows:
            test_region = self._tracked_windows[0]["region"]
            test_window_id = self._tracked_windows[0]["id"]
            try:
                test_frame = await self._run_in_thread(sct.grab, test_region, test_window_id)
                if test_frame:
                    capture_mode = "window-specific" if test_window_id else "region-based"
                    log.info(
                        f"[OK] Screen capture test successful ({type(sct).__name__}, {capture_mode})"
                    )
                    print(f"[OK] Screen capture working ({type(sct).__name__}, {capture_mode})")
                else:
                    log.warning("[!] Screen capture test returned None")
            except Exception as e:
                log.error(f"Screen capture test failed: {e}")
                print(f"[!] Screen capture test failed: {e}")

        try:
            # Initialize mons list - will be updated dynamically for tracked windows
            if self._tracked_windows:
                # Use the tracked windows/regions
                if self.debug:
                    log.info(f"Recording {len(self._tracked_windows)} window(s)/region(s)")
            else:
                # Use all monitors (backward compatibility)
                if self.debug:
                    log.info("Recording all monitors")

            # ---- nested helper inside the async context ----
            async def flush():
                if self._pending_event is None:
                    return
                if self._skip():
                    self._pending_event = None
                    return

                ev = self._pending_event
                # Clear pending event immediately to avoid blocking next event
                self._pending_event = None

                # Update tracked regions before capturing "after" frame
                await self._update_tracked_regions()

                # Use the region from the event for capturing the "after" frame
                mon_rect = ev["monitor_rect"]
                window_id = ev.get("window_id")  # May be None for fixed regions
                if mon_rect is None:
                    if self.debug:
                        logging.getLogger("Screen").warning("Monitor region not available")
                    return

                try:
                    # Use window-specific capture if we have a window ID
                    aft = await self._run_in_thread(sct.grab, mon_rect, window_id)
                    if aft is None:
                        return
                except Exception as e:
                    if self.debug:
                        logging.getLogger("Screen").error(f"Failed to capture after frame: {e}")
                    return

                if "scroll" in ev["type"]:
                    scroll_info = ev.get("scroll", (0, 0))
                    pos = ev["position"]
                    step = f"scroll({pos[0]:.1f}, {pos[1]:.1f}, dx={scroll_info[0]:.2f}, dy={scroll_info[1]:.2f})"
                else:
                    step = f"{ev['type']}({ev['position'][0]:.1f}, {ev['position'][1]:.1f})"

                bef_path = await self._save_frame(
                    ev["before"],
                    ev["monitor_rect"],
                    ev["position"][0],
                    ev["position"][1],
                    f"{step}_before",
                )
                aft_path = await self._save_frame(
                    aft, mon_rect, ev["position"][0], ev["position"][1], f"{step}_after"
                )
                await self._process_and_emit(bef_path, aft_path, ev["type"], ev)

                log.info(f"{ev['type']} captured on window {ev['mon']}")

            # ---- mouse event reception ----
            async def mouse_event(x: float, y: float, typ: str):
                # Check if point is in any of our tracked windows/regions
                tracked = self._find_region_for_point(x, y)
                if tracked is None:
                    if self.debug:
                        log.info(
                            f"{typ:<6} @({x:7.1f},{y:7.1f}) outside tracked window(s), skipping"
                        )
                    return

                # Update regions for tracked windows
                if tracked["id"] is not None:
                    await self._update_tracked_regions()

                mon = tracked["region"]
                rel_x = x - mon["left"]
                rel_y = y - mon["top"]
                idx = self._tracked_windows.index(tracked) + 1  # 1-indexed for display

                # Grab FRESH "before" frame using current window rect
                # Use window-specific capture if we have a window ID (prevents capturing overlapping windows)
                window_id = tracked["id"]
                try:
                    bf = await self._run_in_thread(sct.grab, mon, window_id)
                    if bf is None:

                        return
                except Exception as e:
                    if self.debug:
                        log.error(f"Failed to capture before frame: {e}")

                    return

                log.info(
                    f"{typ:<6} @({rel_x:7.1f},{rel_y:7.1f}) -> win={idx}   {'(guarded)' if self._skip() else ''}"
                )
                if self._skip():
                    return

                # Update activity timestamp
                await self._update_activity_time()

                self._pending_event = {
                    "type": typ,
                    "position": (rel_x, rel_y),
                    "mon": idx,
                    "before": bf,
                    "monitor_rect": mon,
                    "window_id": window_id,
                }

                # Process asynchronously - don't wait for completion
                asyncio.create_task(flush())

            # ---- keyboard event reception ----
            async def key_event(key, typ: str):
                # Get current mouse position to determine active window
                x, y = input_listener.get_mouse_position()

                # Check if point is in any of our tracked windows/regions
                tracked = self._find_region_for_point(x, y)
                if tracked is None:
                    if self.debug:
                        log.info(f"Key {typ}: {str(key)} outside tracked window(s), skipping")
                    return

                # Update regions for tracked windows
                if tracked["id"] is not None:
                    await self._update_tracked_regions()

                mon = tracked["region"]
                window_id = tracked["id"]
                rel_x = x - mon["left"]
                rel_y = y - mon["top"]
                idx = self._tracked_windows.index(tracked) + 1  # 1-indexed for display

                # Grab FRESH frame using current window rect
                # Use window-specific capture if we have a window ID
                try:
                    frame = await self._run_in_thread(sct.grab, mon, window_id)
                except Exception as e:
                    if self.debug:
                        log.error(f"Failed to capture keyboard frame: {e}")
                    return

                log.info(f"Key {typ}: {str(key)} on window {idx}")

                # Update activity timestamp
                await self._update_activity_time()

                step = f"key_{typ}({str(key)})"
                await self.update_queue.put(Update(content=step, content_type="input_text"))

                async with self._key_activity_lock:
                    current_time = time.time()

                    # Check if this is the start of a new keyboard session
                    if (
                        self._key_activity_start is None
                        or current_time - self._key_activity_start > self._key_activity_timeout
                    ):
                        # Start new session - save first screenshot
                        self._key_activity_start = current_time
                        self._key_screenshots = []

                        # Save frame
                        screenshot_path = await self._save_frame(
                            frame, mon, rel_x, rel_y, f"{step}_first"
                        )
                        self._key_screenshots.append(screenshot_path)
                        log.info(
                            f"Started new keyboard session, saved first screenshot: {screenshot_path}"
                        )
                    else:
                        # Continue existing session - save intermediate screenshot
                        screenshot_path = await self._save_frame(
                            frame, mon, rel_x, rel_y, f"{step}_intermediate"
                        )
                        self._key_screenshots.append(screenshot_path)
                        log.info(
                            f"Continued keyboard session, saved intermediate screenshot: {screenshot_path}"
                        )

                    # Schedule cleanup of previous intermediate screenshots
                    if len(self._key_screenshots) > 2:
                        asyncio.create_task(self._cleanup_key_screenshots())

            # ---- scroll event reception ----
            async def scroll_event(x: float, y: float, dx: float, dy: float):
                # Apply scroll filtering
                async with self._scroll_lock:
                    if not self._should_log_scroll(x, y, dx, dy):
                        if self.debug:
                            log.info(f"Scroll filtered out: dx={dx:.2f}, dy={dy:.2f}")
                        return

                # Check if point is in any of our tracked windows/regions
                tracked = self._find_region_for_point(x, y)
                if tracked is None:
                    if self.debug:
                        log.info(f"Scroll @({x:7.1f},{y:7.1f}) outside tracked window(s), skipping")
                    return

                # Update regions for tracked windows
                if tracked["id"] is not None:
                    await self._update_tracked_regions()

                mon = tracked["region"]
                window_id = tracked["id"]
                rel_x = x - mon["left"]
                rel_y = y - mon["top"]
                idx = self._tracked_windows.index(tracked) + 1  # 1-indexed for display

                # Grab FRESH "before" frame using current window rect
                # Use window-specific capture if we have a window ID
                try:
                    bf = await self._run_in_thread(sct.grab, mon, window_id)
                except Exception as e:
                    if self.debug:
                        log.error(f"Failed to capture before frame: {e}")
                    return

                # Only log significant scroll movements
                scroll_magnitude = (dx**2 + dy**2) ** 0.5
                if scroll_magnitude < 1.0:  # Very small scrolls
                    if self.debug:
                        log.info(f"Scroll too small: magnitude={scroll_magnitude:.2f}")
                    return

                log.info(f"Scroll @({rel_x:7.1f},{rel_y:7.1f}) dx={dx:.2f} dy={dy:.2f} -> win={idx}")

                if self._skip():
                    return

                # Update activity timestamp
                await self._update_activity_time()

                self._pending_event = {
                    "type": "scroll",
                    "position": (rel_x, rel_y),
                    "mon": idx,
                    "before": bf,
                    "scroll": (dx, dy),
                    "monitor_rect": mon,
                    "window_id": window_id,
                }

                # Process event immediately
                await flush()

            # ---- Now that all event handlers are defined, set up the input listener ----
            def schedule_event(x: float, y: float, typ: str):
                # Non-blocking: just schedule the coroutine, don't wait for result
                asyncio.run_coroutine_threadsafe(mouse_event(x, y, typ), loop)

            def schedule_scroll_event(x: float, y: float, dx: float, dy: float):
                # Non-blocking: just schedule the coroutine, don't wait for result
                asyncio.run_coroutine_threadsafe(scroll_event(x, y, dx, dy), loop)

            def schedule_key_event(key, typ: str):
                # Non-blocking: just schedule the coroutine, don't wait for result
                asyncio.run_coroutine_threadsafe(key_event(key, typ), loop)

            input_listener = InputListener(
                on_click=lambda x, y, btn, prs: (
                    schedule_event(x, y, f"click_{btn.name}") if prs else None
                ),
                on_scroll=lambda x, y, dx, dy: schedule_scroll_event(x, y, dx, dy),
                on_press=lambda key: schedule_key_event(key, "press"),
            )
            input_listener.start()

            # Log if input monitoring is unavailable
            headless_input = not input_listener._available
            if headless_input:
                log.warning(
                    "[!] Input monitoring unavailable (headless mode or missing dependencies). "
                    "Screen capture will work, but mouse/keyboard events won't be captured. "
                    "Periodic captures will be enabled."
                )

            # ---- main capture loop ----
            log.info(f"Screen observer started - guarding {self._guard or '(none)'}")
            last_periodic = time.time()
            frame_count = 0

            # Initialize last activity time
            async with self._inactivity_lock:
                self._last_activity_time = time.time()

            while self._running:  # flag from base class
                t0 = time.time()

                # Check for inactivity timeout
                async with self._inactivity_lock:
                    if self._last_activity_time is not None:
                        inactive_duration = t0 - self._last_activity_time
                        if inactive_duration >= self._inactivity_timeout:
                            log.info(
                                f"Stopping recording due to {inactive_duration/60:.1f} minutes of inactivity"
                            )
                            print(f"\n{'='*70}")
                            print(
                                f"Recording automatically stopped after {inactive_duration/60:.1f} minutes of inactivity"
                            )
                            print(f"{'='*70}\n")
                            self._running = False
                            break

                # For tracked windows, update regions periodically
                # We capture frames at event time (not periodic)
                if self._tracked_windows:
                    try:
                        title_changed = await self._update_tracked_regions()
                    except Exception:
                        title_changed = False

                    # Trigger screenshot if window title changed (tab switch detected)
                    if title_changed:
                        try:
                            tracked = self._tracked_windows[0]
                            mon = tracked["region"]
                            window_id = tracked["id"]
                            frame = await self._run_in_thread(sct.grab, mon, window_id)
                            if frame:
                                timestamp = time.time()
                                path = await self._save_frame(
                                    frame,
                                    mon,
                                    mon["width"] / 2,
                                    mon["height"] / 2,
                                    f"tab_switch_{int(timestamp)}",
                                )
                                log.info(f"Tab switch detected - screenshot saved: {path}")
                                # Send update to database
                                await self.update_queue.put(
                                    Update(
                                        content=f"tab_switch: window title changed (screenshot: {Path(path).name})",
                                        content_type="input_text",
                                    )
                                )
                        except Exception as e:
                            if self.debug:
                                log.error(f"Tab switch capture error: {e}")

                    # Periodic captures: every PERIOD seconds (even when input is available)
                    # This ensures we capture content even when no events occur (e.g., reading, watching)
                    current_time = time.time()
                    if current_time - last_periodic >= PERIOD:
                        last_periodic = current_time
                        try:
                            tracked = self._tracked_windows[0]
                            mon = tracked["region"]
                            window_id = tracked["id"]
                            frame = await self._run_in_thread(sct.grab, mon, window_id)
                            if frame:
                                # Save periodic capture
                                timestamp = time.time()
                                path = await self._save_frame(
                                    frame,
                                    mon,
                                    mon["width"] / 2,
                                    mon["height"] / 2,
                                    f"periodic_{int(timestamp)}",
                                )
                                log.info(f"Periodic capture: {path}")
                                # Send update to database
                                await self.update_queue.put(
                                    Update(
                                        content=f"periodic_capture: screenshot saved ({Path(path).name})",
                                        content_type="input_text",
                                    )
                                )
                            else:
                                pass
                        except Exception as e:
                            if self.debug:
                                log.error(f"Periodic capture error: {e}")

                    # Legacy: In headless mode (no input events), do periodic captures based on frame count
                    # This is now redundant with time-based periodic captures above, but kept for compatibility
                    if headless_input and frame_count % (CAP_FPS * PERIOD) == 0:
                        # Capture a frame every PERIOD seconds in headless mode
                        try:
                            tracked = self._tracked_windows[0]
                            mon = tracked["region"]
                            window_id = tracked["id"]
                            frame = await self._run_in_thread(sct.grab, mon, window_id)
                            if frame:
                                # Save periodic capture
                                timestamp = time.time()
                                path = await self._save_frame(
                                    frame,
                                    mon,
                                    mon["width"] / 2,
                                    mon["height"] / 2,
                                    f"periodic_{int(timestamp)}",
                                )
                                log.info(f"Periodic capture in headless mode: {path}")
                            else:
                                pass
                        except Exception as e:
                            if self.debug:
                                log.error(f"Periodic capture error: {e}")

                                # Also send an update to database indicating periodic activity
                                await self.update_queue.put(
                                    Update(
                                        content=f"periodic_capture: headless_mode_active (screenshot saved: {Path(path).name})",
                                        content_type="input_text",
                                    )
                                )
                        except Exception as e:
                            if self.debug:
                                log.error(f"Periodic capture failed: {e}")

                    if self.debug and frame_count % 30 == 0:  # Log every 30 frames to avoid spam
                        log.info("Updated tracked window regions")
                    frame_count += 1

                    # Force garbage collection periodically to prevent memory buildup
                    if frame_count % self._MEMORY_CLEANUP_INTERVAL == 0:
                        await self._run_in_thread(gc.collect)

                # Check for keyboard session timeout
                current_time = time.time()
                if (
                    self._key_activity_start is not None
                    and current_time - self._key_activity_start > self._key_activity_timeout
                    and len(self._key_screenshots) > 1
                ):
                    # Session ended - rename last screenshot to indicate it's the final one
                    async with self._key_activity_lock:
                        if len(self._key_screenshots) > 1:
                            last_path = self._key_screenshots[-1]
                            final_path = last_path.replace("_intermediate", "_final")
                            try:
                                await self._run_in_thread(os.rename, last_path, final_path)
                                self._key_screenshots[-1] = final_path
                                log.info(
                                    f"Keyboard session ended, renamed final screenshot: {final_path}"
                                )
                            except OSError:
                                pass
                        self._key_activity_start = None
                        self._key_screenshots = []

                # fps throttle
                dt = time.time() - t0
                await asyncio.sleep(max(0, (1 / CAP_FPS) - dt))

            # shutdown
            input_listener.stop()

            # Final cleanup of any remaining keyboard session
            if self._key_activity_start is not None and len(self._key_screenshots) > 1:
                async with self._key_activity_lock:
                    last_path = self._key_screenshots[-1]
                    final_path = last_path.replace("_intermediate", "_final")
                    try:
                        await self._run_in_thread(os.rename, last_path, final_path)
                        log.info(f"Final keyboard session cleanup, renamed: {final_path}")
                    except OSError:
                        pass
                    await self._cleanup_key_screenshots()

        finally:
            # Clean up screen capturer
            if hasattr(sct, "close"):
                sct.close()
