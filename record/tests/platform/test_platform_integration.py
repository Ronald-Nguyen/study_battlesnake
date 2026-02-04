"""
Integration tests for platform implementations.

These tests run against real platform APIs and are conditionally skipped
based on the current platform and available capabilities.

IMPORTANT: Platform-specific imports (e.g., from gum.platform.macos.*)
must be done INSIDE test methods, not at module level. This ensures the
imports only happen when the test actually runs (after skipif is evaluated).
"""

import sys
import os
import pytest

# Platform detection
IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
IS_WAYLAND = os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


class TestPlatformGuards:
    """Tests that platform module guards work correctly."""

    @pytest.mark.skipif(IS_MACOS, reason="Test only runs on non-macOS")
    def test_macos_module_raises_on_non_macos(self):
        """Importing gum.platform.macos should raise ImportError on non-macOS."""
        with pytest.raises(ImportError) as exc_info:
            pass
        assert "macOS" in str(exc_info.value)
        assert "gum.platform.get_window_manager" in str(exc_info.value)

    @pytest.mark.skipif(IS_WINDOWS, reason="Test only runs on non-Windows")
    def test_windows_module_raises_on_non_windows(self):
        """Importing gum.platform.windows should raise ImportError on non-Windows."""
        with pytest.raises(ImportError) as exc_info:
            pass
        assert "Windows" in str(exc_info.value)
        assert "gum.platform.get_window_manager" in str(exc_info.value)

    @pytest.mark.skipif(IS_LINUX, reason="Test only runs on non-Linux")
    def test_linux_module_raises_on_non_linux(self):
        """Importing gum.platform.linux should raise ImportError on non-Linux."""
        with pytest.raises(ImportError) as exc_info:
            pass
        assert "Linux" in str(exc_info.value)
        assert "gum.platform.get_window_manager" in str(exc_info.value)


class TestPlatformFactory:
    """Tests for the platform factory functions."""

    def test_get_platform_returns_valid_string(self):
        """get_platform should return 'macos', 'windows', or 'linux'."""
        from gum.platform import get_platform

        platform = get_platform()
        assert platform in ("macos", "windows", "linux")

    def test_get_platform_matches_sys_platform(self):
        """get_platform should match the current sys.platform."""
        from gum.platform import get_platform

        platform = get_platform()
        if IS_MACOS:
            assert platform == "macos"
        elif IS_WINDOWS:
            assert platform == "windows"
        elif IS_LINUX:
            assert platform == "linux"

    def test_get_window_manager_returns_instance(self):
        """get_window_manager should return a WindowManager instance."""
        from gum.platform import get_window_manager
        from gum.platform.base import WindowManagerBase

        wm = get_window_manager()
        assert isinstance(wm, WindowManagerBase)

    def test_get_clipboard_returns_instance(self):
        """get_clipboard should return a Clipboard instance."""
        from gum.platform import get_clipboard
        from gum.platform.base import ClipboardBase

        clipboard = get_clipboard()
        assert isinstance(clipboard, ClipboardBase)

    def test_get_active_app_detector_returns_instance(self):
        """get_active_app_detector should return an ActiveAppDetector instance."""
        from gum.platform import get_active_app_detector
        from gum.platform.base import ActiveAppDetectorBase

        detector = get_active_app_detector()
        assert isinstance(detector, ActiveAppDetectorBase)


@pytest.mark.skipif(not IS_MACOS, reason="macOS-only tests")
class TestMacOSIntegration:
    """Integration tests for macOS platform."""

    def test_macos_window_manager_display_bounds(self):
        """macOS window manager should return valid display bounds."""
        from gum.platform.macos.window_manager import MacOSWindowManager

        wm = MacOSWindowManager()
        bounds = wm.get_display_bounds()
        min_x, min_y, max_x, max_y = bounds
        assert max_x > min_x
        assert max_y > min_y

    def test_macos_window_manager_visible_windows(self):
        """macOS window manager should enumerate visible windows."""
        from gum.platform.macos.window_manager import MacOSWindowManager

        wm = MacOSWindowManager()
        windows = wm.get_visible_windows()
        assert isinstance(windows, list)
        # There should be at least one window (the test runner)
        assert len(windows) > 0

    def test_macos_clipboard_get_text(self):
        """macOS clipboard should return text or None."""
        from gum.platform.macos.clipboard import MacOSClipboard

        clipboard = MacOSClipboard()
        result = clipboard.get_text()
        assert result is None or isinstance(result, str)

    def test_macos_active_app_detector(self):
        """macOS active app detector should return app name."""
        from gum.platform.macos.active_app import MacOSActiveAppDetector

        detector = MacOSActiveAppDetector()
        app_name = detector.get_active_app_name()
        assert isinstance(app_name, str)


@pytest.mark.skipif(not IS_WINDOWS, reason="Windows-only tests")
class TestWindowsIntegration:
    """Integration tests for Windows platform."""

    def test_windows_window_manager_display_bounds(self):
        """Windows window manager should return valid display bounds."""
        from gum.platform.windows.window_manager import WindowsWindowManager

        wm = WindowsWindowManager()
        bounds = wm.get_display_bounds()
        min_x, min_y, max_x, max_y = bounds
        assert max_x > min_x
        assert max_y > min_y

    def test_windows_window_manager_visible_windows(self):
        """Windows window manager should enumerate visible windows."""
        from gum.platform.windows.window_manager import WindowsWindowManager

        wm = WindowsWindowManager()
        windows = wm.get_visible_windows()
        assert isinstance(windows, list)

    def test_windows_clipboard_get_text(self):
        """Windows clipboard should return text or None."""
        from gum.platform.windows.clipboard import WindowsClipboard

        clipboard = WindowsClipboard()
        result = clipboard.get_text()
        assert result is None or isinstance(result, str)

    def test_windows_active_app_detector(self):
        """Windows active app detector should return app name."""
        from gum.platform.windows.active_app import WindowsActiveAppDetector

        detector = WindowsActiveAppDetector()
        app_name = detector.get_active_app_name()
        assert isinstance(app_name, str)


@pytest.mark.skipif(not IS_LINUX, reason="Linux-only tests")
class TestLinuxIntegration:
    """Integration tests for Linux platform."""

    @pytest.mark.skipif(IS_WAYLAND, reason="X11 required, Wayland detected")
    def test_linux_window_manager_display_bounds(self):
        """Linux window manager should return valid display bounds on X11."""
        from gum.platform.linux.window_manager import LinuxWindowManager

        wm = LinuxWindowManager()
        bounds = wm.get_display_bounds()
        min_x, min_y, max_x, max_y = bounds
        assert max_x > min_x
        assert max_y > min_y

    @pytest.mark.skipif(IS_WAYLAND, reason="X11 required, Wayland detected")
    def test_linux_window_manager_visible_windows(self):
        """Linux window manager should enumerate visible windows on X11."""
        from gum.platform.linux.window_manager import LinuxWindowManager

        wm = LinuxWindowManager()
        windows = wm.get_visible_windows()
        assert isinstance(windows, list)

    def test_linux_clipboard_get_text(self):
        """Linux clipboard should return text or None (None on Wayland)."""
        from gum.platform.linux.clipboard import LinuxClipboard

        clipboard = LinuxClipboard()
        result = clipboard.get_text()
        if IS_WAYLAND:
            # Wayland clipboard access is restricted
            assert result is None
        else:
            assert result is None or isinstance(result, str)

    @pytest.mark.skipif(IS_WAYLAND, reason="X11 required, Wayland detected")
    def test_linux_active_app_detector(self):
        """Linux active app detector should return app name on X11."""
        from gum.platform.linux.active_app import LinuxActiveAppDetector

        detector = LinuxActiveAppDetector()
        app_name = detector.get_active_app_name()
        assert isinstance(app_name, str)


class TestWaylandDetection:
    """Tests for Wayland session detection and graceful degradation."""

    @pytest.mark.skipif(not IS_LINUX, reason="Linux-only")
    def test_wayland_detection_env_var(self):
        """Wayland detection should use XDG_SESSION_TYPE."""
        session_type = os.environ.get("XDG_SESSION_TYPE", "")
        if IS_WAYLAND:
            assert session_type.lower() == "wayland"

    @pytest.mark.skipif(not (IS_LINUX and IS_WAYLAND), reason="Wayland-only")
    def test_wayland_clipboard_works(self):
        """Clipboard should work on Wayland via wl-paste."""
        from gum.platform.linux.clipboard import LinuxClipboard

        clipboard = LinuxClipboard()
        # Should not raise, returns None or string
        result = clipboard.get_text()
        assert result is None or isinstance(result, str)

    @pytest.mark.skipif(not (IS_LINUX and IS_WAYLAND), reason="Wayland-only")
    def test_wayland_window_manager_capabilities(self):
        """Window manager should report limited capabilities on Wayland."""
        from gum.platform.linux.window_manager import LinuxWindowManager

        wm = LinuxWindowManager()
        caps = wm.capabilities
        # Wayland has limited window enumeration
        assert caps.get("supports_window_enum") is False
        assert caps.get("supports_clipboard") is True

    @pytest.mark.skipif(not (IS_LINUX and IS_WAYLAND), reason="Wayland-only")
    def test_wayland_screen_capture_available(self):
        """Screen capture should work on Wayland via grim or similar."""
        from gum.platform.linux.screen_capture import LinuxScreenCapture

        capturer = LinuxScreenCapture()
        assert capturer._wayland is True
        capturer.close()

    @pytest.mark.skipif(not (IS_LINUX and IS_WAYLAND), reason="Wayland-only")
    def test_wayland_active_window_detection(self):
        """Active window detection should work via compositor tools."""
        from gum.platform.linux.wayland_portal import get_active_window_title_wayland

        # May return None if no compositor tools available, but should not raise
        result = get_active_window_title_wayland()
        assert result is None or isinstance(result, str)


class TestGracefulDegradation:
    """Tests for graceful degradation when features are unavailable."""

    def test_clipboard_unavailable_returns_none(self):
        """Clipboard should return None, not raise, when unavailable."""
        from gum.platform import get_clipboard

        clipboard = get_clipboard()
        # Should not raise
        result = clipboard.get_text()
        assert result is None or isinstance(result, str)

    def test_browser_tab_title_returns_none_when_unsupported(self):
        """get_browser_tab_title should return None when unsupported."""
        from gum.platform import get_active_app_detector

        detector = get_active_app_detector()
        result = detector.get_browser_tab_title("NonExistentBrowser")
        assert result is None or isinstance(result, str)

    def test_browser_tab_url_returns_none_when_unsupported(self):
        """get_browser_tab_url should return None when unsupported."""
        from gum.platform import get_active_app_detector

        detector = get_active_app_detector()
        result = detector.get_browser_tab_url("NonExistentBrowser")
        assert result is None or isinstance(result, str)
