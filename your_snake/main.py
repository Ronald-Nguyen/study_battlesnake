
import random
import typing
from SnakeBehavior import*


"""
class to run the snake
"""
class Snake:    
    def info() -> typing.Dict:
        """
        Returns information about the Battlesnake.
        """
        print("INFO")
        return {
            "apiversion": "1",
            "author": "ronald",  
            "color": "#888888",  
            "head": "default",  
            "tail": "default",  
    
        }
    
    def my_head(game_state: typing.Dict):
        """
        initialize the head of the snake at the start of the game
        """
        print("GAME my_head")
    
    def end(game_state: typing.Dict):
        """
        called at the end of the game to determine the end of the game
        """
        print("GAME OVER\n")
    
    
    
    def move(game_state: typing.Dict) -> typing.Dict:
        """
        Decides the next move for the snake
        """

        #Intializing all important attributes
        is_move_safe = {
              "up": True, 
              "down": True, 
              "left": True, 
              "right": True
            }
        my_head = game_state["you"]["body"][0]
        my_neck = game_state["you"]["body"][1]
        my_size = game_state[ "you"]["length"] 
        my_id = game_state["you"]["id"]
        board_width = game_state['board']['width']
        board_height = game_state['board']['height']
        my_body = game_state['you']['body']
        opponents = [snake for snake in game_state['board']['snakes'] if snake['id'] != my_id]
        largest_opponent = max(opponents, key=lambda snake: snake['length'], default = None)
        my_tail = game_state["you"]["body"][-1]
        food = game_state['board']['food']
        move_options = {}


        #Method to prevent the snake to killing himself by going backwards
        SnakeBehavior.preventBack(is_move_safe, my_head, my_neck)
        
        #Method to prevent the snake to moving out of bounds   
        SnakeBehavior.preventOutOfBounds(is_move_safe, my_head, board_width, board_height)

        #Method to prevent the snake to collide with itself
        SnakeBehavior.preventSelfCollision(is_move_safe, my_body, my_head)

        #Method to prevent the snake to collide with other snakes
        SnakeBehavior.preventCollision(is_move_safe, opponents, my_head)

        #Initialize all safe_moves
        safe_moves = [move for move, isSafe in is_move_safe.items() if isSafe]

        #determine move options through flood fill
        SnakeBehavior.determine_move_options(safe_moves, my_head, board_width, board_height, my_body, opponents, game_state, move_options)

        #determine next move
        next_move = SnakeBehavior.determine_next_move(food, my_head, game_state, my_size, my_tail, my_id, is_move_safe, largest_opponent, opponents, move_options)
    
        
        print(f"MOVE {game_state['turn']}: {next_move}")
        return {"move": next_move}


    if __name__ == "__main__":
        from server import run_server
    
        run_server({
            "info": info, 
            "my_head": my_head, 
            "move": move, 
            "end": end
        })