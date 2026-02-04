import os
import subprocess


def check_and_build_rules_cli():
    """
    Check if Battlesnake rules CLI exists, build if necessary.
    Returns True if CLI is ready, False if build failed.
    """
    cli_path = "rules/battlesnake"

    # Check if binary exists and is executable
    if os.path.exists(cli_path) and os.access(cli_path, os.X_OK):
        print(f"[OK] Found Battlesnake CLI at {cli_path}")
        return True

    print(f"Battlesnake CLI not found at {cli_path}")

    # Check if we have the rules directory
    if not os.path.exists("rules"):
        print("[X] ERROR: 'rules' directory not found")
        print("  Please clone the Battlesnake rules repository:")
        print("  git clone https://github.com/BattlesnakeOfficial/rules.git")
        return False

    # Try to build the CLI
    print("Attempting to build Battlesnake CLI...")

    # Check if it's a Go project (has go.mod or main.go)
    if os.path.exists("rules/go.mod") or os.path.exists("rules/cli/main.go"):
        return _build_go_cli()
    elif os.path.exists("rules/Makefile"):
        return _build_with_make()
    else:
        print("[X] ERROR: Don't know how to build the CLI")
        print("  Please build manually in the rules/ directory")
        return False


def _build_go_cli():
    """Build CLI using Go"""
    print("Building with Go...")

    # Check if Go is installed
    go_check = subprocess.run(["which", "go"], capture_output=True)
    if go_check.returncode != 0:
        print("[X] ERROR: Go is not installed")
        print("  Install Go: https://golang.org/doc/install")
        return False

    # Try building in rules/cli directory
    build_dir = "rules/cli" if os.path.exists("rules/cli") else "rules"

    try:
        print(f"Running: go build in {build_dir}")
        result = subprocess.run(
            ["go", "build", "-o", "../battlesnake"],
            cwd=build_dir,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        if result.returncode == 0:
            print("[OK] Successfully built Battlesnake CLI")

            # Make it executable
            os.chmod("rules/battlesnake", 0o755)
            return True
        else:
            print("[X] Build failed:")
            print(result.stderr)
            return False

    except subprocess.TimeoutExpired:
        print("[X] Build timed out after 2 minutes")
        return False
    except Exception as e:
        print(f"[X] Build error: {e}")
        return False


def _build_with_make():
    """Build CLI using Makefile"""
    print("Building with make...")

    try:
        result = subprocess.run(
            ["make", "build"], cwd="rules", capture_output=True, text=True, timeout=120
        )

        if result.returncode == 0:
            print("[OK] Successfully built Battlesnake CLI")
            return True
        else:
            print("[X] Build failed:")
            print(result.stderr)
            return False

    except FileNotFoundError:
        print("[X] ERROR: 'make' command not found")
        return False
    except Exception as e:
        print(f"[X] Build error: {e}")
        return False
