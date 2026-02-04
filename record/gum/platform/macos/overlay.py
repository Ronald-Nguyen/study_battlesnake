import objc
import AppKit
import Quartz
from Foundation import NSDate, NSRunLoop
from typing import List, Optional, Tuple, Dict, Any
from ..base import RegionSelectorBase

_selected_regions = []  # List of selected regions
_selected_window_ids = []  # List of selected window IDs


class OverlayWindow(AppKit.NSWindow):
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return True

    def becomeKeyWindow(self):
        result = objc.super(OverlayWindow, self).becomeKeyWindow()
        try:
            content = self.contentView()
            if content is not None:
                self.makeFirstResponder_(content)
        except Exception:
            pass
        return result


class SelectionView(AppKit.NSView):
    def init(self):
        self = objc.super(SelectionView, self).initWithFrame_(AppKit.NSMakeRect(0, 0, 10000, 10000))
        if self is None:
            return None
        self.start = None
        self.end = None
        self.highlighted_window = None
        self.selected_windows = []  # Currently selected windows (for visual feedback)
        return self

    def viewDidMoveToWindow(self):
        objc.super(SelectionView, self).viewDidMoveToWindow()
        try:
            win = self.window()
            if win is not None:
                win.makeFirstResponder_(self)
        except Exception:
            pass

    def acceptsFirstResponder(self):
        return True

    def becomeFirstResponder(self):
        result = objc.super(SelectionView, self).becomeFirstResponder()
        return result

    def acceptsFirstMouse_(self, event):
        return True  # first click acts immediately

    def keyDown_(self, event):
        global _selected_regions, _selected_window_ids
        keyCode = event.keyCode()

        # ESC = cancel
        if keyCode == 53:  # kVK_Escape
            _selected_regions = []
            _selected_window_ids = []
            self.window().orderOut_(None)
            AppKit.NSApp().stopModalWithCode_(AppKit.NSModalResponseCancel)
            return

        # Enter/Return = confirm selection
        elif keyCode == 36 or keyCode == 76:  # kVK_Return or kVK_KeypadEnter
            if self.selected_windows:
                # Use the selected windows
                _selected_regions = [w.copy() for w in self.selected_windows]
                _selected_window_ids = [w.get("window_id") for w in self.selected_windows]
                # Remove window_id from regions as it's stored separately
                for region in _selected_regions:
                    region.pop("window_id", None)
                self.window().orderOut_(None)
                AppKit.NSApp().stopModalWithCode_(AppKit.NSModalResponseOK)
            else:
                pass  # No windows selected
            return

        objc.super(SelectionView, self).keyDown_(event)

    def mouseMoved_(self, event):
        location = event.locationInWindow()
        window_info = self._get_window_at_location(location)
        if window_info != self.highlighted_window:
            self.highlighted_window = window_info
            self.setNeedsDisplay_(True)

    def mouseDown_(self, event):
        """Click adds/removes windows or confirms selection via button"""
        global _selected_regions, _selected_window_ids

        location = event.locationInWindow()

        # Check if clicking the DONE button (centered in banner)
        banner_height = 60
        screen_height = self.bounds().size.height
        button_width = 120
        button_height = 40
        button_x = (self.bounds().size.width - button_width) / 2
        button_y = screen_height - banner_height + 10

        if (
            button_x <= location.x <= button_x + button_width
            and button_y <= location.y <= button_y + button_height
        ):
            # Clicked DONE button
            if self.selected_windows:
                _selected_regions = [w.copy() for w in self.selected_windows]
                _selected_window_ids = [w.get("window_id") for w in self.selected_windows]
                for region in _selected_regions:
                    region.pop("window_id", None)
                self.window().orderOut_(None)
                AppKit.NSApp().stopModalWithCode_(AppKit.NSModalResponseOK)
                return

        window_info = self._get_window_at_location(location)

        # Double-click on empty area to confirm selection (backup method)
        if event.clickCount() == 2 and window_info is None and not self.start:
            if self.selected_windows:
                _selected_regions = [w.copy() for w in self.selected_windows]
                _selected_window_ids = [w.get("window_id") for w in self.selected_windows]
                for region in _selected_regions:
                    region.pop("window_id", None)
                self.window().orderOut_(None)
                AppKit.NSApp().stopModalWithCode_(AppKit.NSModalResponseOK)
                return

        if window_info:
            window_id = window_info.get("window_id")
            # Check if already selected - if so, DESELECT it
            already_selected = False
            for i, w in enumerate(self.selected_windows):
                if w.get("window_id") == window_id:
                    self.selected_windows.pop(i)
                    already_selected = True
                    break

            if not already_selected and window_id:
                # Add window to selection
                self.selected_windows.append(window_info.copy())

            self.highlighted_window = None
            self.setNeedsDisplay_(True)
        else:
            # Start manual region drawing
            self.start = location
            self.end = self.start
            self.setNeedsDisplay_(True)

    def mouseDragged_(self, event):
        if self.start:
            self.end = event.locationInWindow()
            self.highlighted_window = None
            self.setNeedsDisplay_(True)

    def mouseUp_(self, event):
        if not self.start:
            return
        self.end = event.locationInWindow()
        self.setNeedsDisplay_(True)

        x0, y0 = self.start.x, self.start.y
        x1, y1 = self.end.x, self.end.y
        left, top = min(x0, x1), min(y0, y1)
        width, height = abs(x1 - x0), abs(y1 - y0)

        screen = AppKit.NSScreen.mainScreen().frame()
        top = screen.size.height - top - height  # Flip Y

        # Add manual region to selection (no window_id for manual regions)
        manual_region = {
            "left": int(left),
            "top": int(top),
            "width": int(width),
            "height": int(height),
        }
        self.selected_windows.append(manual_region)

        # Reset drag state
        self.start = None
        self.end = None
        self.setNeedsDisplay_(True)

    def _get_window_at_location(self, location):
        window_frame = self.window().frame()
        screen_point = AppKit.NSMakePoint(
            window_frame.origin.x + location.x, window_frame.origin.y + location.y
        )

        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        if not window_list:
            return None

        # Compute Quartz Y-flip
        max_y = 0
        for scr in AppKit.NSScreen.screens():
            f = scr.frame()
            max_y = max(max_y, f.origin.y + f.size.height)
        quartz_y = max_y - screen_point.y

        for win in window_list:
            bounds = win.get("kCGWindowBounds", {})
            if not bounds:
                continue
            x, y, w, h = (
                bounds.get("X", 0),
                bounds.get("Y", 0),
                bounds.get("Width", 0),
                bounds.get("Height", 0),
            )
            layer = win.get("kCGWindowLayer", 0)
            if layer >= AppKit.NSFloatingWindowLevel or w < 50 or h < 50:
                continue
            if x <= screen_point.x <= x + w and y <= quartz_y <= y + h:
                window_id = win.get("kCGWindowNumber")

                # Chrome (and some apps) draw tab bars as a separate child window.
                # Merge overlapping windows with the same PID to avoid split selections.
                pid = win.get("kCGWindowOwnerPID")
                main_window = win
                max_area = w * h
                union_left, union_top = x, y
                union_right, union_bottom = x + w, y + h

                if pid:
                    for other in window_list:
                        if other is win or other.get("kCGWindowOwnerPID") != pid:
                            continue
                        ob = other.get("kCGWindowBounds", {})
                        ox, oy = ob.get("X", 0), ob.get("Y", 0)
                        ow, oh = ob.get("Width", 0), ob.get("Height", 0)
                        if ow < 20 or oh < 20:
                            continue
                        # Only merge if the windows overlap at all
                        if not (ox + ow < x or x + w < ox or oy + oh < y or y + h < oy):
                            union_left = min(union_left, ox)
                            union_top = min(union_top, oy)
                            union_right = max(union_right, ox + ow)
                            union_bottom = max(union_bottom, oy + oh)
                            area = ow * oh
                            if area > max_area:
                                max_area = area
                                main_window = other

                merged_w = int(union_right - union_left)
                merged_h = int(union_bottom - union_top)
                # Use the largest window in the PID group as the canonical window_id
                window_id = main_window.get("kCGWindowNumber")
                return {
                    "left": int(union_left),
                    "top": int(union_top),
                    "width": merged_w,
                    "height": merged_h,
                    "window_id": window_id,
                }
        return None

    def drawRect_(self, _):
        # Draw instruction banner at top
        banner_height = 60
        banner_rect = AppKit.NSMakeRect(
            0, self.bounds().size.height - banner_height, self.bounds().size.width, banner_height
        )
        AppKit.NSColor.colorWithCalibratedWhite_alpha_(0, 0.8).set()
        AppKit.NSBezierPath.fillRect_(banner_rect)

        # Draw DONE button (centered)
        button_width = 120
        button_height = 40
        button_x = (self.bounds().size.width - button_width) / 2
        button_y = self.bounds().size.height - banner_height + 10

        button_rect = AppKit.NSMakeRect(button_x, button_y, button_width, button_height)
        button_path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            button_rect, 8, 8
        )

        if self.selected_windows:
            # Enabled - green
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.8, 0.3, 0.9).setFill()
        else:
            # Disabled - gray
            AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.5, 0.5).setFill()

        button_path.fill()
        AppKit.NSColor.whiteColor().setStroke()
        button_path.setLineWidth_(2)
        button_path.stroke()

        # Draw DONE text
        done_text = AppKit.NSString.stringWithString_("DONE")
        done_attrs = {
            AppKit.NSFontAttributeName: AppKit.NSFont.boldSystemFontOfSize_(18),
            AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor(),
        }
        done_size = done_text.sizeWithAttributes_(done_attrs)
        done_x = button_x + (button_width - done_size.width) / 2
        done_y = button_y + (button_height - done_size.height) / 2
        done_text.drawAtPoint_withAttributes_(AppKit.NSMakePoint(done_x, done_y), done_attrs)

        # Draw instruction text
        text_str = "Click windows to toggle selection  *  Click again to deselect"
        text = AppKit.NSString.stringWithString_(text_str)
        attrs = {
            AppKit.NSFontAttributeName: AppKit.NSFont.systemFontOfSize_(14),
            AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor(),
        }
        text_size = text.sizeWithAttributes_(attrs)
        text_x = 20  # Left-aligned
        text_y = self.bounds().size.height - banner_height + (banner_height - text_size.height) / 2
        text.drawAtPoint_withAttributes_(AppKit.NSMakePoint(text_x, text_y), attrs)

        # Calculate max_y once for coordinate conversions
        max_y = 0
        for scr in AppKit.NSScreen.screens():
            f = scr.frame()
            max_y = max(max_y, f.origin.y + f.size.height)
        window_frame = self.window().frame()

        # Draw selected windows in green
        for idx, win in enumerate(self.selected_windows, 1):
            view_x = win["left"] - window_frame.origin.x
            view_y = (max_y - win["top"] - win["height"]) - window_frame.origin.y
            rect = AppKit.NSMakeRect(view_x, view_y, win["width"], win["height"])

            path = AppKit.NSBezierPath.bezierPathWithRect_(rect)
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.8, 0.3, 0.3).setFill()
            path.fill()
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.8, 0.3, 0.9).setStroke()
            path.setLineWidth_(4.0)
            path.stroke()

            # Draw number badge (positioned lower to avoid top cutoff)
            badge_text_str = str(idx)
            badge_text = AppKit.NSString.stringWithString_(badge_text_str)
            badge_attrs = {
                AppKit.NSFontAttributeName: AppKit.NSFont.boldSystemFontOfSize_(24),
                AppKit.NSForegroundColorAttributeName: AppKit.NSColor.whiteColor(),
            }
            badge_size = badge_text.sizeWithAttributes_(badge_attrs)
            badge_x = view_x + 10
            badge_y = view_y + win["height"] - badge_size.height - 50

            # Draw badge background circle
            badge_radius = 20
            badge_circle = AppKit.NSBezierPath.bezierPathWithOvalInRect_(
                AppKit.NSMakeRect(badge_x - 5, badge_y - 5, badge_radius * 2, badge_radius * 2)
            )
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.8, 0.3, 0.9).setFill()
            badge_circle.fill()

            badge_text.drawAtPoint_withAttributes_(
                AppKit.NSMakePoint(badge_x + 5, badge_y), badge_attrs
            )

        # Draw highlighted window in blue (only if not dragging)
        if self.highlighted_window and not self.start:
            win = self.highlighted_window
            view_x = win["left"] - window_frame.origin.x
            view_y = (max_y - win["top"] - win["height"]) - window_frame.origin.y
            rect = AppKit.NSMakeRect(view_x, view_y, win["width"], win["height"])

            path = AppKit.NSBezierPath.bezierPathWithRect_(rect)
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.3, 0.6, 1.0, 0.25).setFill()
            path.fill()
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.3, 0.6, 1.0, 0.9).setStroke()
            path.setLineWidth_(3.0)
            path.stroke()

        # Draw manual region being dragged in red
        elif self.start and self.end:
            rect = AppKit.NSMakeRect(
                min(self.start.x, self.end.x),
                min(self.start.y, self.end.y),
                abs(self.end.x - self.start.x),
                abs(self.end.y - self.start.y),
            )
            path = AppKit.NSBezierPath.bezierPathWithRect_(rect)
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 0, 0, 0.3).setFill()
            path.fill()
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(1, 0, 0, 0.9).setStroke()
            path.setLineWidth_(2.0)
            path.stroke()


class MacOSRegionSelector(RegionSelectorBase):

    def select_regions(self) -> Tuple[List[Dict[str, Any]], List[Optional[int]]]:
        """
        Show overlay for user to select windows/regions.
        Returns (list of region dicts, list of window IDs).
        """
        global _selected_regions, _selected_window_ids
        _selected_regions = []
        _selected_window_ids = []

        app = AppKit.NSApplication.sharedApplication()
        # Use the union of all screens' visible frames so overlay isn't clipped on multi-monitor setups
        screens = AppKit.NSScreen.screens()
        if screens:
            min_x = min(scr.visibleFrame().origin.x for scr in screens)
            min_y = min(scr.visibleFrame().origin.y for scr in screens)
            max_x = max(
                scr.visibleFrame().origin.x + scr.visibleFrame().size.width for scr in screens
            )
            max_y = max(
                scr.visibleFrame().origin.y + scr.visibleFrame().size.height for scr in screens
            )
            content_rect = AppKit.NSMakeRect(min_x, min_y, max_x - min_x, max_y - min_y)
        else:
            screen = AppKit.NSScreen.mainScreen()
            visible = screen.visibleFrame()
            content_rect = AppKit.NSMakeRect(
                visible.origin.x, visible.origin.y, visible.size.width, visible.size.height
            )

        window = OverlayWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            content_rect,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        window.setOpaque_(False)
        window.setHasShadow_(False)
        window.setReleasedWhenClosed_(True)
        window.setBackgroundColor_(AppKit.NSColor.clearColor())
        window.setLevel_(AppKit.NSFloatingWindowLevel)
        window.setIgnoresMouseEvents_(False)
        window.setAcceptsMouseMovedEvents_(True)
        window.setHidesOnDeactivate_(False)
        try:
            window.setCollectionBehavior_(AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces)
        except Exception:
            pass

        view = SelectionView.alloc().init()
        view.setFrame_(window.contentView().bounds())
        view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)
        window.setContentView_(view)

        # Make window key and active
        window.makeKeyAndOrderFront_(None)
        window.orderFrontRegardless()
        app.activateIgnoringOtherApps_(True)

        # Give the window system time to process
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))

        # Force the window to become key
        window.makeKeyWindow()

        # Set up first responder
        window.makeFirstResponder_(view)
        window.setInitialFirstResponder_(view)

        AppKit.NSCursor.crosshairCursor().push()
        response = None
        try:
            response = app.runModalForWindow_(window)  # blocks until stopModalWithCode_ called
        finally:
            # Always restore cursor
            try:
                AppKit.NSCursor.pop()
            except Exception:
                AppKit.NSCursor.arrowCursor().set()

            # Now that the modal loop is over, tear the window down
            window.orderOut_(None)
            window.close()
            app.updateWindows()

            # Give AppKit a tick to process the close
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.05))

        # Check if user cancelled
        if response != AppKit.NSModalResponseOK:
            raise RuntimeError("Selection cancelled")

        return _selected_regions, _selected_window_ids
