"""
Tests for observer modules.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestInputListener:
    """Tests for the InputListener abstraction."""

    def test_input_listener_creation(self):
        """InputListener should be creatable without errors."""
        from gum.observers.input import InputListener

        listener = InputListener()
        assert listener is not None

    def test_input_listener_callbacks(self):
        """InputListener should accept callback functions."""
        from gum.observers.input import InputListener

        on_click = MagicMock()
        on_scroll = MagicMock()
        on_press = MagicMock()

        listener = InputListener(on_click=on_click, on_scroll=on_scroll, on_press=on_press)

        assert listener.on_click == on_click
        assert listener.on_scroll == on_scroll
        assert listener.on_press == on_press

    def test_input_listener_start_stop(self):
        """InputListener start/stop should not raise."""
        from gum.observers.input import InputListener

        listener = InputListener()

        # These should not raise even if pynput is unavailable
        listener.start()
        listener.stop()

    def test_get_mouse_position_returns_tuple(self):
        """get_mouse_position should return a tuple of coordinates."""
        from gum.observers.input import InputListener

        listener = InputListener()

        pos = listener.get_mouse_position()
        assert isinstance(pos, tuple)
        assert len(pos) == 2


class TestAIActivityDetector:
    """Tests for AIActivityDetector with mocked platform."""

    @pytest.fixture
    def mock_platform(self):
        """Mock platform adapters for testing."""
        with patch("gum.observers.ai_activity.get_active_app_detector") as mock_detector, patch(
            "gum.observers.ai_activity.get_clipboard"
        ) as mock_clipboard:

            detector = MagicMock()
            detector.get_active_app_name.return_value = "TestApp"
            detector.get_browser_tab_title.return_value = None
            detector.get_browser_tab_url.return_value = None
            detector.get_active_window_title.return_value = "Test Window"
            mock_detector.return_value = detector

            clipboard = MagicMock()
            clipboard.get_text.return_value = "Test clipboard"
            mock_clipboard.return_value = clipboard

            yield {"detector": detector, "clipboard": clipboard}

    def test_ai_activity_detector_creation(self, mock_platform):
        """AIActivityDetector should be creatable with mocked platform."""
        from gum.observers.ai_activity import AIActivityDetector

        observer = AIActivityDetector()
        assert observer is not None

    def test_ai_tools_constant(self, mock_platform):
        """AIActivityDetector should have AI_TOOLS mapping."""
        from gum.observers.ai_activity import AIActivityDetector

        observer = AIActivityDetector()

        assert hasattr(observer, "AI_TOOLS")
        assert isinstance(observer.AI_TOOLS, dict)
        assert "cursor" in observer.AI_TOOLS
        assert "chatgpt" in observer.AI_TOOLS

    def test_browsers_constant(self, mock_platform):
        """AIActivityDetector should have BROWSERS list."""
        from gum.observers.ai_activity import AIActivityDetector

        observer = AIActivityDetector()

        assert hasattr(observer, "BROWSERS")
        assert isinstance(observer.BROWSERS, list)
        assert "Google Chrome" in observer.BROWSERS


class TestScreenObserver:
    """Tests for Screen observer with mocked dependencies."""

    @pytest.fixture
    def mock_all_deps(self):
        """Mock all dependencies for Screen observer."""
        with patch("gum.observers.screen.get_window_manager") as mock_wm, patch(
            "gum.observers.screen.get_region_selector"
        ) as mock_selector, patch("gum.observers.screen.InputListener") as mock_input, patch(
            "gum.observers.screen.mss"
        ):

            wm = MagicMock()
            wm.get_window_by_name.return_value = (
                12345,
                {"left": 0, "top": 0, "width": 800, "height": 600},
            )
            wm.get_window_bounds_by_id.return_value = {
                "left": 0,
                "top": 0,
                "width": 800,
                "height": 600,
            }
            wm.get_visible_windows.return_value = []
            mock_wm.return_value = wm

            selector = MagicMock()
            selector.select_regions.return_value = (
                [{"left": 0, "top": 0, "width": 800, "height": 600}],
                [12345],
            )
            mock_selector.return_value = selector

            input_listener = MagicMock()
            input_listener.get_mouse_position.return_value = (400, 300)
            mock_input.return_value = input_listener

            yield {"wm": wm, "selector": selector, "input": input_listener}

    def test_screen_observer_with_track_window(self, mock_all_deps):
        """Screen observer should track window by name."""
        from gum.observers.screen import Screen

        observer = Screen(track_window="TestApp")

        assert observer is not None
        assert len(observer._tracked_windows) == 1
        mock_all_deps["wm"].get_window_by_name.assert_called_once_with("TestApp")

    def test_screen_observer_with_coordinates(self, mock_all_deps):
        """Screen observer should accept target coordinates."""
        from gum.observers.screen import Screen

        observer = Screen(target_coordinates=(100, 100, 400, 300))

        assert observer is not None
        assert len(observer._tracked_windows) == 1
        region = observer._tracked_windows[0]["region"]
        assert region["left"] == 100
        assert region["top"] == 100
        assert region["width"] == 400
        assert region["height"] == 300
