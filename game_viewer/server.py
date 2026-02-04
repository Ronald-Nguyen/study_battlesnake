from flask import Flask, render_template, jsonify
from flask_cors import CORS
from flask_sock import Sock
from pathlib import Path
import json
import time
from game_viewer.converter import GameLogConverter

app = Flask(__name__)
CORS(app)
sock = Sock(app)

# Get the directory where this script is located
script_dir = Path(__file__).parent
project_dir = script_dir.parent
# Use the tournaments directory in the current directory
default_games_dir = project_dir / "tournaments"

converter = GameLogConverter(default_games_dir)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/games")
def list_all_games():
    """List all available games for next/prev navigation in board viewer"""
    all_games = []

    try:
        for session_dir in converter.games_dir.iterdir():
            if session_dir.is_dir():
                session_id = session_dir.name
                # Only handle round-robin tournaments
                if session_id.startswith("round_robin_"):
                    # It's a tournament with matchups inside
                    for matchup_dir in session_dir.iterdir():
                        if matchup_dir.is_dir():
                            games_subdir = matchup_dir / "games"
                            if games_subdir.exists():
                                for game_file in games_subdir.glob("*.json"):
                                    game_stem = game_file.stem
                                    # Format: tournament_id/matchup_id_game_X
                                    combined_id = f"{session_id}/{matchup_dir.name}_{game_stem}"
                                    all_games.append({"ID": combined_id, "Status": "complete"})
    except Exception as e:
        print(f"Error listing games: {e}")
        return jsonify({"Games": []})

    # Smart sorting: by session, then by game number
    def sort_game_key(game):
        game_id = game["ID"]
        if "_game_" in game_id:
            parts = game_id.split("_game_")
            session = parts[0]
            try:
                game_num = int(parts[1])
                return (session, game_num)
            except Exception:
                return (session, 999999)
        return (game_id, 0)

    all_games.sort(key=sort_game_key)

    print(f"Listed {len(all_games)} total games across all tournaments")
    return jsonify({"Games": all_games})


@app.route("/api/tournaments")
def list_tournaments():
    """List all round-robin tournaments"""
    tournaments = []

    if not default_games_dir.exists():
        return jsonify({"error": f"Games directory not found: {default_games_dir}"}), 404

    for session_dir in default_games_dir.iterdir():
        if session_dir.is_dir():
            session_name = session_dir.name

            if session_name.startswith("round_robin_"):
                # It's a round-robin tournament
                matchup_count = 0
                total_games = 0
                matchups = []

                # Load TrueSkill results if available
                trueskill_file = session_dir / "trueskill_results.json"
                trueskill_data = None
                if trueskill_file.exists():
                    try:
                        with open(trueskill_file, "r") as f:
                            trueskill_data = json.load(f)
                    except Exception:
                        pass

                # Count matchups and games
                for matchup_dir in session_dir.iterdir():
                    if matchup_dir.is_dir():
                        games_subdir = matchup_dir / "games"
                        if games_subdir.exists():
                            game_count = len(list(games_subdir.glob("*.json")))
                            if game_count > 0:
                                matchups.append(
                                    {"name": matchup_dir.name, "game_count": game_count}
                                )
                                total_games += game_count
                                matchup_count += 1

                tournaments.append(
                    {
                        "id": session_name,
                        "type": "round_robin",
                        "matchup_count": matchup_count,
                        "total_games": total_games,
                        "matchups": matchups,
                        "trueskill": trueskill_data,
                        "path": str(session_dir),
                    }
                )

    # Sort tournaments by date (newest first)
    tournaments.sort(key=lambda x: x["id"], reverse=True)

    return jsonify({"tournaments": tournaments})


@app.route("/api/tournaments/<tournament_id>/matchups/<matchup_id>/games")
def list_matchup_games(tournament_id, matchup_id):
    """List all games in a specific matchup within a tournament"""
    games = []
    matchup_path = default_games_dir / tournament_id / matchup_id / "games"

    if not matchup_path.exists():
        return jsonify({"error": f"Matchup not found: {tournament_id}/{matchup_id}"}), 404

    for game_file in matchup_path.glob("*.json"):
        try:
            game_id = game_file.stem
            games.append({"id": game_id, "filename": game_file.name, "path": str(game_file)})
        except Exception as e:
            print(f"Error processing {game_file}: {e}")
            continue

    # Sort by game number
    try:
        games.sort(key=lambda x: int(x["id"].split("_")[1]) if "_" in x["id"] else 0)
    except Exception:
        games.sort(key=lambda x: x["id"])

    return jsonify(games)


# Battlesnake board viewer API endpoints
@app.route("/games/<path:game_id>")
def get_game_info(game_id):
    """Get game metadata for battlesnake board viewer"""

    def get_game_info_from_path(tournament_id, matchup_id, game_id):
        battlesnake_data = converter.convert_to_battlesnake_format_tournament(
            tournament_id, matchup_id, game_id
        )
        game_info = battlesnake_data["game"].copy()
        response = {"Game": game_info}
        return jsonify(response)

    try:
        # Tournament game format: tournament_id/matchup_id_game_X
        if "/" in game_id:
            parts = game_id.split("/")
            if len(parts) >= 2:
                tournament_id = parts[0]
                # The rest might be matchup_game format
                rest = parts[1]
                if "_game_" in rest:
                    matchup_parts = rest.split("_game_")
                    matchup_id = matchup_parts[0]
                    actual_game_id = "game_" + matchup_parts[1]
                    return get_game_info_from_path(tournament_id, matchup_id, actual_game_id)

        return jsonify({"error": "Game not found"}), 404
    except Exception as e:
        print(f"Error in get_game_info: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@sock.route("/games/<path:game_id>/events")
def get_game_events_ws(ws, game_id):
    """Get game events for battlesnake board viewer using WebSocket"""
    print(f"========== WebSocket connected for game: {game_id} ==========")

    try:
        # Tournament game format: tournament_id/matchup_id_game_X
        if "/" in game_id:
            parts = game_id.split("/")
            if len(parts) >= 2:
                tournament_id = parts[0]
                rest = parts[1]
                if "_game_" in rest:
                    matchup_parts = rest.split("_game_")
                    matchup_id = matchup_parts[0]
                    actual_game_id = "game_" + matchup_parts[1]

                    battlesnake_data = converter.convert_to_battlesnake_format_tournament(
                        tournament_id, matchup_id, actual_game_id
                    )

                    # Send each frame
                    for frame in battlesnake_data["frames"]:
                        event = {"Type": "frame", "Data": frame}
                        ws.send(json.dumps(event))
                        time.sleep(0.01)

                    # Send game end event
                    game_end_event = {
                        "Type": "game_end",
                        "Data": {"game": battlesnake_data["game"]},
                    }
                    ws.send(json.dumps(game_end_event))
                    return

        # Game not found
        print(f"ERROR: Game not found: {game_id}")
        error_event = {"Type": "error", "Data": {"error": "Game not found"}}
        ws.send(json.dumps(error_event))

    except Exception as e:
        print(f"EXCEPTION in WebSocket handler: {e}")
        import traceback

        traceback.print_exc()

        try:
            error_event = {"Type": "error", "Data": {"error": str(e)}}
            ws.send(json.dumps(error_event))
        except Exception:
            pass


if __name__ == "__main__":
    app.run(debug=True, port=5000)
