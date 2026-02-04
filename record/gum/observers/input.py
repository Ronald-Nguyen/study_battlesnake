import logging
from typing import Optional, Callable, Tuple

logger = logging.getLogger("InputObserver")


class InputListener:
    """
    Abstracts input monitoring to handle platform differences and permissions.
    """

    def __init__(
        self,
        on_click: Optional[Callable] = None,
        on_scroll: Optional[Callable] = None,
        on_press: Optional[Callable] = None,
        suppress: bool = False,
    ):
        self.on_click = on_click
        self.on_scroll = on_scroll
        self.on_press = on_press
        self.suppress = suppress

        self._mouse_listener = None
        self._keyboard_listener = None
        self._available = False

        try:
            from pynput import mouse, keyboard

            self._mouse_cls = mouse.Listener
            self._keyboard_cls = keyboard.Listener
            self._mouse_controller = mouse.Controller()
            self._available = True
        except ImportError:
            logger.warning("pynput not found. Input monitoring disabled.")
            self._available = False
        except Exception as e:
            logger.warning(f"Failed to initialize input libraries: {e}")
            self._available = False

    def start(self):
        if not self._available:
            return

        try:
            if self.on_click or self.on_scroll:
                self._mouse_listener = self._mouse_cls(
                    on_click=self.on_click, on_scroll=self.on_scroll, suppress=self.suppress
                )
                self._mouse_listener.start()

            if self.on_press:
                self._keyboard_listener = self._keyboard_cls(
                    on_press=self.on_press, suppress=self.suppress
                )
                self._keyboard_listener.start()

            logger.info("Input listeners started")

        except Exception as e:
            logger.error(f"Failed to start input listeners: {e}")
            self.stop()

    def stop(self):
        if self._mouse_listener:
            self._mouse_listener.stop()
            self._mouse_listener = None

        if self._keyboard_listener:
            self._keyboard_listener.stop()
            self._keyboard_listener = None

    def get_mouse_position(self) -> Tuple[int, int]:
        """Get current mouse position."""
        if self._available and self._mouse_controller:
            try:
                return self._mouse_controller.position
            except Exception:
                pass
        return (0, 0)
