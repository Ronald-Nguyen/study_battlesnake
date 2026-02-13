
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
    
    def start(game_state: typing.Dict):
        """
        initialize the head of the snake at the start of the game
        """
        print("GAME start")
    
    def end(game_state: typing.Dict):
        """
        called at the end of the game to determine the end of the game
        """
        print("GAME OVER\n")
    
    
    
    def move(game_state: typing.Dict) -> typing.Dict:
        """
        Decides the next move for the snake
        """
        next_move = SnakeBehavior.determine_next_move(game_state)
    
        
        print(f"MOVE {game_state['turn']}: {next_move}")
        return {"move": next_move}


    if __name__ == "__main__":
        from server import run_server
    
        run_server({
            "info": info, 
            "start": start, 
            "move": move, 
            "end": end
        })