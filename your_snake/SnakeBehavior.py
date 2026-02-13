from flood_fill import flood_fill
from a_star import a_star


class SnakeBehavior:
    """
    Class for handling the behavior and movement logic of the snake.
    """

    def preventBack(is_move_safe, my_head, my_neck):

        #Prevents the snake from moving back into its neck.
        if my_neck["x"] < my_head["x"]:
            is_move_safe["left"] = False
        elif my_neck["x"] > my_head["x"]:
            is_move_safe["right"] = False
        elif my_neck["y"] < my_head["y"]:
            is_move_safe["down"] = False
        elif my_neck["y"] > my_head["y"]:
            is_move_safe["up"] = False

    def preventOutOfBounds(is_move_safe, my_head, board_width, board_height):

        #Prevents the snake from moving out of bounds.
        if my_head["x"] == 0:
            is_move_safe["left"] = False
        if my_head["x"] == board_width - 1:
            is_move_safe["right"] = False
        if my_head["y"] == 0:
            is_move_safe["down"] = False
        if my_head["y"] == board_height - 1:
            is_move_safe["up"] = False

    def preventSelfCollision(is_move_safe, my_body, my_head):

        #Prevents the snake from colliding with itself.
        for body_part in my_body[1:]:
            if body_part["x"] == my_head["x"]:
                if body_part["y"] == my_head["y"] - 1:
                    is_move_safe["down"] = False
                if body_part["y"] == my_head["y"] + 1:
                    is_move_safe["up"] = False
            if body_part["y"] == my_head["y"]:
                if body_part["x"] == my_head["x"] - 1:
                    is_move_safe["left"] = False
                if body_part["x"] == my_head["x"] + 1:
                    is_move_safe["right"] = False

    def preventCollision(is_move_safe, opponents, my_head):

        #Prevents the snake from colliding with opponents.
        for opponent in opponents:
            for body_part in opponent['body']:
                if body_part["x"] == my_head["x"]:
                    if body_part["y"] == my_head["y"] - 1:
                        is_move_safe["down"] = False
                    if body_part["y"] == my_head["y"] + 1:
                        is_move_safe["up"] = False
                if body_part["y"] == my_head["y"]:
                    if body_part["x"] == my_head["x"] - 1:
                        is_move_safe["left"] = False
                    if body_part["x"] == my_head["x"] + 1:
                        is_move_safe["right"] = False

    def preventHeadToHead(is_move_safe, opponents, my_head, my_size):

        # Avoid head-to-head squares if the opponent is equal or larger.
        move_deltas = {
            "up": (0, 1),
            "down": (0, -1),
            "left": (-1, 0),
            "right": (1, 0),
        }

        for opponent in opponents:
            if opponent["length"] < my_size:
                continue
            opp_head = opponent["head"]
            opp_adjacent = {
                (opp_head["x"] + dx, opp_head["y"] + dy)
                for dx, dy in move_deltas.values()
            }
            for move, (dx, dy) in move_deltas.items():
                new_head = (my_head["x"] + dx, my_head["y"] + dy)
                if new_head in opp_adjacent:
                    is_move_safe[move] = False

    def determine_move_options(safe_moves, my_head, board_width, board_height,
                               my_body, opponents, game_state, move_options):

        #Determines the move options based on safe moves and accessible area.
        base_obstacles = set()
        for opponent in opponents:
            for part in opponent["body"]:
                base_obstacles.add((part["x"], part["y"]))

        food_positions = {(f["x"], f["y"]) for f in game_state["board"]["food"]}

        # Check each possible move using flood fill
        for move in safe_moves:
            if move == "up":
                new_head = (my_head["x"], my_head["y"] + 1)
            elif move == "down":
                new_head = (my_head["x"], my_head["y"] - 1)
            elif move == "left":
                new_head = (my_head["x"] - 1, my_head["y"])
            elif move == "right":
                new_head = (my_head["x"] + 1, my_head["y"])

            obstacles = set(base_obstacles)
            if new_head in food_positions:
                for part in my_body:
                    obstacles.add((part["x"], part["y"]))
            else:
                for part in my_body[:-1]:
                    obstacles.add((part["x"], part["y"]))

            accessible_area = flood_fill.flood_fill(game_state['board'],
                                                    new_head[0], new_head[1],
                                                    board_width, board_height,
                                                    obstacles)
            move_options[move] = accessible_area

    def determine_next_move(game_state):
        """
        Single scoring-based move policy for duel mode.
        """
        board = game_state.get("board", {})
        width = board.get("width", 0)
        height = board.get("height", 0)
        my_snake = game_state.get("you", {})
        my_id = my_snake.get("id")
        my_body = my_snake.get("body", [])
        if width <= 0 or height <= 0 or not my_body:
            return "up"

        my_head = my_body[0]
        my_tail = my_body[-1]
        my_length = my_snake.get("length", len(my_body))
        my_health = my_snake.get("health", 100)
        food = board.get("food", [])
        food_positions = {(f.get("x"), f.get("y")) for f in food
                          if "x" in f and "y" in f}

        snakes = board.get("snakes", [])
        opponents = [snake for snake in snakes if snake.get("id") != my_id]
        opponent = opponents[0] if opponents else None

        move_deltas = {
            "up": (0, 1),
            "down": (0, -1),
            "left": (-1, 0),
            "right": (1, 0),
        }

        def in_bounds(x, y):
            return 0 <= x < width and 0 <= y < height

        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        def build_blocked(next_head):
            eating = next_head in food_positions
            blocked = set()
            for snake in snakes:
                snake_id = snake.get("id")
                for part in snake.get("body", []):
                    if "x" not in part or "y" not in part:
                        continue
                    coord = (part["x"], part["y"])
                    if snake_id == my_id:
                        if coord == (my_tail.get("x"), my_tail.get("y")) and not eating:
                            continue
                    blocked.add(coord)
            return blocked, eating

        opponent_next = set()
        if opponent and "head" in opponent:
            opp_head = opponent["head"]
            for dx, dy in move_deltas.values():
                if "x" in opp_head and "y" in opp_head:
                    nx, ny = opp_head["x"] + dx, opp_head["y"] + dy
                    if in_bounds(nx, ny):
                        opponent_next.add((nx, ny))

        center_x = (width - 1) / 2.0
        center_y = (height - 1) / 2.0
        best_move = "up"
        best_score = float("-inf")

        for move, (dx, dy) in move_deltas.items():
            next_head = (my_head["x"] + dx, my_head["y"] + dy)
            if not in_bounds(next_head[0], next_head[1]):
                continue

            blocked, eating = build_blocked(next_head)
            if next_head in blocked:
                continue

            if opponent and next_head in opponent_next and opponent["length"] >= my_length:
                continue

            space = flood_fill.flood_fill(board, next_head[0], next_head[1],
                                          width, height, blocked)
            if space < my_length + 5:
                continue

            score = float(space) * 4.0

            if food_positions:
                if my_health < 35:
                    nearest_food = min(
                        manhattan(next_head, food_pos)
                        for food_pos in food_positions
                    )
                    score += max(0.0, 10.0 - float(nearest_food))
                    if next_head in food_positions:
                        score += 30.0
                else:
                    if next_head in food_positions:
                        if space >= my_length + 7:
                            score += 5.0
                        else:
                            score -= 5.0

            if opponent and opponent.get("length", 0) < my_length and opponent_next:
                if next_head in opponent_next:
                    score += 15.0
                else:
                    for opp_pos in opponent_next:
                        if manhattan(next_head, opp_pos) == 1:
                            score += 5.0
                            break

            if opponent and "head" in opponent:
                opp_blocked = set()
                for snake in snakes:
                    for part in snake.get("body", []):
                        if "x" not in part or "y" not in part:
                            continue
                        opp_blocked.add((part["x"], part["y"]))
                if not eating:
                    opp_blocked.discard((my_tail.get("x"), my_tail.get("y")))
                opp_head = opponent["head"]
                if "x" in opp_head and "y" in opp_head:
                    opp_blocked.discard((opp_head["x"], opp_head["y"]))
                    opp_blocked.add(next_head)

                    opp_space = flood_fill.flood_fill(board, opp_head["x"],
                                                      opp_head["y"], width,
                                                      height, opp_blocked)
                    if (opp_space < opponent.get("length", 0) + 3 and
                            space >= my_length + 8):
                        score += 200.0

            score -= manhattan(next_head, (center_x, center_y)) * 0.3

            if (next_head[0] == 0 or next_head[0] == width - 1 or
                    next_head[1] == 0 or next_head[1] == height - 1):
                score -= 3.0

            if score > best_score:
                best_score = score
                best_move = move

        return best_move