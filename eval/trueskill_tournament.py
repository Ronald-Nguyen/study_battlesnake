"""
Run a round-robin tournament between multiple snakes and compute TrueSkill ratings.
"""

import argparse
import json
import os
import random
from datetime import datetime
from pathlib import Path
from trueskill import Rating, rate_1vs1, global_env
from eval.config import GameConfig
from eval.pairwise_benchmark import BenchmarkRunner


class TrueSkillTournament:
    def __init__(self, snakes, iterations=100, workers=8, tournament_id=None):
        """
        Args:
            snakes: List of dicts with keys: 'name', 'port'
            iterations: Games per matchup
            workers: Parallel workers
        """
        self.snakes = snakes
        self.iterations = iterations
        self.workers = workers
        self.ratings = {snake["name"]: Rating() for snake in snakes}
        self.matchup_results = {}
        if tournament_id:
            self.round_robin = tournament_id
        else:
            self.round_robin = f"round_robin_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.output_dir = f"tournaments/{self.round_robin}"
        os.makedirs(self.output_dir, exist_ok=True)

        # Configure TrueSkill (conservative settings for small sample sizes)
        global_env()

    def run_tournament(self):
        """Run all pairwise matchups"""
        print("\n" + "=" * 70)
        print("     TRUESKILL ROUND-ROBIN TOURNAMENT")
        print(f"     Snakes: {', '.join([s['name'] for s in self.snakes])}")
        print(f"     Games per matchup: {self.iterations}")
        print("=" * 70 + "\n")

        # Generate all pairwise matchups
        matchups = []
        for i in range(len(self.snakes)):
            for j in range(i + 1, len(self.snakes)):
                matchups.append((self.snakes[i], self.snakes[j]))

        print(f"Running {len(matchups)} matchups...\n")

        # Run each matchup
        for idx, (snake1, snake2) in enumerate(matchups, 1):
            print(f"\n{'='*70}")
            print(f"Matchup {idx}/{len(matchups)}: {snake1['name']} vs {snake2['name']}")
            print(f"{'='*70}")

            # Create game config
            game_config = GameConfig(
                round_robin=self.round_robin,
                p1_name=snake1["name"],
                p1_base_port=snake1["port"],
                p2_name=snake2["name"],
                p2_base_port=snake2["port"],
            )

            # Run benchmark
            benchmark = BenchmarkRunner(
                iterations=self.iterations, game_config=game_config, num_workers=self.workers
            )
            benchmark.run_multiple_games()

            # Store results
            matchup_key = f"{snake1['name']}_vs_{snake2['name']}"
            self.matchup_results[matchup_key] = {
                "snake1": snake1["name"],
                "snake2": snake2["name"],
                "snake1_wins": benchmark.results["p1_wins"],
                "snake2_wins": benchmark.results["p2_wins"],
                "draws": benchmark.results["draws"],
            }

        # Calculate TrueSkill ratings from all games
        self._calculate_trueskill_from_games()

        # Print final rankings
        self._print_final_rankings()

    def _calculate_trueskill_from_games(self):
        """Calculate TrueSkill ratings by processing individual games in sequence"""
        print("\n" + "=" * 70)
        print("     CALCULATING TRUESKILL RATINGS FROM GAME SEQUENCE")
        print("=" * 70 + "\n")

        # Reset ratings
        self.ratings = {snake["name"]: Rating() for snake in self.snakes}

        # Collect all game results from all matchups
        all_games = []
        tournament_dir = Path(self.output_dir)

        for matchup_dir in tournament_dir.iterdir():
            if matchup_dir.is_dir():
                games_dir = matchup_dir / "games"
                if games_dir.exists():
                    # Parse matchup name to get snake names
                    matchup_name = matchup_dir.name
                    if "_vs_" in matchup_name:
                        snake1_name, snake2_name = matchup_name.split("_vs_")

                        # Read all game files
                        for game_file in sorted(games_dir.glob("game_*.json")):
                            try:
                                winner = self._parse_game_winner(
                                    game_file, snake1_name, snake2_name
                                )
                                all_games.append(
                                    {
                                        "snake1": snake1_name,
                                        "snake2": snake2_name,
                                        "winner": winner,
                                        "file": str(game_file),
                                    }
                                )
                            except Exception as e:
                                print(f"Warning: Could not parse {game_file}: {e}")

        print(f"Found {len(all_games)} total games across all matchups")

        # Shuffle games to avoid order bias
        # Use a fixed seed for reproducibility
        random.seed(42)
        random.shuffle(all_games)

        print("Processing games in randomized order to calculate TrueSkill...")

        # Update TrueSkill for each game in sequence
        for game in all_games:
            snake1 = game["snake1"]
            snake2 = game["snake2"]
            winner = game["winner"]

            if winner == snake1:
                # Snake1 wins
                self.ratings[snake1], self.ratings[snake2] = rate_1vs1(
                    self.ratings[snake1], self.ratings[snake2]
                )
            elif winner == snake2:
                # Snake2 wins
                self.ratings[snake2], self.ratings[snake1] = rate_1vs1(
                    self.ratings[snake2], self.ratings[snake1]
                )
            elif winner == "draw":
                # Draw
                self.ratings[snake1], self.ratings[snake2] = rate_1vs1(
                    self.ratings[snake1], self.ratings[snake2], drawn=True
                )

        print("[OK] TrueSkill ratings calculated\n")

    def _parse_game_winner(self, game_file, snake1_name, snake2_name):
        """Parse a game file to determine the winner"""
        with open(game_file, "r") as f:
            lines = f.readlines()
            if not lines:
                return None

            # Parse the last line (final state)
            final_state = json.loads(lines[-1])

            # Check if it's a draw
            if final_state.get("isDraw", False):
                return "draw"

            # Get winner name
            winner_name = final_state.get("winnerName")

            if winner_name == snake1_name:
                return snake1_name
            elif winner_name == snake2_name:
                return snake2_name
            else:
                # Check which snakes are still alive
                snakes = final_state.get("board", {}).get("snakes", [])
                alive_snakes = [s for s in snakes if s.get("health", 0) > 0]

                if len(alive_snakes) == 1:
                    return alive_snakes[0].get("name")
                elif len(alive_snakes) == 0:
                    return "draw"
                else:
                    # Multiple survivors = draw
                    return "draw"

    def _print_final_rankings(self):
        """Print final TrueSkill rankings and save to file"""
        print("\n" + "=" * 70)
        print("     FINAL TRUESKILL RANKINGS")
        print("=" * 70 + "\n")

        # Sort by TrueSkill rating (mu - 3*sigma for conservative estimate)
        ranked = sorted(self.ratings.items(), key=lambda x: x[1].mu - 3 * x[1].sigma, reverse=True)

        results = []
        for rank, (snake_name, rating) in enumerate(ranked, 1):
            conservative_skill = rating.mu - 3 * rating.sigma
            print(f"{rank}. {snake_name}")
            print(f"   mu (mean): {rating.mu:.2f}")
            print(f"   sigma (uncertainty): {rating.sigma:.2f}")
            print(f"   Conservative skill: {conservative_skill:.2f}")
            print()

            results.append(
                {
                    "rank": rank,
                    "name": snake_name,
                    "mu": rating.mu,
                    "sigma": rating.sigma,
                    "conservative_skill": conservative_skill,
                }
            )

        # Save results to JSON
        output = {
            "timestamp": datetime.now().isoformat(),
            "iterations_per_matchup": self.iterations,
            "total_games": sum(
                r["snake1_wins"] + r["snake2_wins"] + r["draws"]
                for r in self.matchup_results.values()
            ),
            "rankings": results,
            "matchup_results": self.matchup_results,
        }

        output_file = f"{self.output_dir}/trueskill_results.json"
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)

        print(f"Results saved to: {output_file}")
        print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run TrueSkill round-robin tournament")
    parser.add_argument(
        "--snakes",
        type=str,
        required=True,
        help="Comma-separated list of snake_name:port (e.g., snake1:7123,snake2:7124)",
    )
    parser.add_argument("--iterations", type=int, default=100, help="Number of games per matchup")
    parser.add_argument("--workers", type=int, default=8, help="Number of parallel workers")
    parser.add_argument(
        "--tournament-id",
        type=str,
        default=None,
        help="Optional tournament ID (default: auto-generated)",
    )

    args = parser.parse_args()

    # Parse snakes
    snakes = []
    for snake_str in args.snakes.split(","):
        name, port = snake_str.strip().split(":")
        snakes.append({"name": name, "port": int(port)})

    if len(snakes) < 2:
        print("Error: Need at least 2 snakes for a tournament")
        return

    # Run tournament with optional ID
    tournament = TrueSkillTournament(
        snakes, args.iterations, args.workers, tournament_id=args.tournament_id
    )
    tournament.run_tournament()


if __name__ == "__main__":
    main()
