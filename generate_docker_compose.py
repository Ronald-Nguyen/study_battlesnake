#!/usr/bin/env python3
"""
Generate docker-compose.test.yml from snakes_config.json
"""

import json
import yaml
import argparse


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate docker-compose file from snake configuration"
    )
    parser.add_argument(
        "--config", type=str, default="snakes_config.json", help="Path to snakes configuration file"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="docker-compose.test.yml",
        help="Path to output docker-compose file",
    )
    return parser.parse_args()


def generate_docker_compose(
    config_file="snakes_config.json", output_file="docker-compose.test.yml"
):
    """Generate docker-compose file from snake configuration"""

    # Read config
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: {config_file} not found!")
        raise FileNotFoundError(f"Error: {config_file} not found!")

    snakes = config.get("snakes", [])

    if not snakes:
        print("Error: No snakes defined in config!")
        raise ValueError("Error: No snakes defined in config!")

    # Build docker-compose structure
    compose = {"version": "3.3", "services": {}}

    for snake in snakes:
        service_name = f"{snake['name']}-service".lower()
        compose["services"][service_name] = {
            "build": snake["directory"],
            "ports": [f"{snake['port']}:{snake['port']}"],
            "environment": [f"PORT={snake['port']}", f"SNAKE_NAME={snake['name']}"],
            "container_name": f"{snake['name']}-test".lower(),
        }

    # Write docker-compose file
    with open(output_file, "w") as f:
        yaml.dump(compose, f, default_flow_style=False, sort_keys=False)

    print(f"Generated {output_file} with {len(snakes)} snakes:")
    for snake in snakes:
        print(f"  - {snake['name']} on port {snake['port']}")


if __name__ == "__main__":
    args = parse_args()
    generate_docker_compose(args.config, args.output)
