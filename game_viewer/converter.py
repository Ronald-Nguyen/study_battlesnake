import json
from pathlib import Path


class GameLogConverter:
    def __init__(self, games_dir=None):
        if games_dir is None:
            games_dir = Path(__file__).parent.parent / "tournaments"
        self.games_dir = Path(games_dir)

    def convert_to_battlesnake_format_tournament(self, tournament_id, matchup_id, game_id):
        """Convert tournament game log to battlesnake format"""
        game_file = self.games_dir / tournament_id / matchup_id / "games" / f"{game_id}.json"
        return self._convert_file_to_battlesnake_format(game_file, game_id)

    def _convert_file_to_battlesnake_format(self, game_file, game_id):
        """Internal method to convert a game file to battlesnake format"""
        with open(game_file, "r") as f:
            lines = [line.strip() for line in f if line.strip()]

            # First line should be game metadata
            game_metadata = None
            if lines:
                try:
                    first_line = json.loads(lines[0])
                    if "ruleset" in first_line and "id" in first_line:
                        game_metadata = first_line
                except json.JSONDecodeError:
                    pass

            # Parse turn data
            turns = []
            for line in lines:
                try:
                    turn_data = json.loads(line)
                    # Only include lines that have the expected structure
                    if "board" in turn_data and "turn" in turn_data:
                        turns.append(turn_data)
                except json.JSONDecodeError:
                    continue

        if not turns:
            raise ValueError(f"No valid game data found in {game_file}")

        # Build game metadata
        if game_metadata:
            ruleset = game_metadata.get("ruleset", {})
            battlesnake_game = {
                "ID": game_metadata.get("id", game_id),
                "Width": turns[0]["board"]["width"],
                "Height": turns[0]["board"]["height"],
                "Ruleset": ruleset,
                "Map": game_metadata.get("map", "standard"),
                "Status": "complete",
                "RulesetName": ruleset.get("name", "standard"),
                "RulesStages": [],
                "SnakeTimeout": game_metadata.get("timeout", 500),
                "Source": game_metadata.get("source", ""),
            }
        else:
            # Fallback for games without metadata
            battlesnake_game = {
                "ID": game_id,
                "Width": turns[0]["board"]["width"],
                "Height": turns[0]["board"]["height"],
                "Ruleset": {"name": "standard"},
                "Map": "standard",
                "Status": "complete",
                "RulesetName": "standard",
                "RulesStages": [],
                "SnakeTimeout": 500,
                "Source": "",
            }

        battlesnake_data = {"game": battlesnake_game, "frames": []}

        for turn in turns:
            # Convert food and hazards coordinates to PascalCase
            food_points = [{"X": point["x"], "Y": point["y"]} for point in turn["board"]["food"]]
            hazard_points = [
                {"X": point["x"], "Y": point["y"]} for point in turn["board"]["hazards"]
            ]

            battlesnake_data["frames"].append(
                {
                    "Turn": turn["turn"],
                    "Snakes": self._convert_snakes(turn["board"]["snakes"], turn["turn"]),
                    "Food": food_points,
                    "Hazards": hazard_points,
                }
            )

        return battlesnake_data

    def _convert_snakes(self, snakes, turn_number=0):
        converted_snakes = []
        for snake in snakes:
            # Convert body coordinates to PascalCase
            body_points = []
            for point in snake["body"]:
                body_points.append({"X": point["x"], "Y": point["y"]})

            # Head is the first body point

            # Check if snake is eliminated (health 0 or empty body)
            death = None
            if snake["health"] <= 0 or len(snake["body"]) == 0:
                death = {
                    "Cause": "snake-collision",  # Default cause
                    "Turn": turn_number,
                    "EliminatedBy": "",
                }

            converted_snakes.append(
                {
                    "ID": snake["id"],
                    "Name": snake["name"],
                    "Body": body_points,
                    "Health": snake["health"],
                    "Color": snake.get("customizations", {}).get("color", "#FF0000"),
                    "HeadType": snake.get("customizations", {}).get("head", "default"),
                    "TailType": snake.get("customizations", {}).get("tail", "default"),
                    "Latency": str(snake.get("latency", "0")),
                    "Shout": snake.get("shout", ""),
                    "Squad": snake.get("squad", ""),
                    "Author": "",
                    "StatusCode": 200,
                    "Error": "",
                    "IsBot": False,
                    "IsEnvironment": False,
                    "Death": death,
                }
            )
        return converted_snakes
