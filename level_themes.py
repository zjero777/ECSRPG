from dataclasses import dataclass, field
from typing import Dict, Callable, List

from ecs import World
from entities import (create_goblin, create_orc, create_skeleton, create_mage, create_healing_potion,
                      create_teleport_scroll, create_fireball_scroll, create_bow, create_arrow,
                      create_dagger,
                      create_sword, create_leather_armor, create_chain_mail,
                      create_damage_trap, create_poison_trap)

@dataclass
class LevelTheme:
    """Определяет все параметры для генерации тематического уровня."""
    name: str
    map_generation_type: str = 'rooms'
    monster_chances: Dict[Callable, int] = field(default_factory=dict)
    item_chances: Dict[Callable, int] = field(default_factory=dict)
    trap_chances: Dict[Callable, int] = field(default_factory=dict)
    max_monsters_per_level: int = 5
    max_items_per_level: int = 2
    max_traps_per_level: int = 2

# --- Определения тем ---

GOBLIN_CAVES = LevelTheme(
    name="Goblin Caves",
    map_generation_type='caves',
    monster_chances={
        create_goblin: 90,
        create_orc: 10,
    },
    item_chances={
        create_healing_potion: 50,
        create_dagger: 30,
        create_leather_armor: 20,
        create_bow: 15,
        create_arrow: 40,
    },
    trap_chances={
        create_damage_trap: 100,
    },
    max_monsters_per_level=7,
    max_items_per_level=3,
    max_traps_per_level=3
)

SKELETON_CRYPT = LevelTheme(
    name="Skeleton Crypt",
    map_generation_type='rooms',
    monster_chances={
        create_skeleton: 60,
        create_orc: 20,
        create_mage: 20,
    },
    item_chances={
        create_healing_potion: 30,
        create_fireball_scroll: 25,
        create_sword: 25,
        create_chain_mail: 20,
        create_bow: 10,
        create_arrow: 30,
    },
    trap_chances={
        create_damage_trap: 50,
        create_poison_trap: 50,
    },
    max_monsters_per_level=5,
    max_items_per_level=4,
    max_traps_per_level=5
)

# Последовательность тем в игре
LEVEL_THEME_SEQUENCE: List[LevelTheme] = [
    GOBLIN_CAVES, GOBLIN_CAVES, GOBLIN_CAVES, # Уровни 1-3
    SKELETON_CRYPT, SKELETON_CRYPT, SKELETON_CRYPT # Уровни 4-6
]