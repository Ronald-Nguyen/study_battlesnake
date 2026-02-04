"""
Pytest configuration and fixtures for gum tests.
"""

import sys
import pytest
from unittest.mock import MagicMock


# Platform detection helpers
def is_macos():
    return sys.platform == "darwin"


def is_windows():
    return sys.platform == "win32"


def is_linux():
    return sys.platform.startswith("linux")


# Platform skip markers
skip_unless_macos = pytest.mark.skipif(not is_macos(), reason="Requires macOS")
skip_unless_windows = pytest.mark.skipif(not is_windows(), reason="Requires Windows")
skip_unless_linux = pytest.mark.skipif(not is_linux(), reason="Requires Linux")


# Fixtures for mocked platform adapters
@pytest.fixture
def mock_window_manager():
    """Create a mock WindowManager that satisfies the interface contract."""
    mock = MagicMock()
    mock.capabilities = {
        "supports_overlay": True,
        "supports_tab_title": False,
        "supports_clipboard": True,
        "coordinate_space": "logical",
    }
    mock.get_display_bounds.return_value = (0.0, 0.0, 1920.0, 1080.0)
    mock.get_visible_windows.return_value = [
        {
            "id": 12345,
            "stable_id": "12345",
            "title": "Test Window",
            "bounds": {"left": 0, "top": 0, "width": 800, "height": 600},
            "scale": 1.0,
            "metadata": {},
        }
    ]
    mock.get_window_by_name.return_value = (
        12345,
        {"left": 0, "top": 0, "width": 800, "height": 600},
    )
    mock.get_window_bounds_by_id.return_value = {"left": 0, "top": 0, "width": 800, "height": 600}
    mock.list_available_windows.return_value = ["Test Window", "Another Window"]
    return mock


@pytest.fixture
def mock_clipboard():
    """Create a mock Clipboard that satisfies the interface contract."""
    mock = MagicMock()
    mock.get_text.return_value = "Test clipboard content"
    return mock


@pytest.fixture
def mock_active_app_detector():
    """Create a mock ActiveAppDetector that satisfies the interface contract."""
    mock = MagicMock()
    mock.get_active_app_name.return_value = "TestApp"
    mock.get_active_window_title.return_value = "Test Window Title"
    mock.get_browser_tab_title.return_value = "Test Tab - Browser"
    mock.get_browser_tab_url.return_value = "https://example.com"
    return mock


@pytest.fixture
def mock_region_selector():
    """Create a mock RegionSelector that satisfies the interface contract."""
    mock = MagicMock()
    mock.select_regions.return_value = (
        [{"left": 100, "top": 100, "width": 400, "height": 300}],
        [None],
    )
    return mock


# Capability-aware test helpers
@pytest.fixture
def platform_capabilities():
    """Return capabilities for the current platform's window manager."""
    try:
        from gum.platform import get_window_manager

        wm = get_window_manager()
        return wm.capabilities
    except Exception:
        return {}


def requires_capability(capability_name):
    """Decorator to skip tests when a capability is not supported."""

    def decorator(func):
        @pytest.mark.usefixtures("platform_capabilities")
        def wrapper(platform_capabilities, *args, **kwargs):
            if not platform_capabilities.get(capability_name, False):
                pytest.skip(f"Platform does not support: {capability_name}")
            return func(*args, **kwargs)

        return wrapper

    return decorator
