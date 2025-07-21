import pygame
import numpy as np
import random
import copy
from config import GameConfig
from game_state import GameState
from ecs import World
from systems import (InputSystem, PlayerControlSystem, EnemyAISystem, ItemUseSystem, EquipSystem, InventorySystem, DropItemSystem, CharacterScreenSystem, TrapSystem, PoisonSystem, ShootingSystem, ProjectileSystem, MagicSystem,
                     MovementSystem, ItemPickupSystem, MeleeCombatSystem, DeathSystem, RestingSystem, TradingSystem, HelpScreenSystem,
                     VisibilitySystem, PygameRenderSystem, DoorSystem, LevelUpSystem,
                     NextLevelSystem, TargetingSystem, RangedCombatSystem)
from entities import (create_player, create_wall, create_door, create_stairs, create_up_stairs, create_innkeeper, create_merchant)
from map_generator import MapGenerator
from spawner import spawn_entities, from_dungeon_level
from level_themes import LEVEL_THEME_SEQUENCE, LevelTheme, GOBLIN_CAVES

from components import (Position, Health, Inventory, CombatStats, Name, Experience, Ranged,
                        Item, Consumable, ProvidesHealing, Ranged, AreaOfEffect,
                        InflictsDamage, Equippable, Equipped, Equipment, Poisoned, EquipmentSlot, Mana,
                        Stairs, StairsUp)

def extract_player_data(world: World) -> dict:
    """Extracts player components to carry over to the next level."""
    player = world.player_entity
    if player is None:
        return {}
    
    inventory_component = world.get_component(player, Inventory)
    inventory_items_data = []
    equipped_slots = {} # Maps EquipmentSlot -> inventory index

    if inventory_component:
        for i, item_id in enumerate(inventory_component.items):
            # Check if item is equipped and save its index
            equipped_comp = world.get_component(item_id, Equipped)
            if equipped_comp:
                equipped_slots[equipped_comp.slot] = i

            # Save all components of the item (except Position and Equipped)
            # to recreate it in the new world.
            item_components = []
            for comp_type, components in world.components.items():
                if item_id in components and comp_type not in (Position, Equipped):
                    item_components.append(copy.deepcopy(components[item_id]))
            inventory_items_data.append(item_components)

    data = {
        "health": copy.deepcopy(world.get_component(player, Health)),
        "mana": copy.deepcopy(world.get_component(player, Mana)),
        "inventory_items": inventory_items_data,
        "equipped_slots": copy.deepcopy(equipped_slots),
        "stats": copy.deepcopy(world.get_component(player, CombatStats)),
        "name": copy.deepcopy(world.get_component(player, Name)),
        "experience": copy.deepcopy(world.get_component(player, Experience)),
        "poisoned": copy.deepcopy(world.get_component(player, Poisoned)),
    }
    # Filter out None values in case a component doesn't exist
    return {k: v for k, v in data.items() if v is not None}

def apply_player_data(world: World, player_data: dict | None):
    """Applies saved data to the player entity in the given world."""
    player = world.player_entity
    if player is None or not player_data:
        return

    # Re-apply saved components
    if "health" in player_data: world.add_component(player, player_data["health"])
    if "mana" in player_data: world.add_component(player, player_data["mana"])
    if "stats" in player_data: world.add_component(player, player_data["stats"])
    if "name" in player_data: world.add_component(player, player_data["name"])
    if "experience" in player_data: world.add_component(player, player_data["experience"])
    if "poisoned" in player_data: world.add_component(player, player_data["poisoned"])

    # Re-create inventory items and add them to the player's inventory
    player_inventory = world.get_component(player, Inventory)
    player_equipment = world.get_component(player, Equipment)
    if player_inventory and "inventory_items" in player_data:
        # Clear any default items before adding saved ones
        player_inventory.items.clear()
        for item_components_list in player_data["inventory_items"]:
            item_entity = world.create_entity()
            for component in item_components_list:
                world.add_component(item_entity, component)
            player_inventory.items.append(item_entity)

    # Re-equip items using the saved indices
    if player_equipment and "equipped_slots" in player_data:
        player_equipment.slots.clear()
        for slot, index in player_data["equipped_slots"].items():
            if index < len(player_inventory.items):
                item_to_equip = player_inventory.items[index]
                player_equipment.slots[slot] = item_to_equip
                world.add_component(item_to_equip, Equipped(owner=player, slot=slot))

def generate_hub_world(world: World, player_data: dict | None) -> None:
    """Creates the static hub world."""
    # A simple, static layout for the town
    hub_layout = [
        "####################",
        "#..................#",
        "#.H.......$........#",
        "#..................#",
        "#..................#",
        "#.........>........#",
        "#..................#",
        "####################",
    ]
    
    height = len(hub_layout)
    width = len(hub_layout[0])
    world.game_map = np.zeros((height, width), dtype=np.uint8)

    player_pos = (2, 2)

    for y, row in enumerate(hub_layout):
        for x, char in enumerate(row):
            if char == '#':
                create_wall(world, x, y)
                world.game_map[y, x] = 1
            elif char == '>':
                create_stairs(world, x, y)
                player_pos = (x, y - 1) # Player starts near the stairs
            elif char == 'H':
                create_innkeeper(world, x, y)
            elif char == '$':
                create_merchant(world, x, y)

    player = create_player(world, player_pos[0], player_pos[1])
    # Player data application is handled in generate_world after this call

def recreate_player_in_world(world: World, player_data: dict | None):
    """Creates a player in an existing world and applies their data."""
    player_x, player_y = 2, 2 # Default position

    if world.dungeon_level == 0:
        # In the hub, find the stairs down and place the player nearby
        stairs_entities = world.get_entities_with(Stairs, Position)
        if stairs_entities:
            pos = world.get_component(stairs_entities[0], Position)
            player_x, player_y = pos.x, pos.y - 1
    else:
        # In a dungeon, find the stairs up
        up_stairs_entities = world.get_entities_with(StairsUp, Position)
        if up_stairs_entities:
            pos = world.get_component(up_stairs_entities[0], Position)
            player_x, player_y = pos.x, pos.y

    create_player(world, player_x, player_y)
    apply_player_data(world, player_data)

def generate_world(config: GameConfig, game_state: GameState, theme: LevelTheme) -> World:
    """Creates a new world for a dungeon level."""
    world = World(config, game_state)
    
    # The order is very important for turn-based games!
    # 1. Systems that run every frame (not turn-based)
    world.add_system(InputSystem())
    world.add_system(ProjectileSystem())
    # 2. Systems that handle player UI/targeting modes (pauses the game)
    world.add_system(PlayerControlSystem())
    world.add_system(InventorySystem())
    world.add_system(CharacterScreenSystem())
    world.add_system(HelpScreenSystem())
    world.add_system(EquipSystem())
    world.add_system(TargetingSystem())
    # 3. Turn-based logic: These systems only run if `player_took_turn` is true.
    world.add_system(MagicSystem())
    world.add_system(RangedCombatSystem())
    world.add_system(PoisonSystem())
    world.add_system(EnemyAISystem())
    world.add_system(MovementSystem())
    world.add_system(DoorSystem())
    world.add_system(ItemPickupSystem())
    world.add_system(TrapSystem())
    world.add_system(ShootingSystem())
    world.add_system(MeleeCombatSystem())
    world.add_system(ItemUseSystem())
    world.add_system(RestingSystem())
    world.add_system(TradingSystem())
    world.add_system(DropItemSystem())
    world.add_system(DeathSystem())
    world.add_system(LevelUpSystem())
    world.add_system(NextLevelSystem())
    world.add_system(VisibilitySystem())
    world.add_system(PygameRenderSystem(config))

    if game_state.current_level == 0:
        # Generate the hub world
        generate_hub_world(world, game_state.player_data)
    else:
        # Generate a dungeon level
        map_gen = MapGenerator(config.grid_width, config.grid_height)
        game_map = map_gen.generate(theme.map_generation_type)
        world.game_map = game_map

        # Door placement logic
        door_locations = []
        for y in range(1, config.grid_height - 2):
            for x in range(1, config.grid_width - 2):
                if game_map[y, x] == 0:
                    if game_map[y, x - 1] == 1 and game_map[y, x + 1] == 1 and \
                       game_map[y - 1, x] == 0 and game_map[y + 1, x] == 0:
                        door_locations.append((x, y))
                    elif game_map[y - 1, x] == 1 and game_map[y + 1, x] == 1 and \
                         game_map[y, x - 1] == 0 and game_map[y, x + 1] == 0:
                        door_locations.append((x, y))

        # Create walls and doors
        for y in range(config.grid_height):
            for x in range(config.grid_width):
                if game_map[y, x] == 1:
                    create_wall(world, x, y)
        
        max_doors = from_dungeon_level([[15, 1], [20, 4]], game_state.current_level)
        for x, y in random.sample(door_locations, min(len(door_locations), max_doors)):
            create_door(world, x, y)
            game_map[y, x] = 2 # Mark door location

        map_gen.map = game_map
        
        # Create player
        player_x, player_y = map_gen.find_random_floor_tile()
        player = create_player(world, player_x, player_y)

        # Create stairs
        stairs_x, stairs_y = map_gen.find_random_floor_tile()
        while (stairs_x, stairs_y) == (player_x, player_y):
            stairs_x, stairs_y = map_gen.find_random_floor_tile()
        create_stairs(world, stairs_x, stairs_y)
        create_up_stairs(world, player_x, player_y) # Stairs up appear where player starts

        # Spawn other entities
        spawn_entities(world, map_gen, theme, (player_x, player_y), (stairs_x, stairs_y))

    # Apply player data if it exists (for both hub and dungeon)
    if game_state.player_data:
        apply_player_data(world, game_state.player_data)
            
    return world

def main():
    config = GameConfig()
    game_state = GameState()

    while game_state.running:
        # --- World Loading / Generation ---
        if game_state.current_level in game_state.dungeon_cache:
            world = game_state.dungeon_cache[game_state.current_level]
            world.next_level = False # Reset flag before starting the loop
            recreate_player_in_world(world, game_state.player_data)
        else:
            # Generate a new world if not in cache
            if game_state.current_level == 0:
                current_theme = GOBLIN_CAVES # Dummy theme for hub
            else:
                theme_index = min(game_state.current_level - 1, len(LEVEL_THEME_SEQUENCE) - 1)
                current_theme = LEVEL_THEME_SEQUENCE[theme_index]
            world = generate_world(config, game_state, current_theme)
        
        # --- Game Loop for the current level ---
        while world.running and not world.next_level:
            world.update()

        # --- Level Transition ---
        if not world.running:
            # Player died or quit the game
            game_state.running = False
            continue

        if world.next_level:
            # 1. Save player state
            game_state.player_data = extract_player_data(world)
            
            # 2. Determine target level and update max depth
            prev_level = world.dungeon_level
            target_level = world.next_level_target
            
            if target_level == 0: # Going to hub
                game_state.player_data['experience'].max_dungeon_level = max(game_state.player_data['experience'].max_dungeon_level, prev_level)
            elif target_level == 1 and prev_level == 0: # Going from hub to dungeon
                target_level = game_state.player_data['experience'].max_dungeon_level

            # 3. Remove player from the current world before caching it
            if world.player_entity is not None:
                world.destroy_entity(world.player_entity)
                world.player_entity = None

            # 4. Cache the world state
            game_state.dungeon_cache[prev_level] = world

            # 5. Set the next level to be loaded
            game_state.current_level = target_level

    # Clean up pygame
    pygame.quit()
    
if __name__ == "__main__":
    main()
