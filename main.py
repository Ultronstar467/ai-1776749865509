from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Tuple, Dict
import random
import uuid

app = FastAPI()

# --- Pydantic Models for API ---
class Position(BaseModel):
    x: int
    y: int

class GameStateResponse(BaseModel):
    game_id: str
    board_width: int
    board_height: int
    snake: List[Position]
    food: Position
    score: int
    direction: str # Current direction of the snake
    game_over: bool
    game_won: bool = False # Added for potential win condition

class StartGameResponse(GameStateResponse):
    pass # Same structure as GameStateResponse

class MoveRequest(BaseModel):
    game_id: str
    direction: str # The *desired* new direction

# --- Internal Game State Representation and Logic ---
class InternalGameState:
    def __init__(self, board_width: int = 20, board_height: int = 20):
        self.game_id = str(uuid.uuid4())
        self.board_width = board_width
        self.board_height = board_height
        self.score = 0
        self.game_over = False
        self.game_won = False
        
        # Initialize snake in the middle, head is at index 0
        self.snake = [Position(x=board_width // 2, y=board_height // 2)] 
        self.direction = "RIGHT" # Initial direction
        self.food = self._generate_food()

    def _generate_food(self) -> Position:
        """Generates a new food position, ensuring it's not on the snake."""
        # If the entire board is filled by the snake, the player wins
        if len(self.snake) >= self.board_width * self.board_height:
            self.game_won = True
            return Position(x=-1, y=-1) # Placeholder for no food if game won

        while True:
            food_x = random.randint(0, self.board_width - 1)
            food_y = random.randint(0, self.board_height - 1)
            new_food = Position(x=food_x, y=food_y)
            if new_food not in self.snake:
                return new_food

    def _get_next_head_position(self, current_direction: str) -> Position:
        """Calculates the next potential head position based on current direction."""
        head = self.snake[0]
        if current_direction == "UP":
            return Position(x=head.x, y=head.y - 1)
        elif current_direction == "DOWN":
            return Position(x=head.x, y=head.y + 1)
        elif current_direction == "LEFT":
            return Position(x=head.x - 1, y=head.y)
        elif current_direction == "RIGHT":
            return Position(x=head.x + 1, y=head.y)
        return head # Should not be reached

    def _is_opposite(self, new_dir: str, current_dir: str) -> bool:
        """Checks if the new direction is directly opposite to the current direction."""
        return ((new_dir == "UP" and current_dir == "DOWN") or
                (new_dir == "DOWN" and current_dir == "UP") or
                (new_dir == "LEFT" and current_dir == "RIGHT") or
                (new_dir == "RIGHT" and current_dir == "LEFT"))

    def update_direction(self, desired_direction: str):
        """Updates the snake's direction if the desired direction is valid."""
        if not self._is_opposite(desired_direction, self.direction):
            self.direction = desired_direction

    def advance_game(self) -> GameStateResponse:
        """Advances the game state by one tick, moving the snake and checking for events."""
        if self.game_over or self.game_won:
            return self.to_response()

        new_head = self._get_next_head_position(self.direction)

        # 1. Check for wall collision
        if not (0 <= new_head.x < self.board_width and 0 <= new_head.y < self.board_height):
            self.game_over = True
            return self.to_response()

        # 2. Check for self-collision (new head collides with any part of existing snake)
        if new_head in self.snake:
            self.game_over = True
            return self.to_response()

        # 3. Check for food collision
        eats_food = (new_head == self.food)

        # Update snake position
        self.snake.insert(0, new_head) # Add new head
        if not eats_food:
            self.snake.pop() # Remove tail if no food eaten
        else:
            self.score += 1
            if not self.game_won: # Only generate new food if game isn't won yet
                self.food = self._generate_food()
            # If _generate_food sets game_won to True, the food will be (-1,-1)

        return self.to_response()

    def to_response(self) -> GameStateResponse:
        """Converts the internal game state to a Pydantic response model."""
        return GameStateResponse(
            game_id=self.game_id,
            board_width=self.board_width,
            board_height=self.board_height,
            snake=self.snake,
            food=self.food,
            score=self.score,
            direction=self.direction,
            game_over=self.game_over,
            game_won=self.game_won
        )

# --- Global storage for active games ---
active_games: Dict[str, InternalGameState] = {}

# --- FastAPI Endpoints ---
@app.post("/game/start", response_model=StartGameResponse)
async def start_game():
    """Starts a new snake game and returns its initial state."""
    game = InternalGameState()
    active_games[game.game_id] = game
    return game.to_response()

@app.post("/game/{game_id}/move", response_model=GameStateResponse)
async def move_snake(game_id: str, request: MoveRequest):
    """
    Receives a desired direction for the snake, advances the game by one tick,
    and returns the new game state.
    """
    game = active_games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # If game is over or won, no further moves are processed.
    if game.game_over or game.game_won:
        return game.to_response()

    # Update the internal direction based on desired direction from frontend
    game.update_direction(request.direction)

    # Advance the game state
    return game.advance_game()

@app.get("/game/{game_id}/state", response_model=GameStateResponse)
async def get_game_state(game_id: str):
    """Retrieves the current state of a specific game."""
    game = active_games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game.to_response()