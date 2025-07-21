import random
from typing import List, Tuple

from ecs import World, Entity
from map_generator import MapGenerator
from level_themes import LevelTheme

def from_dungeon_level(table: List[List[int]], level: int) -> int:
    """Возвращает значение из таблицы на основе текущего уровня подземелья."""
    for value, table_level in reversed(table):
        if level >= table_level:
            return value
    return 0

def _spawn_monsters(world: World, map_gen: MapGenerator, theme: LevelTheme):
    """Спавнит монстров на уровне."""
    if not theme.monster_chances: return

    num_enemies = random.randint(max(0, theme.max_monsters_per_level - 2), theme.max_monsters_per_level)
    enemy_factories = list(theme.monster_chances.keys())
    enemy_weights = list(theme.monster_chances.values())

    for _ in range(num_enemies):
        enemy_x, enemy_y = map_gen.find_random_floor_tile()
        chosen_enemy_factory = random.choices(enemy_factories, weights=enemy_weights, k=1)[0]
        chosen_enemy_factory(world, enemy_x, enemy_y)

def _spawn_items(world: World, map_gen: MapGenerator, theme: LevelTheme):
    """Спавнит предметы на уровне."""
    if not theme.item_chances: return

    num_items = random.randint(max(0, theme.max_items_per_level - 1), theme.max_items_per_level)
    item_factories = list(theme.item_chances.keys())
    item_weights = list(theme.item_chances.values())

    for _ in range(num_items):
        item_x, item_y = map_gen.find_random_floor_tile()
        chosen_item_factory = random.choices(item_factories, weights=item_weights, k=1)[0]
        chosen_item_factory(world, item_x, item_y)

def _spawn_traps(world: World, map_gen: MapGenerator, theme: LevelTheme, player_pos: Tuple[int, int], stairs_pos: Tuple[int, int]):
    """Спавнит ловушки на уровне."""
    if not theme.trap_chances: return

    num_traps = random.randint(max(0, theme.max_traps_per_level - 1), theme.max_traps_per_level)
    trap_factories = list(theme.trap_chances.keys())
    trap_weights = list(theme.trap_chances.values())

    for _ in range(num_traps):
        trap_x, trap_y = map_gen.find_random_floor_tile()
        if (trap_x, trap_y) != player_pos and (trap_x, trap_y) != stairs_pos:
            chosen_trap_factory = random.choices(trap_factories, weights=trap_weights, k=1)[0]
            chosen_trap_factory(world, trap_x, trap_y)

def spawn_entities(world: World, map_gen: MapGenerator, theme: LevelTheme, player_pos: Tuple[int, int], stairs_pos: Tuple[int, int]):
    """Главная функция для спавна всех сущностей на уровне."""
    _spawn_traps(world, map_gen, theme, player_pos, stairs_pos)
    _spawn_monsters(world, map_gen, theme)
    _spawn_items(world, map_gen, theme)