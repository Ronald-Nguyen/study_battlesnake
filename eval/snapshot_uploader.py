#!/usr/bin/env python3
"""Upload snapshots using pre-generated signed URLs"""
import os
import json
import tarfile
import hashlib
import requests
from pathlib import Path
from datetime import datetime
import tempfile
import sys


class SnapshotUploader:
    """Uploader using pre-generated signed URLs"""

    def __init__(self, config):
        self.user_id = config["user_id"]
        self.config = config
        # Load counter from file, or start at 0
        self._counter_file = Path(".tournament_slot_counter")
        if self._counter_file.exists():
            try:
                self._tournament_slot_counter = int(self._counter_file.read_text().strip())
                print(f"Resuming from tournament slot {self._tournament_slot_counter}")
            except (ValueError, IOError):
                self._tournament_slot_counter = 0
        else:
            self._tournament_slot_counter = 0

    def create_snapshot(self, source_dir, identifier, results_data=None):
        """Create tarball and metadata

        Args:
            identifier: 'init', 'final', or tournament ID
        """
        source_path = Path(source_dir)
        timestamp = int(datetime.now().timestamp())
        temp_dir = Path(tempfile.gettempdir())

        # Create tarball
        tarball_name = f"{self.user_id}_{identifier}_{timestamp}.tar.gz"
        tarball_path = temp_dir / tarball_name

        print(f"Creating snapshot: {tarball_name}")

        with tarfile.open(tarball_path, "w:gz") as tar:
            tar.add(source_path, arcname=source_path.name)

        # Create metadata
        is_tournament = identifier.startswith("round_robin_")
        metadata = {
            "user_id": self.user_id,
            "identifier": identifier,
            "type": "tournament" if is_tournament else "submission",
            "timestamp": datetime.now().isoformat(),
            "timestamp_unix": timestamp,
            "source_dir": str(source_path),
            "code_hash": self._calculate_hash(source_path),
            "results": results_data,
        }

        metadata_name = f"{self.user_id}_{identifier}_{timestamp}.json"
        metadata_path = temp_dir / metadata_name

        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return tarball_path, metadata_path

    def upload(self, tarball_path, metadata_path, identifier):
        """Upload using pre-generated signed URLs

        Args:
            identifier: 'init', 'final', or tournament ID
        """
        try:
            is_tournament = identifier.startswith("round_robin_")

            if is_tournament:
                if "tournament_urls" not in self.config:
                    raise Exception("No tournament upload URLs")

                if self._tournament_slot_counter >= len(self.config["tournament_urls"]):
                    raise Exception("No more tournament slots")

                slot = self.config["tournament_urls"][self._tournament_slot_counter]
                tarball_url = slot["tarball_url"]  # Use directly, no replacement
                metadata_url = slot["metadata_url"]

                print(f"Using tournament slot {slot['slot']}")

                # Increment and save counter to file
                self._tournament_slot_counter += 1
                self._counter_file.write_text(str(self._tournament_slot_counter))
                print(f"Next tournament will use slot {self._tournament_slot_counter}")

            else:
                # Official submission
                tarball_url = self.config[f"{identifier}_tarball_url"]  # Use directly
                metadata_url = self.config[f"{identifier}_metadata_url"]

            # Upload tarball
            print(f"Uploading code ({tarball_path.stat().st_size / 1024:.1f} KB)...")
            with open(tarball_path, "rb") as f:
                response = requests.put(
                    tarball_url, data=f, headers={"Content-Type": "application/gzip"}, timeout=300
                )
                response.raise_for_status()

            print("[OK] Code uploaded")

            # Upload metadata
            print("Uploading metadata...")
            with open(metadata_path, "rb") as f:
                response = requests.put(
                    metadata_url, data=f, headers={"Content-Type": "application/json"}, timeout=60
                )
                response.raise_for_status()

            print("[OK] Metadata uploaded")

            return {"status": "success"}

        except requests.exceptions.HTTPError as e:
            error_msg = str(e)
            print(f"\n[X] Upload failed: {error_msg}", file=sys.stderr)

            # Check for common error patterns
            status_code = e.response.status_code if e.response else None
            if status_code == 403:
                print("\n" + "-" * 60, file=sys.stderr)
                print("This error likely means your upload URLs have EXPIRED.", file=sys.stderr)
                print("URLs are valid for 7 days from when they were generated.", file=sys.stderr)
                print("\nTo fix: Contact study coordinators for new credentials.", file=sys.stderr)
                print("-" * 60, file=sys.stderr)
            elif status_code == 400:
                print("\n" + "-" * 60, file=sys.stderr)
                print("Bad request - check your config file has valid URLs.", file=sys.stderr)
                print("-" * 60, file=sys.stderr)

            return {"status": "failed", "error": error_msg}

        except requests.exceptions.Timeout:
            print("\n[X] Upload timed out - please check your internet connection", file=sys.stderr)
            return {"status": "failed", "error": "Request timed out"}

        except requests.exceptions.ConnectionError:
            print("\n[X] Connection error - please check your internet connection", file=sys.stderr)
            return {"status": "failed", "error": "Connection failed"}

        except Exception as e:
            print(f"\n[X] Upload failed: {e}", file=sys.stderr)
            return {"status": "failed", "error": str(e)}

    def _calculate_hash(self, directory):
        hash_obj = hashlib.sha256()
        for file_path in sorted(Path(directory).rglob("*")):
            if file_path.is_file() and not file_path.name.startswith("."):
                hash_obj.update(file_path.name.encode())
                with open(file_path, "rb") as f:
                    hash_obj.update(f.read())
        return hash_obj.hexdigest()


def main():
    """CLI interface"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="your_snake")
    parser.add_argument("--config", default="eval/snapshot_config.json")
    parser.add_argument("--results-file")

    # Either stage or tournament-id
    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--stage", choices=["init", "final"])
    id_group.add_argument("--tournament-id")

    args = parser.parse_args()

    identifier = args.stage if args.stage else args.tournament_id

    # Load config
    with open(args.config) as f:
        config = json.load(f)

    # Load results
    results_data = None
    if args.results_file and os.path.exists(args.results_file):
        with open(args.results_file) as f:
            results_data = json.load(f)

    # Upload
    uploader = SnapshotUploader(config)
    tarball, metadata = uploader.create_snapshot(args.source, identifier, results_data)
    result = uploader.upload(tarball, metadata, identifier)

    tarball.unlink()
    metadata.unlink()

    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
