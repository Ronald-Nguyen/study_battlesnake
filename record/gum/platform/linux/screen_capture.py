"""
Linux screen capture supporting both X11 and Wayland.

X11: Uses mss (fast, efficient)
Wayland: Uses grim, gnome-screenshot, or Portal (requires user tools)
"""

import os
import subprocess
import tempfile
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def _is_wayland() -> bool:
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


class LinuxScreenCapture:
    """
    Cross-session Linux screen capture.

    Automatically detects X11 vs Wayland and uses appropriate method.
    On X11, uses scrot/import command-line tools for thread-safe capture.
    """

    def __init__(self):
        self._wayland = _is_wayland()
        self._headless_mode = False
        self._capture_tool = None  # 'scrot', 'import', or 'mss'

        if not self._wayland:
            # Check for DISPLAY
            if os.environ.get("DISPLAY") is None:
                self._headless_mode = True
                logger.warning("Running in headless mode - will generate placeholder screenshots")
            else:
                # Prefer command-line tools (thread-safe) over mss
                self._capture_tool = self._detect_capture_tool()
                logger.info(f"Using capture tool: {self._capture_tool}")

    def _detect_capture_tool(self) -> str:
        """Detect which screenshot tool is available."""
        # Try maim first (modern, fast, thread-safe)
        try:
            result = subprocess.run(["which", "maim"], capture_output=True, timeout=2)
            if result.returncode == 0:
                logger.info("Found maim for screen capture (thread-safe)")
                return "maim"
        except Exception as e:
            logger.debug(f"maim detection failed: {e}")

        # Try scrot (common on Linux, thread-safe)
        try:
            result = subprocess.run(["which", "scrot"], capture_output=True, timeout=2)
            if result.returncode == 0:
                logger.info("Found scrot for screen capture (thread-safe)")
                return "scrot"
        except Exception as e:
            logger.debug(f"scrot detection failed: {e}")

        # Try ImageMagick's import (thread-safe)
        try:
            result = subprocess.run(["which", "import"], capture_output=True, timeout=2)
            if result.returncode == 0:
                logger.info("Found ImageMagick import for screen capture (thread-safe)")
                return "import"
        except Exception as e:
            logger.debug(f"import detection failed: {e}")

        # Fallback to mss (has threading issues on Linux!)
        try:
            pass

            logger.warning(
                "Using mss for screen capture - may have threading issues on Linux! "
                "Install maim or scrot: sudo pacman -S maim (Arch) or sudo apt install maim (Debian/Ubuntu)"
            )
            return "mss"
        except ImportError:
            logger.debug("mss not available")

        logger.error("No screen capture tool found!")
        return "none"

    def grab(self, region: Dict[str, Any], window_id: Optional[int] = None) -> Optional[Any]:
        """
        Capture a screen region or specific window.

        Args:
            region: Dict with 'left', 'top', 'width', 'height'
            window_id: Optional X11 window ID for window-specific capture

        Returns:
            mss-compatible screenshot object or PIL Image
        """
        if self._wayland:
            return self._grab_wayland(region)
        return self._grab_x11(region, window_id)

    def _grab_x11(self, region: Dict[str, Any], window_id: Optional[int] = None) -> Optional[Any]:
        """Capture using maim/scrot/import/mss on X11, or placeholder in headless mode."""
        if self._headless_mode:
            return self._create_placeholder_image(region)

        if self._capture_tool == "maim":
            return self._grab_with_maim(region, window_id)
        elif self._capture_tool == "scrot":
            return self._grab_with_scrot(region)
        elif self._capture_tool == "import":
            return self._grab_with_import(region)
        elif self._capture_tool == "mss":
            return self._grab_with_mss(region)
        else:
            logger.error("No capture tool available")
            return self._create_placeholder_image(region)

    def _grab_with_maim(
        self, region: Dict[str, Any], window_id: Optional[int] = None
    ) -> Optional[Any]:
        """Capture using maim (thread-safe, modern alternative to scrot).

        If window_id is provided, captures that specific window (ignoring overlapping windows).
        Otherwise, captures the screen region (whatever is visible at those coordinates).
        """
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            output_path = f.name

        used_window_capture = False
        try:
            # If we have a window ID, use window-specific capture
            # This captures only the window content, ignoring any windows on top
            if window_id is not None:
                logger.debug(f"maim capture: window_id={window_id} (window-specific capture)")
                result = subprocess.run(
                    ["maim", "-i", str(window_id), output_path],
                    capture_output=True,
                    timeout=10,
                    env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
                )

                if result.returncode == 0 and Path(output_path).exists() and Path(output_path).stat().st_size > 0:
                    used_window_capture = True
                else:
                    logger.debug(
                        f"maim window capture failed: {result.stderr.decode() if result.stderr else ''}, "
                        f"falling back to region capture"
                    )
                    window_id = None  # Fall through to region capture

            # Region-based capture (fallback or when no window_id)
            if window_id is None:
                geometry = f"{region['width']}x{region['height']}+{region['left']}+{region['top']}"
                logger.debug(f"maim capture: geometry={geometry}, region={region}")
                result = subprocess.run(
                    ["maim", "-g", geometry, output_path],
                    capture_output=True,
                    timeout=10,
                    env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
                )

                if result.returncode != 0:
                    logger.debug(
                        f"maim region capture failed, trying full screen: {result.stderr.decode() if result.stderr else ''}"
                    )
                    # Fallback to full screen + crop
                    result = subprocess.run(
                        ["maim", output_path],
                        capture_output=True,
                        timeout=10,
                        env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
                    )

                if result.returncode != 0:
                    logger.error(
                        f"maim failed: {result.stderr.decode() if result.stderr else 'unknown error'}"
                    )
                    return None

            if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
                logger.error("maim did not create valid output file")
                return None

            img = Image.open(output_path)

            # For window-specific capture, use the image as-is (don't crop)
            # maim -i captures the entire window content correctly
            if used_window_capture:
                logger.debug(f"Window capture: using full image {img.size[0]}x{img.size[1]}")
                result_img = img.convert("RGB")
                img.close()
                return MSSCompatibleImage(result_img)

            # For region/fullscreen capture, crop if needed
            if img.size != (region["width"], region["height"]):
                img_width, img_height = img.size
                left = max(0, min(region["left"], img_width - 1))
                top = max(0, min(region["top"], img_height - 1))
                right = min(region["left"] + region["width"], img_width)
                bottom = min(region["top"] + region["height"], img_height)
                cropped = img.crop((left, top, right, bottom)).convert("RGB")
                img.close()
                return MSSCompatibleImage(cropped)

            result_img = img.convert("RGB")
            img.close()
            return MSSCompatibleImage(result_img)

        except subprocess.TimeoutExpired:
            logger.error("maim timed out")
            return None
        except Exception as e:
            logger.error(f"maim capture failed: {e}")
            return None
        finally:
            try:
                if Path(output_path).exists():
                    os.unlink(output_path)
            except Exception:
                pass

    def _grab_with_scrot(self, region: Dict[str, Any]) -> Optional[Any]:
        """Capture using scrot (thread-safe)."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            output_path = f.name

        try:
            # Capture full screen and crop (most reliable method)
            # scrot needs the filename as the last argument
            result = subprocess.run(
                ["scrot", "--overwrite", output_path],
                capture_output=True,
                timeout=10,
                env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
            )

            if result.returncode != 0:
                err_msg = result.stderr.decode() if result.stderr else "no error message"
                logger.error(f"scrot failed with code {result.returncode}: {err_msg}")
                return None

            if not Path(output_path).exists():
                logger.error("scrot did not create output file")
                return None

            file_size = Path(output_path).stat().st_size
            if file_size == 0:
                logger.error("scrot created empty file")
                return None

            logger.debug(f"scrot captured {file_size} bytes to {output_path}")

            # Open and crop to region
            img = Image.open(output_path)
            img_width, img_height = img.size

            # Validate crop bounds
            left = max(0, min(region["left"], img_width - 1))
            top = max(0, min(region["top"], img_height - 1))
            right = min(region["left"] + region["width"], img_width)
            bottom = min(region["top"] + region["height"], img_height)

            if right <= left or bottom <= top:
                logger.error(
                    f"Invalid crop region: ({left}, {top}, {right}, {bottom}) for image size ({img_width}, {img_height})"
                )
                img.close()
                return None

            cropped = img.crop((left, top, right, bottom)).convert("RGB")
            img.close()

            return MSSCompatibleImage(cropped)

        except subprocess.TimeoutExpired:
            logger.error("scrot timed out")
            return None
        except Exception as e:
            logger.error(f"scrot capture failed: {e}")
            return None
        finally:
            try:
                if Path(output_path).exists():
                    os.unlink(output_path)
            except Exception:
                pass

    def _grab_with_import(self, region: Dict[str, Any]) -> Optional[Any]:
        """Capture using ImageMagick import (thread-safe)."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            output_path = f.name

        try:
            # import uses -crop geometry: WxH+X+Y
            geometry = f"{region['width']}x{region['height']}+{region['left']}+{region['top']}"
            result = subprocess.run(
                ["import", "-window", "root", "-crop", geometry, output_path],
                capture_output=True,
                timeout=5,
            )

            if result.returncode == 0 and Path(output_path).exists():
                img = Image.open(output_path).convert("RGB")
                return MSSCompatibleImage(img)

            logger.error(
                f"import failed: {result.stderr.decode() if result.stderr else 'unknown error'}"
            )
            return None

        except subprocess.TimeoutExpired:
            logger.error("import timed out")
            return None
        except Exception as e:
            logger.error(f"import capture failed: {e}")
            return None
        finally:
            try:
                if Path(output_path).exists():
                    os.unlink(output_path)
            except Exception:
                pass

    def _grab_with_mss(self, region: Dict[str, Any]) -> Optional[Any]:
        """Capture using mss (creates new instance each time for thread safety)."""
        try:
            import mss

            # Create a new mss instance for each capture (thread-safe)
            with mss.mss() as sct:
                return sct.grab(region)
        except Exception as e:
            logger.error(f"mss capture failed: {e}")
            return None

    def _create_placeholder_image(self, region: Dict[str, Any]) -> "MSSCompatibleImage":
        """Create a placeholder image for headless mode."""
        width = region.get("width", 1920)
        height = region.get("height", 1080)

        # Create a simple placeholder image (gray with text)
        img = Image.new("RGB", (width, height), color=(128, 128, 128))
        draw = ImageDraw.Draw(img)

        # Add text indicating headless mode
        try:
            from PIL import ImageFont

            # Try to use a default font
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
            except Exception:
                font = ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        text = "Headless Mode - No Display Available"
        # Get text bounding box
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        # Center the text
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        draw.text((x, y), text, fill=(255, 255, 255), font=font)

        return MSSCompatibleImage(img)

    def _grab_wayland(self, region: Dict[str, Any]) -> Optional[Any]:
        """
        Capture using Wayland-native tools.

        Returns a PIL Image wrapped to be mss-compatible.
        """
        # Create temp file for screenshot
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            output_path = f.name

        logger.debug(f"Attempting Wayland screenshot capture to {output_path}")
        logger.debug(f"Region: {region}")

        result_image = None
        try:
            # Build region geometry string
            geometry = f"{region['left']},{region['top']} {region['width']}x{region['height']}"

            # Try grim first (fastest, wlroots-native)
            logger.debug("Trying grim...")
            captured = self._try_grim(output_path, geometry, region)
            if captured:
                result_image = self._load_as_mss_compatible(output_path)
                if result_image:
                    logger.info("Screenshot captured successfully using grim")
                    return result_image

            # Try gnome-screenshot with crop
            logger.debug("Trying gnome-screenshot...")
            captured = self._try_gnome_screenshot(output_path, region)
            if captured:
                result_image = self._load_as_mss_compatible(output_path)
                if result_image:
                    logger.info("Screenshot captured successfully using gnome-screenshot")
                    return result_image

            # Try spectacle (KDE)
            logger.debug("Trying spectacle...")
            captured = self._try_spectacle(output_path, region)
            if captured:
                result_image = self._load_as_mss_compatible(output_path)
                if result_image:
                    logger.info("Screenshot captured successfully using spectacle")
                    return result_image

            logger.error(
                "No Wayland screenshot tool available or all failed. "
                "Install one of: grim, gnome-screenshot, spectacle"
            )
            return None

        finally:
            # Clean up temp file only if we successfully loaded the image
            if result_image is None:
                try:
                    if Path(output_path).exists():
                        os.unlink(output_path)
                except OSError:
                    pass
            else:
                # Delete after successful load
                try:
                    os.unlink(output_path)
                except OSError:
                    pass

    def _try_grim(self, output_path: str, geometry: str, region: Dict[str, Any]) -> bool:
        """Try capturing with grim."""
        try:
            result = subprocess.run(
                ["grim", "-g", geometry, output_path], capture_output=True, timeout=5
            )
            return result.returncode == 0 and Path(output_path).exists()
        except FileNotFoundError:
            return False
        except subprocess.TimeoutExpired:
            logger.warning("grim timed out")
            return False
        except Exception as e:
            logger.debug("grim failed: %s", e)
            return False

    def _try_gnome_screenshot(self, output_path: str, region: Dict[str, Any]) -> bool:
        """Try capturing with gnome-screenshot (captures full screen, then crop)."""
        try:
            # gnome-screenshot can't capture specific regions without interaction
            # Capture full screen and crop
            result = subprocess.run(
                ["gnome-screenshot", "-f", output_path],
                capture_output=True,
                timeout=10,  # Increased timeout for reliability
                stderr=subprocess.PIPE,
            )

            # Log stderr for debugging
            if result.stderr:
                logger.debug(
                    f"gnome-screenshot stderr: {result.stderr.decode('utf-8', errors='ignore')}"
                )

            if result.returncode != 0:
                logger.debug(f"gnome-screenshot returned code {result.returncode}")
                return False

            if not Path(output_path).exists():
                logger.debug(f"gnome-screenshot did not create output file {output_path}")
                return False

            # Verify file has content
            if Path(output_path).stat().st_size == 0:
                logger.debug("gnome-screenshot created empty file")
                return False

            # Crop to region
            img = Image.open(output_path)

            # Validate crop region
            img_width, img_height = img.size
            left = max(0, min(region["left"], img_width - 1))
            top = max(0, min(region["top"], img_height - 1))
            right = max(left + 1, min(region["left"] + region["width"], img_width))
            bottom = max(top + 1, min(region["top"] + region["height"], img_height))

            cropped = img.crop((left, top, right, bottom))
            cropped.save(output_path, "PNG")
            img.close()

            logger.debug(f"gnome-screenshot succeeded: {output_path}")
            return True

        except FileNotFoundError:
            logger.debug("gnome-screenshot command not found")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("gnome-screenshot timed out after 10 seconds")
            return False
        except Exception as e:
            logger.error(f"gnome-screenshot failed with exception: {e}", exc_info=True)
            return False

    def _try_spectacle(self, output_path: str, region: Dict[str, Any]) -> bool:
        """Try capturing with spectacle (KDE)."""
        try:
            # spectacle -b = background mode, -n = no notification, -r = region
            # Unfortunately spectacle's region mode is interactive
            # Use full screen and crop
            result = subprocess.run(
                ["spectacle", "-b", "-n", "-f", "-o", output_path], capture_output=True, timeout=5
            )
            if result.returncode != 0 or not Path(output_path).exists():
                return False

            # Crop to region
            img = Image.open(output_path)
            cropped = img.crop(
                (
                    region["left"],
                    region["top"],
                    region["left"] + region["width"],
                    region["top"] + region["height"],
                )
            )
            cropped.save(output_path)
            return True

        except FileNotFoundError:
            return False
        except subprocess.TimeoutExpired:
            logger.warning("spectacle timed out")
            return False
        except Exception as e:
            logger.debug("spectacle failed: %s", e)
            return False

    def _load_as_mss_compatible(self, path: str) -> Optional["MSSCompatibleImage"]:
        """Load image and wrap in mss-compatible object."""
        try:
            img = Image.open(path).convert("RGB")
            return MSSCompatibleImage(img)
        except Exception as e:
            logger.error("Failed to load screenshot: %s", e)
            return None

    def close(self):
        """Clean up resources."""
        pass  # No persistent resources to clean up


class MSSCompatibleImage:
    """
    Wrapper to make PIL Image compatible with mss screenshot interface.

    Provides .rgb, .width, .height attributes like mss screenshots.
    """

    def __init__(self, img: Image.Image):
        self._img = img
        self.width = img.width
        self.height = img.height
        self.rgb = img.tobytes()

    def __del__(self):
        if hasattr(self, "_img") and self._img:
            self._img.close()
