# Welcome to
# __________         __    __  .__                               __
# \______   \_____ _/  |__/  |_|  |   ____   ______ ____ _____  |  | __ ____
#  |    |  _/\__  \\   __\   __\  | _/ __ \ /  ___//    \\__  \ |  |/ // __ \
#  |    |   \ / __ \|  |  |  | |  |_\  ___/ \___ \|   |  \/ __ \|    <\  ___/
#  |________/(______/__|  |__| |____/\_____>______>___|__(______/__|__\\_____>
#
# STRATEGY: Defensive Space-Control Snake
# - Uses flood fill to calculate available space in each direction
# - Prioritizes moves that maximize available space
# - Only seeks food when health is critically low
# - Avoids risky situations and corners

import typing
from collections import deque


def info() -> typing.Dict:
    print("INFO")
    return {
        "apiversion": "1",
        "author": "DefensiveGuardian",
        "color": "#4444FF",  # Defensive blue color
        "head": "shades",
        "tail": "round-bum",
    }


def start(game_state: typing.Dict):
    print("GAME START - Defensive Guardian")


def end(game_state: typing.Dict):
    print("GAME OVER\n")


def get_next_position(head: typing.Dict, direction: str) -> typing.Dict:
    """Calculate the next position given a head position and direction."""
    x, y = head["x"], head["y"]
    if direction == "up":
        return {"x": x, "y": y + 1}
    elif direction == "down":
        return {"x": x, "y": y - 1}
    elif direction == "left":
        return {"x": x - 1, "y": y}
    elif direction == "right":
        return {"x": x + 1, "y": y}
    return head


def is_out_of_bounds(pos: typing.Dict, board_width: int, board_height: int) -> bool:
    """Check if a position is out of bounds."""
    return pos["x"] < 0 or pos["x"] >= board_width or pos["y"] < 0 or pos["y"] >= board_height


def is_occupied(pos: typing.Dict, snakes: list) -> bool:
    """Check if a position is occupied by any snake body."""
    for snake in snakes:
        # Exclude tail since it will move (unless snake just ate, but we'll be conservative)
        body_to_check = snake["body"][:-1] if len(snake["body"]) > 1 else snake["body"]
        for segment in body_to_check:
            if pos["x"] == segment["x"] and pos["y"] == segment["y"]:
                return True
    return False


def flood_fill(
    start_pos: typing.Dict, board_width: int, board_height: int, snakes: list, max_depth: int = 100
) -> int:
    """
    Use flood fill (BFS) to calculate available space from a starting position.
    Returns the number of reachable squares.
    """
    visited = set()
    queue = deque([start_pos])
    visited.add((start_pos["x"], start_pos["y"]))
    count = 0

    while queue and count < max_depth:
        pos = queue.popleft()
        count += 1

        # Check all four directions
        for direction in ["up", "down", "left", "right"]:
            next_pos = get_next_position(pos, direction)
            pos_tuple = (next_pos["x"], next_pos["y"])

            # Skip if already visited
            if pos_tuple in visited:
                continue

            # Skip if out of bounds
            if is_out_of_bounds(next_pos, board_width, board_height):
                continue

            # Skip if occupied by snake
            if is_occupied(next_pos, snakes):
                continue

            visited.add(pos_tuple)
            queue.append(next_pos)

    return count


def manhattan_distance(pos1: typing.Dict, pos2: typing.Dict) -> int:
    """Calculate Manhattan distance between two positions."""
    return abs(pos1["x"] - pos2["x"]) + abs(pos1["y"] - pos2["y"])


def get_nearest_food(head: typing.Dict, food_list: list) -> typing.Dict:
    """Find the nearest food to the snake's head."""
    if not food_list:
        return None
    return min(food_list, key=lambda food: manhattan_distance(head, food))


def is_head_to_head_risky(pos: typing.Dict, my_length: int, opponents: list) -> bool:
    """Check if a position is risky due to nearby opponent heads."""
    for opponent in opponents:
        opponent_head = opponent["body"][0]
        opponent_length = len(opponent["body"])

        # If opponent is larger or equal and head is adjacent to our potential position
        if opponent_length >= my_length and manhattan_distance(pos, opponent_head) <= 1:
            return True
    return False


def move(game_state: typing.Dict) -> typing.Dict:
    my_head = game_state["you"]["body"][0]
    my_body = game_state["you"]["body"]
    my_length = len(my_body)
    my_health = game_state["you"]["health"]

    board_width = game_state["board"]["width"]
    board_height = game_state["board"]["height"]
    food = game_state["board"]["food"]
    all_snakes = game_state["board"]["snakes"]

    # Get opponent snakes (exclude ourselves)
    opponents = [s for s in all_snakes if s["id"] != game_state["you"]["id"]]

    # Evaluate all possible moves
    moves = ["up", "down", "left", "right"]
    move_scores = {}
    move_spaces = {}

    for direction in moves:
        next_pos = get_next_position(my_head, direction)
        score = 100  # Start with base score

        # Check if move is safe

        # Avoid out of bounds
        if is_out_of_bounds(next_pos, board_width, board_height):
            score = -1000
            move_spaces[direction] = 0
            move_scores[direction] = score
            continue

        # Avoid colliding with any snake (including ourselves)
        if is_occupied(next_pos, all_snakes):
            score = -1000
            move_spaces[direction] = 0
            move_scores[direction] = score
            continue

        # Avoid head-to-head collisions with larger or equal opponents
        if is_head_to_head_risky(next_pos, my_length, opponents):
            score -= 300  # Penalize but don't eliminate

        # Calculate available space using flood fill (most important metric)
        available_space = flood_fill(next_pos, board_width, board_height, all_snakes)
        move_spaces[direction] = available_space

        # Space is the primary factor
        score += available_space * 10

        # If health is critically low, prioritize food
        if my_health < 20:
            nearest_food = get_nearest_food(my_head, food)
            if nearest_food:
                current_distance = manhattan_distance(my_head, nearest_food)
                new_distance = manhattan_distance(next_pos, nearest_food)

                if new_distance < current_distance:
                    score += 500  # Strong incentive to get food when health is low
                elif new_distance > current_distance:
                    score -= 200

        # If health is moderately low, consider food but don't prioritize it
        elif my_health < 50 and food:
            nearest_food = get_nearest_food(my_head, food)
            if nearest_food:
                current_distance = manhattan_distance(my_head, nearest_food)
                new_distance = manhattan_distance(next_pos, nearest_food)

                if new_distance < current_distance:
                    score += 50

        # Avoid edges when possible (give us more options)
        edge_penalty = 0
        if next_pos["x"] == 0 or next_pos["x"] == board_width - 1:
            edge_penalty += 20
        if next_pos["y"] == 0 or next_pos["y"] == board_height - 1:
            edge_penalty += 20
        score -= edge_penalty

        move_scores[direction] = score

    # Choose the best move based on score
    best_moves = [m for m in moves if move_scores[m] > 0]

    if not best_moves:
        # No good moves, pick the least bad one
        print(f"MOVE {game_state['turn']}: No ideal moves! Picking least bad option")
        next_move = max(moves, key=lambda m: move_scores[m])
    else:
        # Choose the move with the highest score
        next_move = max(best_moves, key=lambda m: move_scores[m])

    print(
        f"MOVE {game_state['turn']}: {next_move} (score: {move_scores[next_move]}, "
        f"space: {move_spaces[next_move]}, health: {my_health})"
    )
    return {"move": next_move}


# Start server when `python main.py` is run
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})
