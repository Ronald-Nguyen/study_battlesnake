"""
Windows region selection overlay.
Provides both window picker and custom region drawing modes.
"""

import tkinter as tk
from typing import List, Dict, Optional, Any, Tuple
from ..base import RegionSelectorBase

try:
    import win32gui
    import win32process

    WIN_AVAILABLE = True
except ImportError:
    WIN_AVAILABLE = False
    # Try alternative: use PowerShell to get windows
    import subprocess


class WindowsRegionSelector(RegionSelectorBase):

    def _get_visible_windows(self) -> List[Dict[str, Any]]:
        """Get list of visible windows with their bounds."""

        if not WIN_AVAILABLE:
            # Try PowerShell alternative
            return self._get_windows_via_powershell()

        windows = []
        stats = {
            "total": 0,
            "not_visible": 0,
            "no_title": 0,
            "too_small": 0,
            "error": 0,
            "added": 0,
            "visible_but_filtered": [],
        }

        def enum_callback(hwnd, results):
            stats["total"] += 1
            try:
                is_visible = win32gui.IsWindowVisible(hwnd)
                if not is_visible:
                    stats["not_visible"] += 1
                    return True

                title = win32gui.GetWindowText(hwnd)
                rect = win32gui.GetWindowRect(hwnd)
                width = rect[2] - rect[0]
                height = rect[3] - rect[1]

                # More lenient filtering - show windows even without titles, and smaller minimum size
                if not title or len(title.strip()) == 0:
                    # Use a default title for windows without titles
                    title = f"Window {hwnd}"
                    stats["no_title"] += 1

                # More lenient size requirement (50x50 instead of 100x100)
                if width < 50 or height < 50:
                    stats["too_small"] += 1
                    return True

                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                window_info = {
                    "hwnd": hwnd,
                    "title": title[:60] + ("..." if len(title) > 60 else ""),
                    "full_title": title,
                    "bounds": {
                        "left": rect[0],
                        "top": rect[1],
                        "width": width,
                        "height": height,
                    },
                    "pid": pid,
                }
                results.append(window_info)
                stats["added"] += 1

                # Log first few windows for debugging
            except Exception:
                stats["error"] += 1
                # Log first few errors
            return True

        try:
            win32gui.EnumWindows(enum_callback, windows)
        except Exception:
            raise

        # Sort by title for easier selection
        windows.sort(key=lambda w: w["title"].lower())
        return windows

    def _get_windows_via_powershell(self) -> List[Dict[str, Any]]:
        """Fallback: Get windows using PowerShell if pywin32 is not available."""

        windows = []
        try:
            # PowerShell script to get visible windows
            ps_script = """
            Add-Type @"
            using System;
            using System.Runtime.InteropServices;
            using System.Collections.Generic;
            public class WindowInfo {
                public string Title;
                public int Left;
                public int Top;
                public int Width;
                public int Height;
                public IntPtr Handle;
            }
            public class Win32 {
                [DllImport("user32.dll")]
                public static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);
                public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
                [DllImport("user32.dll")]
                public static extern bool IsWindowVisible(IntPtr hWnd);
                [DllImport("user32.dll", CharSet=CharSet.Auto)]
                public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
                [DllImport("user32.dll")]
                public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
                [StructLayout(LayoutKind.Sequential)]
                public struct RECT {
                    public int Left;
                    public int Top;
                    public int Right;
                    public int Bottom;
                }
            }
"@
            $windows = New-Object System.Collections.ArrayList
            $callback = {
                param([IntPtr]$hWnd, [IntPtr]$lParam)
                if ([Win32]::IsWindowVisible($hWnd)) {
                    $sb = New-Object System.Text.StringBuilder 256
                    [Win32]::GetWindowText($hWnd, $sb, $sb.Capacity) | Out-Null
                    $title = $sb.ToString()
                    if ($title -and $title.Length -gt 0) {
                        $rect = New-Object Win32+RECT
                        if ([Win32]::GetWindowRect($hWnd, [ref]$rect)) {
                            $width = $rect.Right - $rect.Left
                            $height = $rect.Bottom - $rect.Top
                            if ($width -ge 50 -and $height -ge 50) {
                                $win = [PSCustomObject]@{
                                    Title = $title
                                    Left = $rect.Left
                                    Top = $rect.Top
                                    Width = $width
                                    Height = $height
                                    Handle = $hWnd.ToInt64()
                                }
                                [void]$windows.Add($win)
                            }
                        }
                    }
                }
                return $true
            }
            $delegate = [Win32+EnumWindowsProc]$callback
            [Win32]::EnumWindows($delegate, [IntPtr]::Zero) | Out-Null
            $windows | ConvertTo-Json
            """

            result = subprocess.run(
                ["powershell", "-Command", ps_script], capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0 and result.stdout:
                import json

                win_data = json.loads(result.stdout)
                if not isinstance(win_data, list):
                    win_data = [win_data]

                for win in win_data:
                    windows.append(
                        {
                            "hwnd": int(win["Handle"]),
                            "title": win["Title"][:60] + ("..." if len(win["Title"]) > 60 else ""),
                            "full_title": win["Title"],
                            "bounds": {
                                "left": win["Left"],
                                "top": win["Top"],
                                "width": win["Width"],
                                "height": win["Height"],
                            },
                            "pid": 0,  # PowerShell doesn't easily get PID
                        }
                    )
        except Exception:
            pass

        windows.sort(key=lambda w: w["title"].lower())
        return windows

    def select_regions(self) -> Tuple[List[Dict[str, Any]], List[Optional[int]]]:
        regions: List[Dict[str, Any]] = []
        window_ids: List[Optional[int]] = []

        # First, show window picker dialog
        result = self._show_window_picker()

        if result == "cancelled":
            raise RuntimeError("Selection cancelled")
        elif result == "custom":
            # User chose custom region - show draw overlay
            return self._draw_custom_region()
        elif result == "fullscreen":
            # Capture entire screen
            try:
                import win32api
                import win32con

                left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
                top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
                width = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
                height = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
                fullscreen_region = {"left": left, "top": top, "width": width, "height": height}
                regions.append(fullscreen_region)
                window_ids.append(None)
            except Exception:
                # Fallback to common resolution
                fallback_region = {"left": 0, "top": 0, "width": 1920, "height": 1080}
                regions.append(fallback_region)
                window_ids.append(None)
        elif isinstance(result, list):
            # Multiple windows selected
            for win in result:
                if isinstance(win, dict) and "bounds" in win and "hwnd" in win:
                    regions.append(win["bounds"])
                    window_ids.append(win["hwnd"])
        elif isinstance(result, dict) and "bounds" in result and "hwnd" in result:
            # Single window dict
            regions.append(result["bounds"])
            window_ids.append(result["hwnd"])
        else:
            # Unexpected result type
            raise RuntimeError(f"Unexpected selection result: {result}")

        return regions, window_ids

    def _show_window_picker(self) -> Any:
        """Show dialog to pick a window or choose custom region."""
        windows = self._get_visible_windows()

        root = tk.Tk()
        root.title("GUM - Select Recording Area")
        root.geometry("600x500")
        root.attributes("-topmost", True)

        result = {"value": "cancelled"}
        selected_idx = [0] if windows else [-1]  # Track selected index

        # Title
        title_label = tk.Label(root, text="Select a window to record:", font=("Arial", 14, "bold"))
        title_label.pack(pady=10)

        # Main container
        main_frame = tk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # Left side: Window list
        left_frame = tk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        list_label = tk.Label(left_frame, text="Available Windows:", font=("Arial", 10, "bold"))
        list_label.pack(anchor=tk.W, pady=(0, 5))

        # Window list with scrollbar
        list_frame = tk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Use MULTIPLE selection mode for multi-window selection
        listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=("Arial", 10),
            height=15,
            selectmode=tk.EXTENDED,
            exportselection=False,
        )
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        # Populate window list

        if not windows:
            # Show message if no windows found
            listbox.insert(tk.END, "No windows found. Click 'Record Full Screen' instead.")
            listbox.config(state=tk.DISABLED)
        else:
            for i, win in enumerate(windows):
                # Single line format for listbox (no newlines)
                display_text = (
                    f"{win['title']} ({win['bounds']['width']}x{win['bounds']['height']})"
                )
                listbox.insert(tk.END, display_text)

        # Right side: Preview/Info
        right_frame = tk.Frame(main_frame, width=200)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(10, 0))
        right_frame.pack_propagate(False)

        preview_label = tk.Label(
            right_frame, text="Selected Window Info:", font=("Arial", 10, "bold")
        )
        preview_label.pack(anchor=tk.W, pady=(0, 5))

        # Info display
        info_text = tk.Text(
            right_frame, font=("Arial", 9), wrap=tk.WORD, height=10, state=tk.DISABLED
        )
        info_text.pack(fill=tk.BOTH, expand=True)

        def update_preview(idx):
            """Update the preview panel with selected window info."""
            if 0 <= idx < len(windows):
                win = windows[idx]
                info_text.config(state=tk.NORMAL)
                info_text.delete(1.0, tk.END)
                info_text.insert(tk.END, f"Title:\n{win['full_title']}\n\n")
                info_text.insert(
                    tk.END,
                    f"Size:\n{win['bounds']['width']} x {win['bounds']['height']} pixels\n\n",
                )
                info_text.insert(
                    tk.END, f"Position:\n({win['bounds']['left']}, {win['bounds']['top']})\n\n"
                )
                info_text.insert(tk.END, f"Window ID:\n{win['hwnd']}")
                info_text.config(state=tk.DISABLED)
                selected_idx[0] = idx

        def on_listbox_select(event):
            """Handle listbox selection change."""
            selection = listbox.curselection()
            if selection:
                idx = selection[0]
                update_preview(idx)

        def on_select_window():
            """Confirm window selection (supports multiple windows)."""
            selection = listbox.curselection()

            # Support multiple selection
            if selection and len(selection) > 0:
                # Multiple windows selected - return list
                selected_windows = [windows[idx] for idx in selection if 0 <= idx < len(windows)]
                if selected_windows:
                    result["value"] = (
                        selected_windows if len(selected_windows) > 1 else selected_windows[0]
                    )
                    root.quit()
                    return
            elif selected_idx[0] >= 0:
                # Fallback to tracked index
                idx = selected_idx[0]
                if 0 <= idx < len(windows):
                    result["value"] = windows[idx]
                    root.quit()
                    return

        # Bind selection events
        listbox.bind("<<ListboxSelect>>", on_listbox_select)
        listbox.bind("<Double-Button-1>", lambda e: on_select_window())

        # Auto-select first item if list is not empty
        if windows:
            listbox.selection_set(0)
            listbox.activate(0)
            update_preview(0)
        else:
            # Show message in preview if no windows
            info_text.config(state=tk.NORMAL)
            info_text.delete(1.0, tk.END)
            info_text.insert(tk.END, "No windows detected.\n\n")
            info_text.insert(tk.END, "This might happen if:\n")
            info_text.insert(tk.END, "* All windows are minimized\n")
            info_text.insert(tk.END, "* Windows are too small\n")
            info_text.insert(tk.END, "* Permission issues\n\n")
            info_text.insert(tk.END, "Try 'Record Full Screen' instead.")
            info_text.config(state=tk.DISABLED)

        def on_fullscreen():
            result["value"] = "fullscreen"
            root.quit()

        def on_custom():
            result["value"] = "custom"
            root.quit()

        def on_cancel():
            result["value"] = "cancelled"
            root.quit()

        # Buttons with better styling
        button_frame = tk.Frame(root)
        button_frame.pack(pady=15)

        # Primary action button (highlighted)
        select_btn = tk.Button(
            button_frame,
            text="[OK] Record Selected Window",
            command=on_select_window,
            width=22,
            font=("Arial", 10, "bold"),
            bg="#4CAF50",
            fg="white",
            relief=tk.RAISED,
            bd=2,
        )
        select_btn.pack(side=tk.LEFT, padx=5)

        # Secondary buttons
        fullscreen_btn = tk.Button(
            button_frame,
            text="Record Full Screen",
            command=on_fullscreen,
            width=18,
            font=("Arial", 9),
        )
        fullscreen_btn.pack(side=tk.LEFT, padx=5)

        custom_btn = tk.Button(
            button_frame, text="Draw Custom Region", command=on_custom, width=18, font=("Arial", 9)
        )
        custom_btn.pack(side=tk.LEFT, padx=5)

        cancel_btn = tk.Button(
            button_frame, text="Cancel", command=on_cancel, width=12, font=("Arial", 9)
        )
        cancel_btn.pack(side=tk.LEFT, padx=5)

        # Keyboard shortcuts
        root.bind("<Escape>", lambda e: on_cancel())
        root.bind("<Return>", lambda e: on_select_window())
        root.bind("<F11>", lambda e: on_fullscreen())

        # Instructions with better formatting
        instructions_frame = tk.Frame(root)
        instructions_frame.pack(pady=10)

        instructions = tk.Label(
            instructions_frame,
            text=(
                "* Click to select * Ctrl+Click or Shift+Click to select multiple "
                "* Double-click or Enter to confirm * F11 for fullscreen * Esc to cancel"
            ),
            font=("Arial", 9),
            fg="gray",
            wraplength=550,
        )
        instructions.pack()

        root.mainloop()
        root.destroy()

        return result["value"]

    def _draw_custom_region(self) -> Tuple[List[Dict[str, Any]], List[Optional[int]]]:
        """Show overlay for drawing a custom region."""
        regions: List[Dict[str, Any]] = []
        window_ids: List[Optional[int]] = []

        root = tk.Tk()
        root.attributes("-fullscreen", True)
        root.attributes("-alpha", 0.3)
        root.attributes("-topmost", True)
        root.config(cursor="cross")

        canvas = tk.Canvas(root, bg="gray", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)

        # Instructions text
        canvas.create_text(
            root.winfo_screenwidth() // 2,
            50,
            text="Click and drag to select a region. Press Escape to cancel.",
            font=("Arial", 16),
            fill="white",
        )

        selection = {"start": None, "rect": None}

        def on_button_press(event):
            selection["start"] = (event.x, event.y)
            if selection["rect"] is not None:
                canvas.delete(selection["rect"])
            selection["rect"] = canvas.create_rectangle(
                event.x, event.y, event.x, event.y, outline="red", width=3
            )

        def on_move(event):
            if selection["start"] and selection["rect"]:
                x0, y0 = selection["start"]
                canvas.coords(selection["rect"], x0, y0, event.x, event.y)

        def on_release(event):
            if selection["start"] and selection["rect"]:
                x0, y0 = selection["start"]
                x1, y1 = event.x, event.y
                left, top = min(x0, x1), min(y0, y1)
                width, height = abs(x1 - x0), abs(y1 - y0)
                if width > 10 and height > 10:  # Minimum size
                    regions.append(
                        {
                            "left": int(left),
                            "top": int(top),
                            "width": int(width),
                            "height": int(height),
                        }
                    )
                    window_ids.append(None)
            root.quit()

        canvas.bind("<ButtonPress-1>", on_button_press)
        canvas.bind("<B1-Motion>", on_move)
        canvas.bind("<ButtonRelease-1>", on_release)

        # Escape to cancel
        root.bind("<Escape>", lambda _: (regions.clear(), window_ids.clear(), root.quit()))

        root.mainloop()
        root.destroy()

        if not regions:
            raise RuntimeError("Selection cancelled")
        return regions, window_ids
