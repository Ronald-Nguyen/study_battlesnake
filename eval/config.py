# data class for game configuration
from dataclasses import dataclass
import json
from pathlib import Path
import os
import re
import sys


@dataclass
class GameConfig:
    width: int = 11
    height: int = 11
    round_robin: str = ""
    p1_source: str = "main.py"
    p2_source: str = "opponent.py"
    p1_name: str = "AggressiveHunter"
    p1_base_port: int = 7123
    p2_name: str = "DefensiveGuardian"
    p2_base_port: int = 7124


def load_snake_config(path="snakes_config.json"):
    config_path = Path(path)
    try:
        with open(config_path) as f:
            config = json.load(f)
        snakes = config.get("snakes", [])
        if not snakes:
            raise ValueError(f"No snakes defined in {config_path}")
        settings = config.get("tournament_settings", {})
        iterations = settings.get("iterations_per_matchup", 100)
        workers = settings.get("workers", 8)
        return snakes, settings, iterations, workers
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {config_path}: {e}")
    except FileNotFoundError:
        raise ValueError(f"File not found: {config_path}")
    except KeyError as e:
        raise ValueError(f"Key error in {config_path}: {e}")
    except Exception as e:
        raise ValueError(f"Error loading {config_path}: {e}")


def main():
    """CLI interface for config loading"""
    import argparse  # noqa: F811

    parser = argparse.ArgumentParser(description="Load configuration files")
    parser.add_argument("config_file", help="Path to config file")
    parser.add_argument(
        "--type", choices=["snake", "snapshot"], required=True, help="Type of config to load"
    )

    args = parser.parse_args()

    if args.type == "snake":
        try:
            snakes, settings, iterations, workers = load_snake_config(args.config_file)

            # Output bash variable assignments

            # Use $(...) command substitution with printf for proper newlines
            # Or use IFS and read, or just use proper quoting
            snakes_data = [f"{snake['name']}:{snake['port']}" for snake in snakes]

            # Output as space-separated list that bash can easily split
            # Or output as multiple variables
            print(f"SNAKE_DATA='{' '.join(snakes_data)}'")  # Space-separated
            print(f"ITERATIONS={iterations}")
            print(f"WORKERS={workers}")
            print(f"NUM_SNAKES={len(snakes)}")

            sys.exit(0)
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.type == "snapshot":
        try:
            with open(args.config_file) as f:
                config = json.load(f)

            # Check enabled
            if not config.get("enabled", False):
                print("VALIDATION_STATUS='DISABLED'")
                sys.exit(0)

            # Get user_id
            user_id = config.get("user_id")
            if not user_id or user_id == "null":
                user_id = os.getenv("USER", "")

            if not user_id or user_id.strip() == "":
                print("ERROR: user_id is empty", file=sys.stderr)
                sys.exit(1)

            # Validate user_id format
            if not re.match(r"^[a-zA-Z0-9_-]+$", user_id):
                print(
                    f"ERROR: user_id '{user_id}' contains invalid characters", file=sys.stderr
                )
                sys.exit(1)

            # Validate required URL fields exist
            required_urls = [
                "init_tarball_url",
                "init_metadata_url",
                "final_tarball_url",
                "final_metadata_url",
            ]

            missing_urls = [url for url in required_urls if not config.get(url)]
            if missing_urls:
                print(f"ERROR: Missing required URLs: {', '.join(missing_urls)}", file=sys.stderr)
                sys.exit(1)

            # Check if URLs are placeholder values
            placeholder_text = "PASTE_YOUR"
            for url_key in required_urls:
                if placeholder_text in config.get(url_key, ""):
                    print(
                        f"ERROR: {url_key} contains placeholder text. "
                        "Please paste your actual URL.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

            # Output for bash
            print(f"USER_ID='{user_id}'")
            print("VALIDATION_STATUS='VALID'")
            sys.exit(0)

        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
