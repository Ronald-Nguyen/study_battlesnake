#!/usr/bin/env python3
"""Upload recording data to GCS using pre-signed URLs (no credentials needed)"""
import json
import tarfile
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
import tempfile


class GCSUploader:
    """Simple uploader for recording data using pre-signed URLs"""

    def __init__(self, config_path: str = "haic_starter/eval/snapshot_config.json"):
        """
        Initialize uploader with shared config from haic_starter.

        Args:
            config_path: Path to snapshot config (default: haic_starter/eval/snapshot_config.json)
        """
        self.config = self._load_config(config_path)
        self.user_id = self.config.get("user_id")
        self.enabled = self.config.get("enabled", False)
        
        # Determine which slot to use based on whether init was uploaded
        # Init uses slot 0, final uses slot 1
        init_uploaded_file = Path(".init_uploaded")
        if init_uploaded_file.exists():
            self._session_slot = 1  # Final stage
            self._stage = "final"
        else:
            self._session_slot = 0  # Init stage
            self._stage = "init"

    def _load_config(self, config_path: str) -> Dict:
        """Load GCS configuration"""
        if not Path(config_path).exists():
            return {"enabled": False}

        with open(config_path) as f:
            return json.load(f)

    def create_bundle(self, data_dir: str) -> tuple[Optional[Path], Optional[Path]]:
        """
        Create tarball bundle including screenshots, database, and AI session logs.

        Returns:
            (tarball_path, metadata_path) or (None, None) if error
        """
        data_path = Path(data_dir).expanduser()
        screenshots_dir = data_path / "screenshots"
        actions_db = data_path / "actions.db"
        ai_sessions_dir = screenshots_dir / "ai_sessions"  # AI logs are in screenshots/ai_sessions/

        # Validate
        if not screenshots_dir.exists() or not actions_db.exists():
            return None, None

        # Create tarball
        timestamp = int(datetime.now().timestamp())
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_dir = Path(tempfile.gettempdir())

        tarball_name = f"{self.user_id}_session_{timestamp}.tar.gz"
        tarball_path = temp_dir / tarball_name

        with tarfile.open(tarball_path, "w:gz") as tar:
            tar.add(screenshots_dir, arcname="screenshots")
            tar.add(actions_db, arcname="actions.db")
            # Add AI session logs if they exist
            if ai_sessions_dir.exists():
                tar.add(ai_sessions_dir, arcname="screenshots/ai_sessions")

        # Count files for metadata
        screenshot_files = list(screenshots_dir.glob("*.jpg")) + list(screenshots_dir.glob("*.png"))
        ai_log_files = list(ai_sessions_dir.glob("*.log")) if ai_sessions_dir.exists() else []

        # Create metadata
        metadata = {
            "user_id": self.user_id,
            "type": "recording_session",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "timestamp_unix": timestamp,
            "screenshot_count": len(screenshot_files),
            "ai_session_log_count": len(ai_log_files),
            "bundle_size_mb": tarball_path.stat().st_size / (1024 * 1024),
            "storage": "gcs_only",
        }

        metadata_path = temp_dir / f"{self.user_id}_session_{timestamp}.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return tarball_path, metadata_path

    def upload(self, tarball_path: Path, metadata_path: Path) -> Dict:
        """Upload using pre-signed URLs"""
        if not self.enabled:
            return {"status": "disabled"}

        try:
            session_urls = self.config.get("session_urls", [])
            if not session_urls or self._session_slot >= len(session_urls):
                return {
                    "status": "error",
                    "error": f"No available upload slot for {self._stage} stage. "
                    f"Expected slot {self._session_slot} but only {len(session_urls)} slots available.",
                }

            slot = session_urls[self._session_slot]
            print(f"Using slot {self._session_slot} for {self._stage} stage")

            # Upload tarball
            with open(tarball_path, "rb") as f:
                response = requests.put(
                    slot["tarball_url"],
                    data=f,
                    headers={"Content-Type": "application/gzip"},
                    timeout=1200,
                )
                response.raise_for_status()

            # Upload metadata
            with open(metadata_path, "rb") as f:
                response = requests.put(
                    slot["metadata_url"],
                    data=f,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )
                response.raise_for_status()

            return {"status": "success", "slot": slot["slot"]}

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else None
            if status_code == 403:
                return {
                    "status": "error",
                    "error": "403 Forbidden - URLs may have expired (valid for 7 days). "
                    "Contact study coordinators for new credentials.",
                }
            elif status_code == 400:
                return {
                    "status": "error",
                    "error": "400 Bad Request - check config file has valid URLs",
                }
            return {"status": "error", "error": str(e)}

        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "error": "Upload timed out - check your internet connection and try again",
            }

        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "error": "Connection failed - check your internet connection",
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def upload_recording(self, data_dir: str) -> Dict:
        """Create bundle and upload in one call"""
        if not self.enabled:
            return {"status": "disabled"}

        print("Creating bundle...")

        tarball, metadata = self.create_bundle(data_dir)

        if not tarball:
            return {"status": "error", "error": "Failed to create bundle"}

        bundle_size_mb = tarball.stat().st_size / (1024 * 1024)
        print(f"Bundle size: {bundle_size_mb:.1f} MB")
        print("Uploading to GCS (this may take a few minutes)...")

        result = self.upload(tarball, metadata)

        # Cleanup temp files
        tarball.unlink(missing_ok=True)
        metadata.unlink(missing_ok=True)

        return result
