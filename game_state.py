from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ecs import World

@dataclass
class GameState:
    """Holds the state of the game that persists between levels."""
    log: List[str] = field(default_factory=list)
    dungeon_cache: Dict[int, World] = field(default_factory=dict)
    current_level: int = 0
    player_data: Dict[str, Any] | None = None
    running: bool = True