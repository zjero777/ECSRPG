from __future__ import annotations
import pygame
import numpy as np
from typing import Dict, List, Type, Set, Any, Optional, TYPE_CHECKING

from config import GameConfig

if TYPE_CHECKING:
    from pygame.event import Event
    from game_state import GameState

# Entity - просто уникальный идентификатор
Entity = int

# Базовый класс для систем
class System:
    def update(self, world: "World"):
        pass

# Мир, который управляет всем
class World:
    def __init__(self, config: GameConfig, game_state: GameState):
        self.entities: Set[Entity] = set()
        self.next_entity = 0
        self.available_entities: List[Entity] = []
        self.components: Dict[Type, Dict[Entity, Any]] = {}
        self.systems: List[System] = []
        self.config = config
        self.dungeon_level = game_state.current_level
        self.running = True
        self.player_entity: Optional[Entity] = None
        self.player_took_turn: bool = False
        self.visibility_map = np.zeros((config.grid_height, config.grid_width), dtype=np.uint8)
        self.game_map: Optional[np.ndarray] = None
        self.log = game_state.log
        self.events: List[Event] = []
        self.turn = 0
        self.next_level: bool = False
        self.next_level_target: int = 0
    
    def create_entity(self) -> Entity:
        if self.available_entities:
            entity_id = self.available_entities.pop()
        else:
            entity_id = self.next_entity
            self.next_entity += 1
        self.entities.add(entity_id)
        return entity_id
    
    def destroy_entity(self, entity: Entity):
        """Полностью удаляет сущность и все ее компоненты, делая ее ID доступным для переиспользования."""
        if entity not in self.entities:
            return

        for component_pool in self.components.values():
            if entity in component_pool:
                del component_pool[entity]

        self.entities.remove(entity)
        self.available_entities.append(entity)

    def add_component(self, entity: Entity, component: Any):
        component_type = type(component)
        if component_type not in self.components:
            self.components[component_type] = {}
        self.components[component_type][entity] = component

    def get_component(self, entity: Entity, component_type: Type) -> Any:
        return self.components.get(component_type, {}).get(entity)
    
    def get_entities_with(self, *component_types: Type) -> List[Entity]:
        if not component_types:
            return list(self.entities)

        try:
            smallest_component_pool = min(component_types, key=lambda ct: len(self.components.get(ct, {})))
        except (KeyError, ValueError):
            return []

        entities_with_smallest_pool = set(self.components.get(smallest_component_pool, {}).keys())
        if not entities_with_smallest_pool:
            return []

        return [entity for entity in entities_with_smallest_pool
                if all(entity in self.components.get(ct, {}) for ct in component_types)]

    def add_system(self, system: System):
        self.systems.append(system)
    
    def update(self):
        for system in self.systems:
            system.update(self)
        
    def quit(self):
        pygame.quit()