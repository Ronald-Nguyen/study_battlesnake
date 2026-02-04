# Welcome to
# __________         __    __  .__                               __
# \______   \_____ _/  |__/  |_|  |   ____   ______ ____ _____  |  | __ ____
#  |    |  _/\__  \\   __\   __\  | _/ __ \ /  ___//    \\__  \ |  |/ // __ \
#  |    |   \ / __ \|  |  |  | |  |_\  ___/ \___ \|   |  \/ __ \|    <\  ___/
#  |________/(______/__|  |__| |____/\_____>______>___|__(______/__|__\\_____>
#

import random
import typing
from collections import deque

# ============================================================================
# STRATEGY CONFIGURATION
# ============================================================================

# Note: These are default values, will be dynamically adjusted by functions
AGGRESSIVE_LENGTH_THRESHOLD = 8  # Aggressive mode threshold (will be dynamically adjusted)
LOW_HEALTH_THRESHOLD = 30  # Food seeking threshold
CRITICAL_HEALTH_THRESHOLD = 15  # Critical threshold
HUNT_REWARD_THRESHOLD = 3  # Hunt reward threshold


# ============================================================================
# API FUNCTIONS
# ============================================================================

def info() -> typing.Dict:
    print("INFO")
    return {
        "apiversion": "1",
        "author": "miikkee",
        "color": "#7C3AED",
        "head": "shades",
        "tail": "sharp",
    }


def start(game_state: typing.Dict):
    print("GAME START")


def end(game_state: typing.Dict):
    print("GAME OVER\n")


def move(game_state: typing.Dict) -> typing.Dict:
    """Core movement logic - fully enhanced version"""

    my_head = game_state["you"]["body"][0]
    my_body = game_state["you"]["body"]
    my_length = len(my_body)
    my_health = game_state["you"]["health"]
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    food = game_state['board']['food']
    all_snakes = game_state['board']['snakes']

    opponents = [snake for snake in all_snakes if snake['id'] != game_state['you']['id']]

    possible_moves = ["up", "down", "left", "right"]
    move_scores = {move: 0 for move in possible_moves}

    # Layer 1: Basic safety
    safe_moves_mask = _evaluate_basic_safety(
        my_head, my_body, opponents,
        board_width, board_height,
        move_scores, possible_moves
    )

    # Layer 2: Space evaluation (using dynamic depth flood fill)
    _evaluate_space_availability(
        my_head, my_body, my_length, opponents,
        board_width, board_height,
        move_scores, possible_moves, safe_moves_mask,
        game_state
    )

    # Patch 5: Dynamically calculate aggressive threshold
    dynamic_threshold = _calculate_dynamic_aggressive_threshold(game_state)

    is_aggressive = my_length >= dynamic_threshold and my_health > LOW_HEALTH_THRESHOLD
    is_critical = my_health < CRITICAL_HEALTH_THRESHOLD
    need_food = my_health < LOW_HEALTH_THRESHOLD

    # Emergency mode (enhanced version, considers third-party threats)
    if is_critical and opponents:
        _evaluate_emergency_strategy_enhanced(
            my_head, my_body, my_length, my_health,
            food, opponents, board_width, board_height,
            move_scores, possible_moves, safe_moves_mask,
            game_state
        )

    # Normal food seeking (smart food selection)
    elif food and (need_food or not is_aggressive):
        _evaluate_food_seeking_smart(
            my_head, food, move_scores,
            possible_moves, safe_moves_mask,
            is_critical, need_food,
            game_state
        )

    # Aggressive strategy
    if is_aggressive and opponents:
        _evaluate_aggressive_strategy(
            my_head, my_length, opponents,
            move_scores, possible_moves, safe_moves_mask
        )

    # Head-to-head defense (2-step prediction)
    if opponents:
        _evaluate_head_to_head_defense_enhanced(
            my_head, my_length, opponents,
            board_width, board_height,
            move_scores, possible_moves, safe_moves_mask
        )

    # Position preference
    _evaluate_position_preference(
        my_head, board_width, board_height,
        move_scores, possible_moves, safe_moves_mask
    )

    # Select best move
    safe_moves = [m for m in possible_moves if safe_moves_mask[m] and move_scores[m] > -9000]

    if not safe_moves:
        next_move = max(possible_moves, key=lambda m: move_scores[m])
        print(f"MOVE {game_state['turn']}: {next_move} (NO SAFE MOVES!)")
    else:
        next_move = max(safe_moves, key=lambda m: move_scores[m])
        mode = "CRITICAL" if is_critical else ("AGGRESSIVE" if is_aggressive else "SURVIVAL")
        print(f"MOVE {game_state['turn']}: {next_move} | {mode} | Threshold={dynamic_threshold}")

    return {"move": next_move}


# ============================================================================
# Patch 5: Dynamic Aggressive Threshold Calculation
# ============================================================================

def _calculate_dynamic_aggressive_threshold(game_state: typing.Dict) -> int:
    """
    Dynamically calculate aggressive threshold based on current game state

    Patch 5 - Solves the problem of fixed thresholds being easily predictable
    """
    my_length = len(game_state['you']['body'])
    opponents = [s for s in game_state['board']['snakes']
                 if s['id'] != game_state['you']['id']]

    if not opponents:
        return 6  # No opponents, can be aggressive

    # Calculate average opponent length
    avg_opponent_length = sum(len(s['body']) for s in opponents) / len(opponents)

    # Calculate strongest opponent length
    max_opponent_length = max(len(s['body']) for s in opponents)

    # Strategy 1: If opponents are generally much stronger, be conservative
    if avg_opponent_length > my_length + 3:
        return 10

    # Strategy 2: If strongest opponent is much stronger, be conservative
    if max_opponent_length > my_length + 4:
        return 11

    # Strategy 3: If opponents are generally weaker, be aggressive
    if avg_opponent_length < my_length - 2:
        return 6

    # Strategy 4: Many opponents, be conservative
    if len(opponents) >= 4:
        return 9

    # Strategy 5: Few opponents, can be somewhat aggressive
    if len(opponents) <= 2:
        return 7

    # Default
    return 8


# ============================================================================
# EVALUATION LAYERS
# ============================================================================

def _evaluate_basic_safety(
        my_head, my_body, opponents, board_width, board_height, move_scores, possible_moves
):
    """Layer 1: Basic safety"""
    safe_mask = {move: True for move in possible_moves}
    my_neck = my_body[1] if len(my_body) > 1 else None

    for move in possible_moves:
        next_pos = _get_next_position(my_head, move)

        if my_neck and next_pos['x'] == my_neck['x'] and next_pos['y'] == my_neck['y']:
            move_scores[move] -= 10000
            safe_mask[move] = False
            continue

        if not _is_in_bounds(next_pos, board_width, board_height):
            move_scores[move] -= 10000
            safe_mask[move] = False
            continue

        if _is_collision_with_body(next_pos, my_body[:-1]):
            move_scores[move] -= 10000
            safe_mask[move] = False
            continue

        if _is_collision_with_opponents(next_pos, opponents, exclude_tails=True):
            move_scores[move] -= 10000
            safe_mask[move] = False
            continue

    return safe_mask


def _evaluate_space_availability(
        my_head, my_body, my_length, opponents, board_width, board_height,
        move_scores, possible_moves, safe_mask, game_state
):
    """
    Layer 2: Space evaluation
    Patch 1 - Use dynamic depth flood fill
    """
    for move in possible_moves:
        if not safe_mask[move]:
            continue

        next_pos = _get_next_position(my_head, move)
        available_space = _flood_fill_dynamic(next_pos, game_state)

        move_scores[move] += available_space * 10

        if available_space < my_length:
            penalty = (my_length - available_space) * 50
            move_scores[move] -= penalty

            if available_space < my_length // 2:
                move_scores[move] -= 200


def _evaluate_emergency_strategy_enhanced(
        my_head, my_body, my_length, my_health, food, opponents,
        board_width, board_height, move_scores, possible_moves, safe_mask, game_state
):
    """
    Emergency strategy (enhanced version)
    Patch 2 - Consider third-party threats and path safety
    """
    best_food_option = None
    best_hunt_option = None

    # Evaluate food options
    if food:
        closest_food = min(food, key=lambda f: _manhattan_distance(my_head, f))
        food_distance = _manhattan_distance(my_head, closest_food)

        if food_distance < my_health:
            best_food_option = {
                'target': closest_food,
                'distance': food_distance,
                'score': 500 / (food_distance + 1)
            }

    # Evaluate hunt options (enhanced version)
    for opponent in opponents:
        opponent_length = len(opponent['body'])
        opponent_head = opponent['body'][0]

        if opponent_length >= my_length:
            continue

        distance_to_opponent = _manhattan_distance(my_head, opponent_head)

        if distance_to_opponent >= my_health - 5:
            continue

        potential_food_gain = opponent_length

        # New: Check third-party threats
        third_party_threat = 0
        for other_opponent in opponents:
            if other_opponent['id'] == opponent['id']:
                continue

            other_length = len(other_opponent['body'])
            other_head = other_opponent['body'][0]

            if other_length >= my_length:
                distance_to_other = _manhattan_distance(opponent_head, other_head)

                if distance_to_other <= 5:
                    third_party_threat += 200 / (distance_to_other + 1)

        # New: Evaluate chase path safety
        temp_game_state = game_state.copy()
        temp_game_state['you'] = {
            'id': game_state['you']['id'],
            'body': [opponent_head] + game_state['you']['body'][:-1],
            'health': game_state['you']['health']
        }
        chase_space = _flood_fill_dynamic(opponent_head, temp_game_state)
        chase_path_safe = chase_space >= my_length

        # Comprehensive score (includes new risk factors)
        hunt_score = (
                potential_food_gain * 50
                - distance_to_opponent * 10
                - third_party_threat
                - (0 if chase_path_safe else 150)
                - 100
        )

        # Increase reward threshold (more conservative)
        if hunt_score > 50 and potential_food_gain >= HUNT_REWARD_THRESHOLD:
            if best_hunt_option is None or hunt_score > best_hunt_option['score']:
                best_hunt_option = {
                    'target': opponent_head,
                    'distance': distance_to_opponent,
                    'score': hunt_score,
                    'third_party_risk': third_party_threat,
                    'path_safe': chase_path_safe
                }

    # Decision (stricter conditions)
    if best_hunt_option and best_food_option:
        # Hunt must be significantly better than food seeking, and path must be safe
        if (best_hunt_option['score'] > best_food_option['score'] * 2.0 and
                best_hunt_option['path_safe'] and
                best_hunt_option['third_party_risk'] < 100):

            _apply_hunting_strategy(my_head, best_hunt_option, move_scores, possible_moves, safe_mask)
            print(
                f"EMERGENCY: HUNTING (score={best_hunt_option['score']:.0f}, risk={best_hunt_option['third_party_risk']:.0f})")
        else:
            _apply_food_seeking(my_head, best_food_option['target'], move_scores, possible_moves, safe_mask, 500)
            print(f"EMERGENCY: FOOD (hunt too risky)")

    elif best_hunt_option:
        _apply_hunting_strategy(my_head, best_hunt_option, move_scores, possible_moves, safe_mask)
        print(f"EMERGENCY: HUNTING (no food)")

    elif best_food_option:
        _apply_food_seeking(my_head, best_food_option['target'], move_scores, possible_moves, safe_mask, 500)
        print(f"EMERGENCY: FOOD")


def _apply_hunting_strategy(my_head, hunt_option, move_scores, possible_moves, safe_mask):
    """Apply hunting strategy"""
    target = hunt_option['target']

    for move in possible_moves:
        if not safe_mask[move]:
            continue

        next_pos = _get_next_position(my_head, move)
        distance = _manhattan_distance(next_pos, target)
        move_scores[move] += hunt_option['score'] / (distance + 1)


def _apply_food_seeking(my_head, target_food, move_scores, possible_moves, safe_mask, weight):
    """Apply food seeking strategy"""
    for move in possible_moves:
        if not safe_mask[move]:
            continue

        next_pos = _get_next_position(my_head, move)
        distance = _manhattan_distance(next_pos, target_food)
        move_scores[move] += weight / (distance + 1)


def _evaluate_food_seeking_smart(
        my_head, food, move_scores, possible_moves, safe_mask,
        is_critical, need_food, game_state
):
    """
    Smart food selection (Patch 4)
    Comprehensively considers distance, space, and threats
    """
    my_length = len(game_state['you']['body'])
    opponents = [s for s in game_state['board']['snakes'] if s['id'] != game_state['you']['id']]

    food_evaluations = []

    for f in food:
        distance = _manhattan_distance(my_head, f)
        distance_score = 100.0 / (distance + 1)

        space = _estimate_space_after_reaching(f, game_state)
        space_score = space * 2.0

        threat = _count_threats_near(f, opponents, my_length, my_head)
        threat_score = -threat

        total_score = distance_score + space_score + threat_score
        food_evaluations.append((f, total_score))

    best_food = max(food_evaluations, key=lambda x: x[1])[0]

    if is_critical:
        food_weight = 200
    elif need_food:
        food_weight = 100
    else:
        food_weight = 30

    for move in possible_moves:
        if not safe_mask[move]:
            continue

        next_pos = _get_next_position(my_head, move)
        distance_to_best = _manhattan_distance(next_pos, best_food)
        move_scores[move] += food_weight / (distance_to_best + 1)


def _evaluate_aggressive_strategy(my_head, my_length, opponents, move_scores, possible_moves, safe_mask):
    """Aggressive strategy"""
    for opponent in opponents:
        opponent_head = opponent['body'][0]
        opponent_length = len(opponent['body'])

        if opponent_length < my_length:
            for move in possible_moves:
                if not safe_mask[move]:
                    continue

                next_pos = _get_next_position(my_head, move)
                distance = _manhattan_distance(next_pos, opponent_head)
                move_scores[move] += 50 / (distance + 1)

        elif opponent_length >= my_length:
            for move in possible_moves:
                if not safe_mask[move]:
                    continue

                next_pos = _get_next_position(my_head, move)
                distance = _manhattan_distance(next_pos, opponent_head)

                if distance <= 2:
                    move_scores[move] -= 100 / (distance + 1)


def _evaluate_head_to_head_defense_enhanced(
        my_head, my_length, opponents, board_width, board_height,
        move_scores, possible_moves, safe_mask
):
    """
    Head-to-head defense (enhanced version)
    Patch 3 - Use 2-step prediction
    """
    for opponent in opponents:
        opponent_head = opponent['body'][0]
        opponent_length = len(opponent['body'])

        if opponent_length >= my_length:
            # Use 2-step prediction
            predicted_positions = _predict_opponent_next_moves(
                opponent, board_width, board_height, depth=2
            )

            for move in possible_moves:
                if not safe_mask[move]:
                    continue

                next_pos = _get_next_position(my_head, move)

                for pred_pos in predicted_positions:
                    if _positions_equal(next_pos, pred_pos):
                        distance = _manhattan_distance(next_pos, opponent_head)

                        if distance <= 1:
                            penalty = 400 + (opponent_length - my_length) * 50
                        else:
                            penalty = 200 + (opponent_length - my_length) * 30

                        move_scores[move] -= penalty
                        break


def _evaluate_position_preference(my_head, board_width, board_height, move_scores, possible_moves, safe_mask):
    """Position preference"""
    center_x = board_width / 2
    center_y = board_height / 2

    for move in possible_moves:
        if not safe_mask[move]:
            continue

        next_pos = _get_next_position(my_head, move)
        distance_to_center = abs(next_pos['x'] - center_x) + abs(next_pos['y'] - center_y)
        move_scores[move] += 5 / (distance_to_center + 1)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _get_next_position(position, move):
    x, y = position['x'], position['y']
    if move == "up":
        return {"x": x, "y": y + 1}
    elif move == "down":
        return {"x": x, "y": y - 1}
    elif move == "left":
        return {"x": x - 1, "y": y}
    elif move == "right":
        return {"x": x + 1, "y": y}
    return position


def _is_in_bounds(position, width, height):
    return 0 <= position['x'] < width and 0 <= position['y'] < height


def _is_collision_with_body(position, body):
    return any(position['x'] == segment['x'] and position['y'] == segment['y'] for segment in body)


def _is_collision_with_opponents(position, opponents, exclude_tails=True):
    for opponent in opponents:
        body = opponent['body'][:-1] if exclude_tails else opponent['body']
        if _is_collision_with_body(position, body):
            return True
    return False


def _manhattan_distance(pos1, pos2):
    return abs(pos1['x'] - pos2['x']) + abs(pos1['y'] - pos2['y'])


def _positions_equal(pos1, pos2):
    return pos1['x'] == pos2['x'] and pos1['y'] == pos2['y']


def _get_possible_next_positions(position, width, height):
    possible = []
    for move in ["up", "down", "left", "right"]:
        next_pos = _get_next_position(position, move)
        if _is_in_bounds(next_pos, width, height):
            possible.append(next_pos)
    return possible


# ============================================================================
# Patch 1: Dynamic Flood Fill
# ============================================================================

def _flood_fill_dynamic(start_pos, game_state):
    """
    Flood fill algorithm (dynamic depth version)
    Patch 1 - Dynamically adjust search depth based on map size
    """
    board_width = game_state['board']['width']
    board_height = game_state['board']['height']
    my_body = game_state['you']['body']
    my_length = len(my_body)
    all_snakes = game_state['board']['snakes']

    obstacles = set()
    for segment in my_body[:-1]:
        obstacles.add((segment['x'], segment['y']))

    for snake in all_snakes:
        if snake['id'] != game_state['you']['id']:
            for segment in snake['body'][:-1]:
                obstacles.add((segment['x'], segment['y']))

    # Dynamically calculate maximum iterations
    board_size = board_width * board_height

    if board_size <= 100:  # Small map (7x7, 10x10)
        base_max = 80
    elif board_size <= 200:  # Medium map (11x11, 13x13)
        base_max = 120
    else:  # Large map (19x19, 25x25)
        base_max = min(board_size // 2, 250)

    # Early termination condition
    safe_space = my_length * 3

    visited = set()
    queue = deque([start_pos])
    start_tuple = (start_pos['x'], start_pos['y'])
    visited.add(start_tuple)
    count = 0

    while queue and count < base_max:
        current = queue.popleft()
        count += 1

        # Early termination optimization
        if count >= safe_space:
            break

        for move in ["up", "down", "left", "right"]:
            next_pos = _get_next_position(current, move)
            pos_tuple = (next_pos['x'], next_pos['y'])

            if (pos_tuple not in visited and
                    pos_tuple not in obstacles and
                    _is_in_bounds(next_pos, board_width, board_height)):
                visited.add(pos_tuple)
                queue.append(next_pos)

    return count


# ============================================================================
# Patch 4: Smart Food Selection Helper Functions
# ============================================================================

def _estimate_space_after_reaching(food_pos, game_state):
    """Estimate space after reaching food position"""
    temp_state = {
        'board': game_state['board'],
        'you': {
            'id': game_state['you']['id'],
            'body': [food_pos] + game_state['you']['body'][:-1],
            'health': game_state['you']['health']
        }
    }
    return _flood_fill_dynamic(food_pos, temp_state)


def _count_threats_near(food_pos, opponents, my_length, my_head):
    """Count threats near food position"""
    threat_count = 0.0
    my_distance = _manhattan_distance(my_head, food_pos)

    for opponent in opponents:
        opp_head = opponent['body'][0]
        opp_distance = _manhattan_distance(opp_head, food_pos)
        opp_length = len(opponent['body'])

        if opp_distance <= my_distance and opp_length >= my_length:
            threat_count += 10.0 / (opp_distance + 1)

    return threat_count


# ============================================================================
# Patch 3: Multi-step Prediction
# ============================================================================

def _predict_opponent_next_moves(opponent, board_width, board_height, depth=2):
    """Predict opponent's next 2 positions"""
    opponent_head = opponent['body'][0]
    opponent_body = opponent['body']
    predicted_positions = []
    first_step_positions = []

    for move1 in ["up", "down", "left", "right"]:
        pos1 = _get_next_position(opponent_head, move1)
        if not _is_in_bounds(pos1, board_width, board_height):
            continue
        if _is_collision_with_body(pos1, opponent_body[:-1]):
            continue
        predicted_positions.append(pos1)
        first_step_positions.append(pos1)

    if depth >= 2:
        for pos1 in first_step_positions:
            for move2 in ["up", "down", "left", "right"]:
                pos2 = _get_next_position(pos1, move2)
                if not _is_in_bounds(pos2, board_width, board_height):
                    continue
                future_body = [pos1] + opponent_body[:-2]
                if _is_collision_with_body(pos2, future_body):
                    continue
                predicted_positions.append(pos2)

    return predicted_positions


# Start server
if __name__ == "__main__":
    from server import run_server

    run_server({"info": info, "start": start, "move": move, "end": end})