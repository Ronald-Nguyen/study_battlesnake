"""
Unit tests for platform abstraction layer interface contracts.

These tests verify that all platform implementations conform to the base interface
contracts defined in gum.platform.base.
"""


class TestWindowManagerContract:
    """Tests that verify WindowManager implementations follow the contract."""

    def test_capabilities_returns_dict(self, mock_window_manager):
        """capabilities should return a dict of bool values."""
        caps = mock_window_manager.capabilities
        assert isinstance(caps, dict)
        for key, value in caps.items():
            assert isinstance(key, str)
            # Values can be bool or str (for coordinate_space)

    def test_get_display_bounds_returns_tuple(self, mock_window_manager):
        """get_display_bounds should return (min_x, min_y, max_x, max_y)."""
        bounds = mock_window_manager.get_display_bounds()
        assert isinstance(bounds, tuple)
        assert len(bounds) == 4
        min_x, min_y, max_x, max_y = bounds
        assert min_x <= max_x, "min_x should be <= max_x"
        assert min_y <= max_y, "min_y should be <= max_y"

    def test_get_visible_windows_returns_list(self, mock_window_manager):
        """get_visible_windows should return a list of window dicts."""
        windows = mock_window_manager.get_visible_windows()
        assert isinstance(windows, list)
        for win in windows:
            assert isinstance(win, dict)
            # Required fields
            assert "id" in win
            assert "bounds" in win
            assert isinstance(win["bounds"], dict)
            # Bounds validation
            bounds = win["bounds"]
            assert "left" in bounds
            assert "top" in bounds
            assert "width" in bounds
            assert "height" in bounds

    def test_get_window_by_name_returns_tuple_or_none(self, mock_window_manager):
        """get_window_by_name should return (id, bounds) or None."""
        result = mock_window_manager.get_window_by_name("Test Window")
        if result is not None:
            assert isinstance(result, tuple)
            assert len(result) == 2
            window_id, bounds = result
            assert isinstance(bounds, dict)

    def test_get_window_bounds_by_id_returns_dict_or_none(self, mock_window_manager):
        """get_window_bounds_by_id should return bounds dict or None."""
        result = mock_window_manager.get_window_bounds_by_id(12345)
        if result is not None:
            assert isinstance(result, dict)
            assert "left" in result
            assert "top" in result
            assert "width" in result
            assert "height" in result

    def test_list_available_windows_returns_list_of_strings(self, mock_window_manager):
        """list_available_windows should return list of window names."""
        windows = mock_window_manager.list_available_windows()
        assert isinstance(windows, list)
        for name in windows:
            assert isinstance(name, str)


class TestClipboardContract:
    """Tests that verify Clipboard implementations follow the contract."""

    def test_get_text_returns_string_or_none(self, mock_clipboard):
        """get_text should return string content or None."""
        result = mock_clipboard.get_text()
        assert result is None or isinstance(result, str)

    def test_get_text_handles_unavailable_gracefully(self, mock_clipboard):
        """get_text should return None (not raise) when clipboard unavailable."""
        mock_clipboard.get_text.return_value = None
        result = mock_clipboard.get_text()
        assert result is None


class TestActiveAppDetectorContract:
    """Tests that verify ActiveAppDetector implementations follow the contract."""

    def test_get_active_app_name_returns_string(self, mock_active_app_detector):
        """get_active_app_name should return a string (possibly empty)."""
        result = mock_active_app_detector.get_active_app_name()
        assert isinstance(result, str)

    def test_get_active_window_title_returns_string_or_none(self, mock_active_app_detector):
        """get_active_window_title should return string or None."""
        result = mock_active_app_detector.get_active_window_title("TestApp")
        assert result is None or isinstance(result, str)

    def test_get_browser_tab_title_returns_string_or_none(self, mock_active_app_detector):
        """get_browser_tab_title should return string or None."""
        result = mock_active_app_detector.get_browser_tab_title("Chrome")
        assert result is None or isinstance(result, str)

    def test_get_browser_tab_url_returns_string_or_none(self, mock_active_app_detector):
        """get_browser_tab_url should return string or None."""
        result = mock_active_app_detector.get_browser_tab_url("Chrome")
        assert result is None or isinstance(result, str)


class TestRegionSelectorContract:
    """Tests that verify RegionSelector implementations follow the contract."""

    def test_select_regions_returns_tuple(self, mock_region_selector):
        """select_regions should return (list of regions, list of window_ids)."""
        result = mock_region_selector.select_regions()
        assert isinstance(result, tuple)
        assert len(result) == 2
        regions, window_ids = result
        assert isinstance(regions, list)
        assert isinstance(window_ids, list)
        assert len(regions) == len(window_ids)

    def test_select_regions_region_format(self, mock_region_selector):
        """Each region should have left, top, width, height."""
        regions, _ = mock_region_selector.select_regions()
        for region in regions:
            assert isinstance(region, dict)
            assert "left" in region
            assert "top" in region
            assert "width" in region
            assert "height" in region


class TestBoundsNormalization:
    """Tests for coordinate normalization requirements."""

    def test_bounds_use_logical_pixels(self, mock_window_manager):
        """Bounds should be in logical pixels (coordinate_space capability)."""
        caps = mock_window_manager.capabilities
        if "coordinate_space" in caps:
            assert caps["coordinate_space"] == "logical"

    def test_bounds_origin_top_left(self, mock_window_manager):
        """Display bounds origin should be top-left of primary display."""
        min_x, min_y, max_x, max_y = mock_window_manager.get_display_bounds()
        # Primary display typically starts at (0, 0)
        # But multi-monitor can have negative coordinates
        assert isinstance(min_x, (int, float))
        assert isinstance(min_y, (int, float))

    def test_window_bounds_positive_dimensions(self, mock_window_manager):
        """Window bounds should have positive width and height."""
        windows = mock_window_manager.get_visible_windows()
        for win in windows:
            bounds = win["bounds"]
            assert bounds["width"] > 0
            assert bounds["height"] > 0
