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

    def determine_move_options(safe_moves, my_head, board_width, board_height,
                               my_body, opponents, game_state, move_options):

        #Determines the move options based on safe moves and accessible area.
        obstacles = set()
        for part in my_body:
            obstacles.add((part["x"], part["y"]))
        for opponent in opponents:
            for part in opponent["body"]:
                obstacles.add((part["x"], part["y"]))

        # Check each possible move using flood fill
        for move in safe_moves:
            if move == "up":
                new_head = (my_head["x"], my_head["y"] - 1)
            elif move == "down":
                new_head = (my_head["x"], my_head["y"] + 1)
            elif move == "left":
                new_head = (my_head["x"] - 1, my_head["y"])
            elif move == "right":
                new_head = (my_head["x"] + 1, my_head["y"])

            accessible_area = flood_fill.flood_fill(game_state['board'],
                                                    new_head[0], new_head[1],
                                                    board_width, board_height,
                                                    obstacles)
            move_options[move] = accessible_area

    def determine_next_move(food, my_head, game_state, my_size, my_tail, my_id,
                            is_move_safe, largest_opponent, opponents,
                            move_options):
        """
        This method determines the snake's next move by pathfinding to the nearest food using A* search. 
        It iterates through all foods to check if any other snake has a shorter path to them. 
        If every food can be reached faster, then the snake is looping around itself.
        If no food is reachable, the snake maximizes its accessible area on the board.
        """

        next_move = None

        #Initializing the path to tail of the snake to make the snake looping and avoid self-trapping
        my_path_tail = a_star.a_star_search(
            (my_head['x'], my_head['y']), (my_tail['x'], my_tail['y']),
            game_state['board'], game_state['board']['snakes'], my_id)

        if food:
            #sort food items by distance to  the snake's head
            sorted_foods = sorted(food,
                                  key=lambda f: abs(f['x'] - my_head['x']) +
                                  abs(f['y'] - my_head['y']))

            # Iterate through each food to find the closest and safest path with A* search
            for food_item in sorted_foods:
                my_path = a_star.a_star_search(
                    (my_head['x'], my_head['y']),
                    (food_item['x'], food_item['y']), game_state['board'],
                    game_state['board']['snakes'], my_id)
                if not my_path:
                    continue
                closest_food = True

                # check paths of each oppenent for the same food item
                for opponent in opponents:
                    opponent_path = a_star.a_star_search(
                        (opponent["head"]["x"], opponent["head"]["y"]),
                        (food_item['x'], food_item['y']), game_state['board'],
                        game_state['board']['snakes'], my_id)
                    if not opponent_path:
                        continue
                    if len(opponent_path) < len(my_path) or (
                            len(opponent_path) == len(my_path)
                            and my_size <= opponent["length"]):
                        closest_food = False
                        break

                if closest_food:
                    # check if there is a safe path from the food item to the tail
                    food_tail_path = a_star.a_star_search(
                        (food_item['x'], food_item['y']),
                        (my_tail['x'], my_tail['y']), game_state['board'],
                        game_state['board']['snakes'], my_id)
                    if len(sorted_foods) == 1 and food_tail_path:
                        print("path")
                        next_move = my_path[0]
                        break

                    # check if another food is reachable from the food item
                    for foods in sorted_foods:
                        food_path = a_star.a_star_search(
                            (foods['x'], foods['y']),
                            (food_item['x'], food_item['y']),
                            game_state['board'], game_state['board']['snakes'],
                            my_id)
                        if foods != food_item:
                            if not food_path and len(sorted_foods) > 1:
                                if my_path:
                                    print("path not safe")
                                    is_move_safe[my_path[0]] = False
                            else:
                                if my_path:
                                    print("path")
                                    next_move = my_path[0]
                                    break
                    else:
                        continue
                    break

            else:
                """
                if no food path is safe but my snake is the strongest, then the snake is doing A* pathfinding to the food
                if no food path is reachable then, the snake is maximizing it reachable area through flood fill
                """
                if largest_opponent:
                    if largest_opponent[
                            'length'] < my_size and largest_opponent:
                        for foods in sorted_foods:
                            food_path = a_star.a_star_search(
                                (foods['x'], foods['y']),
                                (food_item['x'], food_item['y']),
                                game_state['board'],
                                game_state['board']['snakes'], my_id)
                            food_tail_path = a_star.a_star_search(
                                (foods['x'], foods['y']),
                                (my_tail['x'], my_tail['y']),
                                game_state['board'],
                                game_state['board']['snakes'], my_id)
                            if foods != food_item:
                                if not food_path and len(
                                        sorted_foods
                                ) > 1 and not food_tail_path and my_path:
                                    print("path not safe")
                                    is_move_safe[my_path[0]] = False
                                else:
                                    if my_path:
                                        print("path size")
                                        next_move = my_path[0]
                                        break
                                    else:
                                        print("flood fill")
                                        next_move = max(move_options,
                                                        key=move_options.get)

                        if my_path:
                            print("path")
                            next_move = my_path[0]

                    elif my_path_tail:
                        print("tail")
                        next_move = my_path_tail[0]

                    else:
                        print("flood fill")
                        next_move = max(move_options, key=move_options.get)

        else:
            print("flood fill")
            next_move = max(move_options, key=move_options.get)

        if next_move is None:
            print("flood fill")
            next_move = max(move_options, key=move_options.get)

        return next_move