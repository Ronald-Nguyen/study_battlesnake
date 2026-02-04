from collections import defaultdict
import subprocess
import os
from eval.config import GameConfig
import argparse
import json
import sympy
import sys
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from threading import Lock
from tqdm import tqdm
from eval.go_utils import check_and_build_rules_cli


class BenchmarkRunner:
    def __init__(self, iterations: int = 500, game_config: GameConfig = None, num_workers: int = 4):
        if not check_and_build_rules_cli():
            raise RuntimeError(
                "Battlesnake CLI is not available and could not be built, please read the "
                "set-up instructions in the README.md! Install Go, and run `make build` in "
                "the rules directory."
            )
        self.iterations = iterations
        self.game_config = game_config
        self.num_workers = num_workers
        self.results = defaultdict(int)
        self.results_lock = Lock()
        if len(game_config.round_robin) > 0:
            self.output_dir = (
                f"tournaments/{game_config.round_robin}/"
                f"{game_config.p1_name}_vs_{game_config.p2_name}"
            )
        else:
            self.output_dir = f"tournaments/{game_config.p1_name}_vs_{game_config.p2_name}"  # noqa: E501
        os.makedirs(self.output_dir, exist_ok=True)

        # Setup loggers
        self.summary_logger = self._setup_summary_logger()
        self.error_logger = self._setup_error_logger()

    def _setup_summary_logger(self):
        """Configure logger for summary and progress messages"""
        logger = logging.getLogger("BenchmarkRunner.Summary")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        formatter = logging.Formatter("%(message)s")

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Summary file handler
        summary_file = f"{self.output_dir}/summary.log"
        file_handler = logging.FileHandler(summary_file, mode="w")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.propagate = False
        return logger

    def _setup_error_logger(self):
        """Configure logger for error and warning messages"""
        logger = logging.getLogger("BenchmarkRunner.Error")
        logger.setLevel(logging.WARNING)
        logger.handlers.clear()

        # Formatter with more details for errors
        formatter = logging.Formatter("[%(levelname)s] %(message)s")

        # Console handler
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Error file handler
        error_file = f"{self.output_dir}/error.log"
        file_handler = logging.FileHandler(error_file, mode="w")
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.propagate = False
        return logger

    def run_multiple_games(self):
        """Run multiple games in parallel with real-time progress tracking"""
        # Print header
        self.summary_logger.info("\n" + "=" * 60)
        self.summary_logger.info("     BATTLESNAKE BENCHMARK RESULTS")
        self.summary_logger.info(
            f"     Running {self.iterations} games with {self.num_workers} parallel workers"
        )
        self.summary_logger.info("     Config:")
        self.summary_logger.info(f"         - Width: {self.game_config.width}")
        self.summary_logger.info(f"         - Height: {self.game_config.height}")
        self.summary_logger.info(f"         - P1 Name: {self.game_config.p1_name}")
        self.summary_logger.info(f"         - P1 Port: {self.game_config.p1_base_port}")
        self.summary_logger.info(f"         - P2 Name: {self.game_config.p2_name}")
        self.summary_logger.info(f"         - P2 Port: {self.game_config.p2_base_port}")
        self.summary_logger.info("         - Using external servers (Docker/manual)")
        self.summary_logger.info("=" * 60 + "\n")

        # Generate all game parameters
        game_params = []
        last_prime = 100
        for i in range(self.iterations):
            next_prime = sympy.nextprime(last_prime)
            game_params.append((i, str(next_prime)))
            last_prime = next_prime

        # Run games in parallel with tqdm progress bar
        with ProcessPoolExecutor(max_workers=self.num_workers) as executor:

            # Submit all games individually
            future_to_game = {
                executor.submit(
                    run_single_game_worker,
                    game_num=game_num,
                    seed=seed,
                    output_dir=self.output_dir,
                    game_config=self.game_config,
                ): (game_num, seed)
                for idx, (game_num, seed) in enumerate(game_params)
            }

            # Process completed games with tqdm progress bar
            bar_fmt = (
                "{l_bar}{bar}| {n_fmt}/{total_fmt} "
                "[{elapsed}<{remaining}, {rate_fmt}] {postfix}"
            )
            with tqdm(
                total=self.iterations,
                desc="Running games",
                unit="game",
                bar_format=bar_fmt,
            ) as pbar:
                for future in as_completed(future_to_game):
                    game_num, seed = future_to_game[future]
                    try:
                        result = future.result()

                        # Update results
                        if result:
                            with self.results_lock:
                                if result == "draw":
                                    self.results["draws"] += 1
                                elif result == "p1":
                                    self.results["p1_wins"] += 1
                                elif result == "p2":
                                    self.results["p2_wins"] += 1

                        # Update progress bar with current stats
                        pbar.set_postfix(
                            {
                                "P1": self.results["p1_wins"],
                                "P2": self.results["p2_wins"],
                                "Draws": self.results["draws"],
                            },
                            refresh=True,
                        )
                        pbar.update(1)

                    except Exception as e:
                        self.error_logger.error(f"Game {game_num} failed with exception: {e}")
                        pbar.update(1)

        # Print final summary
        print()  # Newline after progress bar
        self.summary_logger.info("=" * 60)
        self.summary_logger.info("     Summary:")
        self.summary_logger.info(f"         - Total Games: {self.iterations}")
        self.summary_logger.info(f"         - P1 Wins: {self.results['p1_wins']}")
        self.summary_logger.info(f"         - P2 Wins: {self.results['p2_wins']}")
        self.summary_logger.info(f"         - Draws: {self.results['draws']}")

        # Determine winner
        if self.results["p1_wins"] > self.results["p2_wins"]:
            winner = self.game_config.p1_name
        elif self.results["p2_wins"] > self.results["p1_wins"]:
            winner = self.game_config.p2_name
        else:
            winner = "Draw"

        self.summary_logger.info(f"         - Final Winner: {winner}")
        self.summary_logger.info("=" * 60)


def run_single_game_worker(game_num, seed, output_dir, game_config):
    """
    Run a single game using external snake servers (Docker or otherwise).
    Assumes servers are already running at the configured ports.
    """
    try:
        games_dir = f"{output_dir}/games"
        os.makedirs(games_dir, exist_ok=True)
        output_file = f"{games_dir}/game_{game_num}.json"

        # Run the game against external servers
        cmd = [
            "rules/battlesnake",
            "play",
            "-W",
            str(game_config.width),
            "-H",
            str(game_config.height),
            "-n",
            game_config.p1_name,
            "-u",
            f"http://localhost:{game_config.p1_base_port}",
            "-n",
            game_config.p2_name,
            "-u",
            f"http://localhost:{game_config.p2_base_port}",
            "-r",
            str(seed),
            "-o",
            output_file,
            "--timeout",
            "10000",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Check for errors
        if result.returncode != 0:
            # Determine which snake failed and award win to opponent
            stderr = result.stderr.lower()

            # Check if error mentions either snake's port
            p1_port_str = str(game_config.p1_base_port)
            p2_port_str = str(game_config.p2_base_port)
            stderr_lines = stderr.split("\n")

            if p1_port_str in stderr_lines[-1]:
                # Player 1 failed, player 2 wins
                print(
                    f"Game {game_num}: {game_config.p1_name} failed/timed out, "
                    f"awarding win to {game_config.p2_name}"
                )
                return "p2"
            elif p2_port_str in stderr_lines[-1]:
                # Player 2 failed, player 1 wins
                print(
                    f"Game {game_num}: {game_config.p2_name} failed/timed out, "
                    f"awarding win to {game_config.p1_name}"
                )
                return "p1"
            else:
                # Can't determine who failed, return None (skip game)
                print(f"Game {game_num}: Unknown error, skipping game")
                with open(f"{games_dir}/game_{game_num}_error.txt", "w") as f:
                    f.write(f"Unknown error: {stderr}\n")
                return None

        # Parse result from successful game
        if os.path.exists(output_file):
            with open(output_file, "r") as f:
                lines = f.readlines()
                if not lines:
                    # Empty file - treat as unknown error
                    with open(f"{games_dir}/game_{game_num}_error.txt", "w") as f:
                        f.write("Output file is empty\n")
                    return None

                final_state = json.loads(lines[-1])

                if final_state["isDraw"]:
                    return "draw"
                elif final_state.get("winnerName") == game_config.p1_name:
                    return "p1"
                elif final_state.get("winnerName") == game_config.p2_name:
                    return "p2"
        else:
            # Output file doesn't exist - unknown error
            with open(f"{games_dir}/game_{game_num}_error.txt", "w") as f:
                f.write("Output file not created\n")
                f.write(f"STDOUT:\n{result.stdout}\n")
                f.write(f"STDERR:\n{result.stderr}\n")
            return None

        return None

    except Exception as e:
        # Write exception to debug file
        with open(f"{games_dir}/game_{game_num}_error.txt", "w") as f:
            f.write(f"Exception: {e}\n")
            import traceback

            f.write(traceback.format_exc())
        return None


def main():
    parser = argparse.ArgumentParser(description="Battlesnake Benchmark")
    parser.add_argument("--iterations", type=int, default=1000, help="Number of games to run")
    parser.add_argument("--workers", type=int, default=8, help="Number of parallel workers")
    parser.add_argument("--port_1", type=int, default=7123, help="Port for the first snake")
    parser.add_argument("--port_2", type=int, default=7124, help="Port for the second snake")
    args = parser.parse_args()

    game_config = GameConfig(
        p1_base_port=args.port_1,
        p2_base_port=args.port_2,
    )
    benchmark_runner = BenchmarkRunner(
        iterations=args.iterations, game_config=game_config, num_workers=args.workers
    )
    benchmark_runner.run_multiple_games()


if __name__ == "__main__":
    main()
