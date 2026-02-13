import heapq
class a_star :

    # A* search algorithm for pathfinding
    def a_star_search(start, goal, board, snakes, my_snake_id, largest_opponent = 0, my_size = 0):
        def get_neighbors(node):
            neighbors = []
            directions = {'up': (0, 1), 'down': (0, -1), 'left': (-1, 0), 'right': (1, 0)}
            for direction, (dx, dy) in directions.items():
                neighbor = (node[0] + dx, node[1] + dy)
                if 0 <= neighbor[0] < board['width'] and 0 <= neighbor[1] < board['height']:
                    neighbors.append((neighbor, direction))
            return neighbors

        def heuristic(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])

        def cost(node):
            if node == goal and largest_opponent < my_size:
                return 1
            for snake in snakes:
                snake_body = [(part['x'], part['y']) for part in snake['body']]
                
                # Ignoring own tail
                if snake['id'] == my_snake_id:
                    if node in snake_body[:-1]: 
                        return float('inf')
                else:
                    if node in snake_body:
                        return float('inf')
            return 1

        open_set = []
        heapq.heappush(open_set, (0, start))
        came_from = {}
        g_score = {start: 0}
        f_score = {start: heuristic(start, goal)}

        while open_set:
            current = heapq.heappop(open_set)[1]

            if current == goal:
                path = []
                while current in came_from:
                    current, direction = came_from[current]
                    path.append(direction)
                return path[::-1]

            for neighbor, direction in get_neighbors(current):
                tentative_g_score = g_score[current] + cost(neighbor)
                if tentative_g_score < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = (current, direction)
                    g_score[neighbor] = tentative_g_score
                    f_score[neighbor] = tentative_g_score + heuristic(neighbor, goal)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))

        return []

