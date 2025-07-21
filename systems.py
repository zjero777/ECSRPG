import pygame
import numpy as np
import random
from dataclasses import dataclass
from typing import Dict, Tuple, List

from ecs import System, World, Entity
from components import (Position, Velocity, Renderable, Player, Health, Enemy, BlocksMovement, CombatStats, WantsToAttack, Name, Wall, Item, Inventory, Consumable, ProvidesHealing, ProvidesTeleportation, WantsToUseItem, Door, ToggleDoorState, Experience, GivesExperience, Stairs, WantsToDescend, Ranged, AreaOfEffect, InflictsDamage, Targeting, WantsToThrow, TargetingIndicator, Equipment, Equippable, Equipped, WantsToEquip, WantsToShoot, ShowHelpScreen, WantsToCastSpell, MagicSpell, OnCooldown, Mana,
                        EquipmentSlot, WantsToDropItem, ShowInventory, ShowCharacterScreen, WantsToFlee, Trap, Hidden, Triggered, InflictsPoison, Poisoned, WantsToAscend, StairsUp, ProvidesFullHealing, WantsToRest, ProvidesSupplies, WantsToTrade, Projectile, RequiresAmmunition, Ammunition)
from entities import create_healing_potion
from config import GameConfig

class InputSystem(System):
    """Эта система отвечает за обработку всех событий Pygame."""
    def update(self, world: World):
        # Сохраняем события кадра в мире, чтобы другие системы могли их использовать
        world.events = pygame.event.get()
        for event in world.events:
            if event.type == pygame.QUIT:
                world.running = False

class MovementSystem(System):
    def update(self, world: World):
        # Движение происходит только если игрок совершил действие
        # или если мы не в режиме прицеливания
        if world.get_component(world.player_entity, Targeting):
            return

        if not world.player_took_turn:
            return

        # Карта всех сущностей, которые могут блокировать движение: { (x,y): entity_id }
        blocker_locations = {
            (world.get_component(e, Position).x, world.get_component(e, Position).y): e
            for e in world.get_entities_with(Position, BlocksMovement)
        }
        
        entities_to_move = world.get_entities_with(Position, Velocity)
        
        # Приоритет игрока: обрабатываем его движение первым, чтобы мир реагировал на его действия
        player_entity = world.player_entity
        if player_entity in entities_to_move:
            entities_to_move.remove(player_entity)
            entities_to_move.insert(0, player_entity)

        for entity in entities_to_move:
            pos = world.get_component(entity, Position)
            vel = world.get_component(entity, Velocity)

            if vel.dx == 0 and vel.dy == 0:
                continue

            target_x, target_y = pos.x + vel.dx, pos.y + vel.dy

            # 1. Проверяем границы мира
            if not (0 <= target_x < world.config.grid_width and 0 <= target_y < world.config.grid_height):
                continue # Цель за пределами карты, движение отменяется

            # 2. Проверяем, не занята ли целевая клетка другой сущностью
            target_entity_id = blocker_locations.get((target_x, target_y))

            if target_entity_id is not None:
                # Is it a door?
                door_component = world.get_component(target_entity_id, Door)
                if door_component:
                    # It's a door, add intent to toggle it.
                    # The DoorSystem will handle the opening/closing.
                    # The turn is spent bumping the door.
                    world.add_component(target_entity_id, ToggleDoorState())
                # Is it a friendly NPC?
                elif world.get_component(target_entity_id, ProvidesFullHealing):
                    world.add_component(entity, WantsToRest())
                elif world.get_component(target_entity_id, ProvidesSupplies):
                    world.add_component(entity, WantsToTrade())
                # Is it an attackable entity?
                elif world.get_component(target_entity_id, Health):
                    # Prevent enemies from attacking each other
                    is_attacker_enemy = world.get_component(entity, Enemy) is not None
                    is_target_enemy = world.get_component(target_entity_id, Enemy) is not None

                    if not (is_attacker_enemy and is_target_enemy):
                        world.add_component(entity, WantsToAttack(target=target_entity_id))

                continue # Movement is blocked regardless of interaction (attack or open)

            # 3. Движение возможно. Обновляем карту блокировщиков и позицию сущности.
            if (pos.x, pos.y) in blocker_locations:
                del blocker_locations[(pos.x, pos.y)]
            
            pos.x = target_x
            pos.y = target_y
            
            blocker_locations[(pos.x, pos.y)] = entity

class VisibilitySystem(System):
    """Вычисляет поле зрения игрока."""
    def update(self, world: World):
        # Обновляем видимость, только если игрок совершил действие (или на первом ходу)
        if not world.player_took_turn and world.turn != 0:
            return

        player_pos = world.get_component(world.player_entity, Position)
        if not player_pos:
            return

        # 1. Переводим все видимые в данный момент клетки в "исследованные"
        world.visibility_map[world.visibility_map == 2] = 1

        # 2. Создаем карту препятствий для света
        # Только стены блокируют поле зрения, враги и игрок - нет.
        blocks_light = np.zeros((world.config.grid_height, world.config.grid_width), dtype=bool)
        for wall_entity in world.get_entities_with(Position, Wall):
            pos = world.get_component(wall_entity, Position)
            blocks_light[pos.y, pos.x] = True

        # 3. Вычисляем новое поле зрения с помощью рейкастинга
        radius = world.config.fov_radius
        px, py = player_pos.x, player_pos.y
        world.visibility_map[py, px] = 2 # Клетка игрока всегда видима

        def _cast_ray(x1, y1):
            """Вспомогательная функция для бросания одного луча."""
            line = bresenham_line(px, py, x1, y1)
            for lx, ly in line:
                if not (0 <= lx < world.config.grid_width and 0 <= ly < world.config.grid_height):
                    break
                # Используем квадрат расстояния, чтобы избежать вычисления корня
                if (lx - px)**2 + (ly - py)**2 > radius**2:
                    break
                world.visibility_map[ly, lx] = 2 # Клетка видима
                if blocks_light[ly, lx]:
                    break # Луч уперся в препятствие

        # "Permissive Field of View": бросаем лучи ко всем клеткам в радиусе.
        # Это медленнее, чем бросать лучи только по периметру, но дает более
        # точный и предсказуемый результат без "слепых зон" за углами.
        # Для небольшого радиуса (как у нас) производительность приемлема.
        for y in range(py - radius, py + radius + 1):
            for x in range(px - radius, px + radius + 1):
                if (x - px)**2 + (y - py)**2 <= radius**2:
                    _cast_ray(x, y)

class PoisonSystem(System):
    """Applies poison damage and handles duration."""
    def update(self, world: World):
        if not world.player_took_turn:
            return

        # --- Player Cooldown Management ---
        player = world.player_entity
        if player is not None:
            player_cooldown = world.get_component(player, OnCooldown)
            if player_cooldown and player_cooldown.turns > 0:
                player_cooldown.turns -= 1

        for entity in list(world.get_entities_with(Poisoned, Health, Name)):
            poison = world.get_component(entity, Poisoned)
            health = world.get_component(entity, Health)
            name = world.get_component(entity, Name).name

            health.current -= poison.damage
            world.log.append(f"{name} takes {poison.damage} poison damage.")

            poison.duration -= 1
            if poison.duration <= 0:
                world.log.append(f"{name} is no longer poisoned.")
                del world.components[Poisoned][entity]

class EnemyAISystem(System):
    """A simple AI system for enemies."""
    def update(self, world: World):
        if world.get_component(world.player_entity, Targeting):
            return

        # The AI only acts if the player has taken a turn.
        if not world.player_took_turn:
            return

        player_pos = world.get_component(world.player_entity, Position)
        if not player_pos:
            return

        for entity in world.get_entities_with(Enemy, Position, Velocity, Health, Name):
            enemy_pos = world.get_component(entity, Position)
            enemy_vel = world.get_component(entity, Velocity)
            enemy_health = world.get_component(entity, Health)
            enemy_name = world.get_component(entity, Name).name

            # Default to doing nothing this turn
            enemy_vel.dx, enemy_vel.dy = 0, 0

            # --- Cooldown Management ---
            # Reduce cooldown timer each turn for enemies that have one.
            cooldown = world.get_component(entity, OnCooldown)
            if cooldown and cooldown.turns > 0:
                cooldown.turns -= 1

            player_is_visible = world.visibility_map[enemy_pos.y, enemy_pos.x] == 2
            is_low_health = enemy_health.current <= enemy_health.max / 4

            # --- Decision Making ---
            if player_is_visible and is_low_health:
                # Priority 1: Heal if possible
                inventory = world.get_component(entity, Inventory)
                if inventory: # pragma: no branch
                    potion_to_use = next((item_id for item_id in inventory.items if world.get_component(item_id, ProvidesHealing)), None)
                    if potion_to_use:
                        world.add_component(entity, WantsToUseItem(item=potion_to_use))
                        # Using an item takes a turn, so we don't move.
                        continue # Move to the next enemy

                # Priority 2: Flee if can't heal or no potions
                world.add_component(entity, WantsToFlee())
                dx = player_pos.x - enemy_pos.x
                dy = player_pos.y - enemy_pos.y
                enemy_vel.dx = 0 if dx == 0 else -dx // abs(dx)
                enemy_vel.dy = 0 if dy == 0 else -dy // abs(dy)
                continue

            # Stop fleeing if health is recovered or player is not visible
            if world.get_component(entity, WantsToFlee):
                if not is_low_health or not player_is_visible: # pragma: no branch
                    del world.components[WantsToFlee][entity]
                else: # Continue fleeing
                    dx = player_pos.x - enemy_pos.x
                    dy = player_pos.y - enemy_pos.y
                    enemy_vel.dx = 0 if dx == 0 else -dx // abs(dx)
                    enemy_vel.dy = 0 if dy == 0 else -dy // abs(dy)
                    continue

            # Default behavior: Attack or Wander
            if player_is_visible:
                # --- Magic Attack Logic ---
                spell = world.get_component(entity, MagicSpell)
                cooldown = world.get_component(entity, OnCooldown)
                mana = world.get_component(entity, Mana)
                if spell and cooldown and cooldown.turns <= 0 and mana and mana.current >= spell.mana_cost:
                    distance = ((player_pos.x - enemy_pos.x)**2 + (player_pos.y - enemy_pos.y)**2)**0.5
                    if distance <= spell.range:
                        # Check for clear line of sight before casting
                        line_of_sight = bresenham_line(enemy_pos.x, enemy_pos.y, player_pos.x, player_pos.y)
                        path_is_clear = True
                        # Check intermediate points, not start/end
                        for x, y in line_of_sight[1:-1]:
                            if world.game_map[y, x] == 1: # 1 is a wall
                                path_is_clear = False
                                break
                        
                        if path_is_clear:
                            world.add_component(entity, WantsToCastSpell(target=world.player_entity))
                            cooldown.turns = spell.cooldown
                            mana.current -= spell.mana_cost
                            continue # Mage cast a spell, turn is over

                # --- Ranged Attack Logic ---
                equipment = world.get_component(entity, Equipment)
                weapon_id = equipment.slots.get(EquipmentSlot.WEAPON) if equipment else None
                
                if weapon_id and world.get_component(weapon_id, RequiresAmmunition):
                    distance = ((player_pos.x - enemy_pos.x)**2 + (player_pos.y - enemy_pos.y)**2)**0.5
                    ranged_comp = world.get_component(weapon_id, Ranged)

                    if ranged_comp and distance <= ranged_comp.range:
                        # Check for ammo
                        inventory = world.get_component(entity, Inventory)
                        ammo_req = world.get_component(weapon_id, RequiresAmmunition)
                        if inventory and any(world.get_component(item_id, Ammunition) and world.get_component(item_id, Ammunition).ammo_type == ammo_req.ammo_type for item_id in inventory.items):
                            world.add_component(entity, WantsToShoot(target=world.player_entity))
                            continue # Enemy shot, turn is over

                # --- Melee Attack / Movement Logic ---
                dx = player_pos.x - enemy_pos.x
                dy = player_pos.y - enemy_pos.y
                enemy_vel.dx = 0 if dx == 0 else dx // abs(dx)
                enemy_vel.dy = 0 if dy == 0 else dy // abs(dy)
            else:
                # Wander randomly
                enemy_vel.dx = random.randint(-1, 1)
                enemy_vel.dy = random.randint(-1, 1)

class ShootingSystem(System):
    """Handles the act of shooting a projectile."""
    def update(self, world: World):
        for entity in list(world.get_entities_with(WantsToShoot)):
            intent = world.get_component(entity, WantsToShoot)
            if not intent: continue

            equipment = world.get_component(entity, Equipment)
            weapon_id = equipment.slots.get(EquipmentSlot.WEAPON)
            ammo_req = world.get_component(weapon_id, RequiresAmmunition)
            inventory = world.get_component(entity, Inventory)
            arrow_to_use = next((item_id for item_id in inventory.items if world.get_component(item_id, Ammunition) and world.get_component(item_id, Ammunition).ammo_type == ammo_req.ammo_type), None)

            inventory.items.remove(arrow_to_use)
            arrow_damage = world.get_component(arrow_to_use, InflictsDamage).damage
            world.destroy_entity(arrow_to_use)

            source_pos = world.get_component(entity, Position)
            target_pos = world.get_component(intent.target, Position)
            
            projectile = world.create_entity()
            world.add_component(projectile, Position(x=source_pos.x, y=source_pos.y))
            world.add_component(projectile, Renderable("-", "silver"))
            
            path = bresenham_line(source_pos.x, source_pos.y, target_pos.x, target_pos.y)
            world.add_component(projectile, Projectile(path=path[1:]))
            
            attacker_stats = world.get_component(entity, CombatStats)
            weapon_stats = world.get_component(weapon_id, Equippable)
            total_damage = (attacker_stats.power // 2) + weapon_stats.power_bonus + arrow_damage
            world.add_component(projectile, InflictsDamage(damage=total_damage))
            world.add_component(projectile, Name("Arrow"))

            user_name = world.get_component(entity, Name).name
            target_name = world.get_component(intent.target, Name).name
            world.log.append(f"{user_name} shoots an arrow at {target_name}!")

            del world.components[WantsToShoot][entity]

class MagicSystem(System):
    """Handles casting magic spells."""
    def update(self, world: World):
        for entity in list(world.get_entities_with(WantsToCastSpell)):
            intent = world.get_component(entity, WantsToCastSpell)
            if not intent: continue

            spell = world.get_component(entity, MagicSpell)
            if not spell:
                del world.components[WantsToCastSpell][entity]
                continue

            source_pos = world.get_component(entity, Position)
            target_pos = world.get_component(intent.target, Position)
            
            # Create projectile
            projectile = world.create_entity()
            world.add_component(projectile, Position(x=source_pos.x, y=source_pos.y))
            world.add_component(projectile, Renderable("*", "cyan"))
            
            path = bresenham_line(source_pos.x, source_pos.y, target_pos.x, target_pos.y)
            world.add_component(projectile, Projectile(path=path[1:]))
            
            # Damage is based on spell, but can be modified by caster's stats
            caster_stats = world.get_component(entity, CombatStats)
            total_damage = spell.damage + (caster_stats.power // 2 if caster_stats else 0)
            world.add_component(projectile, InflictsDamage(damage=total_damage))
            world.add_component(projectile, Name(spell.name))

            caster_name = world.get_component(entity, Name).name
            target_name = world.get_component(intent.target, Name).name
            world.log.append(f"{caster_name} casts {spell.name} at {target_name}!")

            del world.components[WantsToCastSpell][entity]

def bresenham_line(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Bresenham's Line Algorithm."""
    points = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return points

class ProjectileSystem(System):
    """Moves projectiles and handles their collision."""
    def update(self, world: World):
        projectiles_to_move = list(world.get_entities_with(Projectile, Position))
        if not projectiles_to_move:
            return

        for entity in projectiles_to_move:
            proj = world.get_component(entity, Projectile)
            pos = world.get_component(entity, Position)

            if not proj.path:
                world.destroy_entity(entity)
                continue

            pos.x, pos.y = proj.path.pop(0)

            hit = False
            # 1. Hit a creature
            for target in world.get_entities_with(Position, Health, Name):
                target_pos = world.get_component(target, Position)
                if pos.x == target_pos.x and pos.y == target_pos.y:
                    damage = world.get_component(entity, InflictsDamage)
                    if damage:
                        target_health = world.get_component(target, Health)
                        target_stats = world.get_component(target, CombatStats)
                        target_name = world.get_component(target, Name).name
                        target_defense = target_stats.defense if target_stats else 0
                        target_equipment = world.get_component(target, Equipment)
                        if target_equipment:
                            for item_id in target_equipment.slots.values():
                                equippable = world.get_component(item_id, Equippable)
                                if equippable:
                                    target_defense += equippable.defense_bonus

                        final_damage = max(0, damage.damage - target_defense)
                        projectile_name = world.get_component(entity, Name).name.capitalize()
                        if final_damage > 0:
                            world.log.append(f"{projectile_name} hits {target_name} for {final_damage} damage!")
                            target_health.current -= final_damage
                        else:
                            world.log.append(f"{projectile_name} hits {target_name} but does no damage.")
                    
                    hit = True
                    break
            
            # 2. Hit a wall or flew out of bounds
            if not hit and (world.game_map[pos.y, pos.x] == 1 or not (0 <= pos.x < world.config.grid_width and 0 <= pos.y < world.config.grid_height)):
                projectile_name = world.get_component(entity, Name).name.capitalize()
                world.log.append(f"{projectile_name} shatters against the wall.")
                hit = True
            
            if hit:
                world.destroy_entity(entity)

class TargetingSystem(System):
    def __init__(self):
        self.target_indicators = []

    def update(self, world: World):
        # First, clean up indicators from the previous frame
        for indicator in self.target_indicators:
            world.destroy_entity(indicator)
        self.target_indicators.clear()

        player = world.player_entity
        if player is None: return
        
        targeting_component = world.get_component(player, Targeting)
        if not targeting_component:
            return # Not in targeting mode

        # Freeze the game by not letting other systems take a turn
        world.player_took_turn = False

        player_pos = world.get_component(player, Position)
        target_range = targeting_component.range
        if not player_pos or target_range is None:
            world.components[Targeting].pop(player, None)
            return


        # Get mouse position in grid coordinates
        mouse_x, mouse_y = pygame.mouse.get_pos()
        # This is a bit of a hack to get the camera, ideally systems shouldn't know about each other
        render_system = next((s for s in world.systems if isinstance(s, PygameRenderSystem)), None)
        if not render_system: return
        
        cam = render_system.camera
        cs = world.config.cell_size
        grid_x = (mouse_x + cam.x) // cs
        grid_y = (mouse_y + cam.y) // cs

        # Draw line of sight
        line_path = bresenham_line(player_pos.x, player_pos.y, grid_x, grid_y)
        
        for i, (px, py) in enumerate(line_path):
            if i > target_range:
                break
            indicator = world.create_entity()
            world.add_component(indicator, Position(px, py))
            world.add_component(indicator, TargetingIndicator(color="cyan"))
            self.target_indicators.append(indicator)

        # Draw AoE at the end of the line if applicable
        if targeting_component.purpose == 'throw' and targeting_component.item:
            aoe = world.get_component(targeting_component.item, AreaOfEffect)
            if aoe:
                target_x, target_y = line_path[min(len(line_path) - 1, target_range)]
                for dx in range(-aoe.radius, aoe.radius + 1):
                    for dy in range(-aoe.radius, aoe.radius + 1):
                        if dx*dx + dy*dy <= aoe.radius*aoe.radius:
                            aoe_x, aoe_y = target_x + dx, target_y + dy
                            indicator = world.create_entity()
                            world.add_component(indicator, Position(aoe_x, aoe_y))
                            world.add_component(indicator, TargetingIndicator(color="red"))
                            self.target_indicators.append(indicator)

        # Check for user input to confirm or cancel
        for event in world.events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:  # Left click
                target_tile_x, target_tile_y = line_path[min(len(line_path) - 1, target_range)]
                
                if targeting_component.purpose == 'throw':
                    world.add_component(player, WantsToThrow(item=targeting_component.item, target_x=target_tile_x, target_y=target_tile_y))
                    world.player_took_turn = True
                    world.turn += 1
                elif targeting_component.purpose == 'shoot':
                    # Find target entity at the location
                    target_entity = next((e for e in world.get_entities_with(Position, Health) if world.get_component(e, Position).x == target_tile_x and world.get_component(e, Position).y == target_tile_y), None)
                    if target_entity:
                        world.add_component(player, WantsToShoot(target=target_entity))
                        world.player_took_turn = True
                        world.turn += 1
                    else:
                        world.log.append("You must target a creature.")
                        return # Don't exit targeting mode, let the player try again.
                elif targeting_component.purpose == 'cast':
                    spell = targeting_component.spell
                    mana = world.get_component(player, Mana)
                    cooldown = world.get_component(player, OnCooldown)

                    if not spell or not mana or not cooldown:
                        world.log.append("You can't cast a spell right now.")
                    elif mana.current < spell.mana_cost:
                        world.log.append("You don't have enough mana.")
                    else:
                        target_entity = next((e for e in world.get_entities_with(Position, Health) if world.get_component(e, Position).x == target_tile_x and world.get_component(e, Position).y == target_tile_y), None)
                        if target_entity:
                            mana.current -= spell.mana_cost
                            cooldown.turns = spell.cooldown
                            world.add_component(player, WantsToCastSpell(target=target_entity))
                            world.player_took_turn = True
                            world.turn += 1
                        else:
                            world.log.append("You must target a creature.")
                            return # Let the player try again without exiting targeting mode.
                world.components[Targeting].pop(player, None) # Exit targeting mode
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                world.log.append("Targeting canceled.")
                world.components[Targeting].pop(player, None) # Exit targeting mode

class NextLevelSystem(System):
    """Handles descending to the next level."""
    def update(self, world: World):
        player = world.player_entity
        if player is None: return

        wants_to_descend = world.get_component(player, WantsToDescend)
        wants_to_ascend = world.get_component(player, WantsToAscend)

        if wants_to_descend or wants_to_ascend:
            world.next_level = True
            world.next_level_target = world.dungeon_level + 1 if wants_to_descend else 0
            # No need to remove the component, the world will be rebuilt.

class DoorSystem(System):
    """Handles opening and closing doors."""
    def update(self, world: World):
        # This system only runs if the player took a turn
        if not world.player_took_turn:
            return

        for entity in list(world.get_entities_with(Door, ToggleDoorState)):
            door = world.get_component(entity, Door)
            renderable = world.get_component(entity, Renderable)
            
            door.is_open = not door.is_open

            if door.is_open:
                world.log.append("You open the door.")
                renderable.char = "'"
                renderable.color = "door_fg_open"
                # Remove blocking components
                if world.get_component(entity, BlocksMovement):
                    del world.components[BlocksMovement][entity]
                if world.get_component(entity, Wall):
                    del world.components[Wall][entity]
            else:
                world.log.append("You close the door.")
                renderable.char = "+"
                renderable.color = "door_fg_closed"
                # Add blocking components
                world.add_component(entity, BlocksMovement())
                world.add_component(entity, Wall())

            # Remove the toggle intent component
            if entity in world.components.get(ToggleDoorState, {}):
                del world.components[ToggleDoorState][entity]

class RangedCombatSystem(System):
    def update(self, world: World):
        for entity in list(world.get_entities_with(WantsToThrow)):
            intent = world.get_component(entity, WantsToThrow)
            if not intent: continue

            item_name = world.get_component(intent.item, Name).name
            user_name = world.get_component(entity, Name).name
            
            world.log.append(f"{user_name} uses a {item_name}!")

            # Find targets in AoE
            aoe = world.get_component(intent.item, AreaOfEffect)
            damage_comp = world.get_component(intent.item, InflictsDamage)
            if not aoe or not damage_comp:
                world.components[WantsToThrow].pop(entity, None)
                continue

            for target_entity in world.get_entities_with(Position, Health, Name):
                if target_entity == entity: continue # Can't hit self
                target_pos = world.get_component(target_entity, Position)
                distance_sq = (target_pos.x - intent.target_x)**2 + (target_pos.y - intent.target_y)**2
                if distance_sq <= aoe.radius**2:
                    target_name = world.get_component(target_entity, Name).name
                    target_health = world.get_component(target_entity, Health)
                    world.log.append(f"The {item_name} hits the {target_name} for {damage_comp.damage} damage!")
                    target_health.current -= damage_comp.damage

            if world.get_component(intent.item, Consumable):
                inventory = world.get_component(entity, Inventory)
                if inventory and intent.item in inventory.items:
                    inventory.items.remove(intent.item)
                    world.destroy_entity(intent.item)
            world.components[WantsToThrow].pop(entity, None)

class ItemUseSystem(System):
    """Handles using items from inventory."""
    def update(self, world: World):
        for entity in list(world.get_entities_with(WantsToUseItem)):
            intent = world.get_component(entity, WantsToUseItem)
            if not intent: continue

            inventory = world.get_component(entity, Inventory)
            if not inventory or intent.item not in inventory.items:
                if entity in world.components.get(WantsToUseItem, {}):
                    del world.components[WantsToUseItem][entity]
                continue

            user_name = world.get_component(entity, Name).name
            item_name = world.get_component(intent.item, Name).name

            # --- Teleportation Logic ---
            teleport_comp = world.get_component(intent.item, ProvidesTeleportation)
            if teleport_comp:
                player_pos = world.get_component(entity, Position)
                if player_pos and world.game_map is not None:
                    # Get all non-blocking floor tiles
                    blocker_locations = {
                        (world.get_component(e, Position).x, world.get_component(e, Position).y)
                        for e in world.get_entities_with(Position, BlocksMovement)
                    }
                    floor_indices_all = np.argwhere(world.game_map == 0)
                    
                    valid_floor_tiles = [
                        (int(x), int(y)) for y, x in floor_indices_all 
                        if (x, y) not in blocker_locations
                    ]

                    if valid_floor_tiles:
                        new_x, new_y = random.choice(valid_floor_tiles)
                        player_pos.x = new_x
                        player_pos.y = new_y
                        world.log.append(f"{user_name} uses a {item_name} and teleports!")
                        
                        # Consume the item
                        inventory.items.remove(intent.item)
                        world.destroy_entity(intent.item)
                    else:
                        world.log.append("The scroll fizzles, there is nowhere to teleport.")
                
                if entity in world.components.get(WantsToUseItem, {}):
                    del world.components[WantsToUseItem][entity]
                continue

            # --- Healing Logic ---
            healing_power = world.get_component(intent.item, ProvidesHealing)
            if healing_power:
                user_health = world.get_component(entity, Health)
                if user_health.current < user_health.max:
                    healed_by = healing_power.amount
                    user_health.current = min(user_health.max, user_health.current + healed_by)
                    world.log.append(f"{user_name} uses a {item_name}, healing for {healed_by} HP.")                    
                    # Consume the item
                    inventory.items.remove(intent.item)
                    world.destroy_entity(intent.item)
                else:
                    world.log.append(f"{user_name} is already at full health.")
            # The intent is removed regardless of whether the item was used.
            # The "can't use" logic is handled in InventorySystem.
            del world.components[WantsToUseItem][entity]

class ItemPickupSystem(System):
    """Handles picking up items by walking over them."""
    def update(self, world: World):
        if world.get_component(world.player_entity, Targeting):
            return

        # This system only runs if the player took a turn, to avoid constant checks
        if not world.player_took_turn:
            return

        # Get all potential item collectors (entities with inventories)
        collectors = world.get_entities_with(Position, Inventory, Name)
        # Create a fast lookup map for item positions
        item_locations = {
            (world.get_component(e, Position).x, world.get_component(e, Position).y): e
            for e in world.get_entities_with(Position, Item, Name)
        }

        if not collectors or not item_locations:
            return

        for collector_entity in collectors:
            collector_pos = world.get_component(collector_entity, Position)
            collector_location = (collector_pos.x, collector_pos.y)

            if collector_location in item_locations:
                item_to_pickup = item_locations[collector_location]
                
                item_name = world.get_component(item_to_pickup, Name).name
                collector_name = world.get_component(collector_entity, Name).name
                world.get_component(collector_entity, Inventory).items.append(item_to_pickup)

                world.log.append(f"{collector_name} picks up the {item_name}.")
                # Убираем предмет с карты, удаляя его позицию. Renderable оставляем, чтобы знать, как его рисовать в инвентаре/при выбрасывании.
                world.components[Position].pop(item_to_pickup, None)
                del item_locations[collector_location]

class TrapSystem(System):
    """Handles triggering traps."""
    def update(self, world: World):
        if not world.player_took_turn:
            return

        potential_victims = world.get_entities_with(Position, Health, Name)
        active_traps = world.get_entities_with(Position, Trap, Hidden)

        trap_locations = {
            (world.get_component(e, Position).x, world.get_component(e, Position).y): e
            for e in active_traps
        }

        for victim_entity in potential_victims:
            victim_pos = world.get_component(victim_entity, Position)
            victim_loc = (victim_pos.x, victim_pos.y)

            if victim_loc in trap_locations:
                trap_entity = trap_locations[victim_loc]
                
                trap_comp = world.get_component(trap_entity, Trap)
                trap_name = world.get_component(trap_entity, Name).name
                victim_name = world.get_component(victim_entity, Name).name
                victim_health = world.get_component(victim_entity, Health)

                world.log.append(f"{victim_name} triggers a {trap_name}!")
                
                trap_renderable = world.get_component(trap_entity, Renderable)
                if trap_renderable:
                    trap_renderable.is_visible = True
                
                if trap_comp.damage > 0:
                    victim_health.current -= trap_comp.damage
                    world.log.append(f"The {trap_name} deals {trap_comp.damage} damage to {victim_name}.")

                poison_effect = world.get_component(trap_entity, InflictsPoison)
                if poison_effect:
                    world.add_component(victim_entity, Poisoned(duration=poison_effect.duration, damage=poison_effect.damage))
                    world.log.append(f"{victim_name} is poisoned!")

                del world.components[Hidden][trap_entity]
                world.add_component(trap_entity, Triggered())
                
                del trap_locations[victim_loc]

class MeleeCombatSystem(System):
    """Разрешает атаки."""
    def update(self, world: World):
        attackers = list(world.get_entities_with(WantsToAttack))

        for entity in attackers:
            intent = world.get_component(entity, WantsToAttack)
            if not intent: continue

            attacker_name = world.get_component(entity, Name).name
            target_name = world.get_component(intent.target, Name).name
            attacker_stats = world.get_component(entity, CombatStats)
            target_stats = world.get_component(intent.target, CombatStats)
            
            if attacker_stats and target_stats:
                # Calculate effective stats including equipment
                attacker_power = attacker_stats.power
                attacker_equipment = world.get_component(entity, Equipment)
                if attacker_equipment:
                    for item_id in attacker_equipment.slots.values():
                        equippable = world.get_component(item_id, Equippable)
                        if equippable:
                            attacker_power += equippable.power_bonus

                target_defense = target_stats.defense
                target_equipment = world.get_component(intent.target, Equipment)
                if target_equipment:
                    for item_id in target_equipment.slots.values():
                        equippable = world.get_component(item_id, Equippable)
                        if equippable:
                            target_defense += equippable.defense_bonus

                damage = max(0, attacker_power - target_defense)
                
                if damage > 0:
                    world.log.append(f"{attacker_name} attacks {target_name} for {damage} hp.")
                    target_health = world.get_component(intent.target, Health)
                    if target_health:
                        target_health.current -= damage
                else:
                    world.log.append(f"{attacker_name} attacks {target_name} but does no damage.")

            if entity in world.components.get(WantsToAttack, {}):
                del world.components[WantsToAttack][entity]

class LevelUpSystem(System):
    """Handles player leveling up."""
    def update(self, world: World):
        player_xp = world.get_component(world.player_entity, Experience)
        if not player_xp:
            return

        if player_xp.current_xp >= player_xp.xp_to_next_level:
            # Level up!
            player_xp.level += 1
            player_xp.current_xp -= player_xp.xp_to_next_level
            player_xp.xp_to_next_level = int(player_xp.xp_to_next_level * 1.5) # Increase next level's requirement

            world.log.append(f"You reached level {player_xp.level}!")

            # Improve stats
            player_health = world.get_component(world.player_entity, Health)
            if player_health:
                player_health.max += 10
                player_health.current = player_health.max # Full heal on level up
                world.log.append("Your health increases!")

            player_mana = world.get_component(world.player_entity, Mana)
            if player_mana:
                player_mana.max += 5
                player_mana.current = player_mana.max # Full mana on level up
                world.log.append("Your mana increases!")

            player_stats = world.get_component(world.player_entity, CombatStats)
            if player_stats:
                player_stats.power += 1
                player_stats.defense += 1
                world.log.append("You feel stronger!")

class DeathSystem(System):
    """Удаляет мертвые сущности и обрабатывает выпадение предметов."""
    def update(self, world: World):
        for entity in list(world.get_entities_with(Health)):
            health = world.get_component(entity, Health)
            if health.current <= 0:
                name = world.get_component(entity, Name).name
                world.log.append(f"{name} dies.")

                # --- Grant Experience ---
                xp_gain = world.get_component(entity, GivesExperience)
                player_xp = world.get_component(world.player_entity, Experience)
                if xp_gain and player_xp:
                    player_xp.current_xp += xp_gain.amount
                    world.log.append(f"You gain {xp_gain.amount} experience points.")
                # --- End Grant Experience ---
                
                # --- New Loot Drop Logic ---
                pos = world.get_component(entity, Position)
                inventory = world.get_component(entity, Inventory)
                if pos and inventory:
                    for item_id in inventory.items:
                        # Remove from being equipped
                        if world.get_component(item_id, Equipped):
                            del world.components[Equipped][item_id]
                        # Add position to drop it on the map
                        world.add_component(item_id, Position(x=pos.x, y=pos.y))
                # --- End Loot Drop Logic ---

                if entity == world.player_entity:
                    world.log.append("GAME OVER")
                    world.running = False
                else:
                    world.destroy_entity(entity)

class DropItemSystem(System):
    """Handles dropping items from inventory."""
    def update(self, world: World):
        for entity in list(world.get_entities_with(WantsToDropItem)):
            intent = world.get_component(entity, WantsToDropItem)
            if not intent: continue

            inventory = world.get_component(entity, Inventory)
            if not inventory or intent.item not in inventory.items:
                del world.components[WantsToDropItem][entity]
                continue

            # Если предмет был экипирован, снимаем его
            equipped = world.get_component(intent.item, Equipped)
            if equipped:
                equipment = world.get_component(entity, Equipment)
                if equipment and equipped.slot in equipment.slots and equipment.slots[equipped.slot] == intent.item:
                    del equipment.slots[equipped.slot]
                del world.components[Equipped][intent.item]

            # Убираем из инвентаря
            inventory.items.remove(intent.item)

            # Возвращаем предмет на карту на позицию игрока
            user_pos = world.get_component(entity, Position)
            world.add_component(intent.item, Position(x=user_pos.x, y=user_pos.y))
            
            item_name = world.get_component(intent.item, Name).name
            world.log.append(f"You drop the {item_name}.")

            del world.components[WantsToDropItem][entity]

class InventorySystem(System):
    """Handles showing the inventory menu and processing user selection."""
    def update(self, world: World):
        player = world.player_entity
        show_inventory = world.get_component(player, ShowInventory)
        if not show_inventory: return

        # В первый кадр, когда меню показывается, просто устанавливаем флаг и ждем ввода в следующем кадре
        if show_inventory.first_frame:
            show_inventory.first_frame = False
            return

        world.player_took_turn = False # Pause the game

        for event in world.events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    del world.components[ShowInventory][player]
                    world.log.append("Action canceled.")
                    return
                
                if pygame.K_a <= event.key <= pygame.K_z:
                    self._handle_item_selection(world, player, show_inventory, event.key)
                    return

    def _handle_item_selection(self, world: World, player: Entity, show_inventory: ShowInventory, key: int):
        inventory = world.get_component(player, Inventory)
        item_index = key - pygame.K_a

        if 0 <= item_index < len(inventory.items):
            selected_item = inventory.items[item_index]
            item_name = world.get_component(selected_item, Name).name

            if show_inventory.purpose == 'use':
                # Use healing potions or teleport scrolls
                if world.get_component(selected_item, ProvidesHealing) or world.get_component(selected_item, ProvidesTeleportation):
                    world.add_component(player, WantsToUseItem(item=selected_item))
                    world.player_took_turn = True
                    world.turn += 1
                else:
                    world.log.append(f"You can't use the {item_name}.")
            elif show_inventory.purpose == 'equip':
                if world.get_component(selected_item, Equippable):
                    world.add_component(player, WantsToEquip(item=selected_item))
                    world.player_took_turn = True
                    world.turn += 1
                else:
                    world.log.append(f"You can't equip the {item_name}.")
            elif show_inventory.purpose == 'drop':
                world.add_component(player, WantsToDropItem(item=selected_item))
                world.player_took_turn = True
                world.turn += 1
            elif show_inventory.purpose == 'throw':
                ranged_comp = world.get_component(selected_item, Ranged)
                if ranged_comp:
                    world.log.append("Select a target. [Left-Click] to throw, [Escape] to cancel.")
                    world.add_component(player, Targeting(range=ranged_comp.range, purpose='throw', item=selected_item))
                else:
                    world.log.append(f"You can't throw the {item_name}.")
         
            del world.components[ShowInventory][player]

class CharacterScreenSystem(System):
    """Handles showing the character screen."""
    def update(self, world: World):
        player = world.player_entity
        if not world.get_component(player, ShowCharacterScreen):
            return

        # В первый кадр, когда экран показывается, просто устанавливаем флаг и ждем ввода в следующем кадре
        show_screen = world.get_component(player, ShowCharacterScreen)
        if show_screen.first_frame:
            show_screen.first_frame = False
            return

        world.player_took_turn = False # Pause the game

        for event in world.events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    del world.components[ShowCharacterScreen][player]
                    return

class HelpScreenSystem(System):
    """Handles showing the help screen."""
    def update(self, world: World):
        player = world.player_entity
        if not world.get_component(player, ShowHelpScreen):
            return

        # В первый кадр, когда экран показывается, просто устанавливаем флаг и ждем ввода в следующем кадре
        show_screen = world.get_component(player, ShowHelpScreen)
        if show_screen.first_frame:
            show_screen.first_frame = False
            return

        world.player_took_turn = False # Pause the game

        for event in world.events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_F1:
                    del world.components[ShowHelpScreen][player]
                    return

class EquipSystem(System):
    """Handles equipping and unequipping items."""
    def update(self, world: World):
        for entity in list(world.get_entities_with(WantsToEquip)):
            intent = world.get_component(entity, WantsToEquip)
            if not intent: continue

            # Entity must have Equipment and Inventory components
            equipment = world.get_component(entity, Equipment)
            inventory = world.get_component(entity, Inventory)
            if not equipment or not inventory:
                del world.components[WantsToEquip][entity]
                continue

            item_to_toggle = intent.item
            equippable = world.get_component(item_to_toggle, Equippable)
            item_name = world.get_component(item_to_toggle, Name).name

            # Check if the item is actually equippable
            if not equippable:
                world.log.append(f"You can't equip the {item_name}.")
                del world.components[WantsToEquip][entity]
                continue

            slot = equippable.slot

            # If the item is already equipped in its slot, unequip it.
            if slot in equipment.slots and equipment.slots[slot] == item_to_toggle:
                del equipment.slots[slot]
                del world.components[Equipped][item_to_toggle]
                world.log.append(f"You unequip the {item_name}.")
            else:
                # If another item is in the slot, unequip it first.
                if slot in equipment.slots:
                    old_item_id = equipment.slots[slot]
                    old_item_name = world.get_component(old_item_id, Name).name
                    world.log.append(f"You unequip the {old_item_name}.")
                    del world.components[Equipped][old_item_id]

                # Equip the new item.
                equipment.slots[slot] = item_to_toggle
                world.add_component(item_to_toggle, Equipped(owner=entity, slot=slot))
                world.log.append(f"You equip the {item_name}.")

            del world.components[WantsToEquip][entity]

class PlayerControlSystem(System):
    def __init__(self):
        self.key_bindings = {
            pygame.K_w: (0, -1),  # Вверх
            pygame.K_s: (0, 1),   # Вниз
            pygame.K_a: (-1, 0),  # Влево
            pygame.K_d: (1, 0),   # Вправо
            # 'o' for open/close is handled separately
        }
    
    def update(self, world: World):
        # Используем прямую ссылку на игрока
        if world.player_entity is None:
            return
        
        # Если открыто какое-либо меню (прицеливание, инвентарь), эта система не работает
        if (world.get_component(world.player_entity, Targeting) or
            world.get_component(world.player_entity, ShowInventory) or
            world.get_component(world.player_entity, ShowCharacterScreen) or
            world.get_component(world.player_entity, ShowHelpScreen)):
            return

        player_vel = world.get_component(world.player_entity, Velocity)
        if not player_vel:
            return

        # Сбрасываем скорость игрока и флаг хода в начале каждого кадра
        player_vel.dx, player_vel.dy = 0, 0
        world.player_took_turn = False

        for event in world.events:
            if event.type == pygame.KEYDOWN:
                action_taken = False
                # Movement
                if event.key in self.key_bindings:
                    dx, dy = self.key_bindings[event.key]
                    player_vel.dx = dx
                    player_vel.dy = dy
                    action_taken = True
                # Wait a turn
                elif event.key == pygame.K_SPACE:
                    world.log.append("You wait a moment.")
                    action_taken = True
                # Actions
                elif event.key == pygame.K_F1:
                    world.add_component(world.player_entity, ShowHelpScreen())
                # This action does not take a turn
                elif event.key == pygame.K_u:
                    inventory = world.get_component(world.player_entity, Inventory)
                    if not inventory or not inventory.items:
                        world.log.append("Your inventory is empty.")
                    else:
                        world.add_component(world.player_entity, ShowInventory(title="Use which item?", purpose='use'))
                elif event.key == pygame.K_t: # Throw
                    inventory = world.get_component(world.player_entity, Inventory)
                    if not inventory or not inventory.items:
                        world.log.append("Your inventory is empty.")
                    else:
                        world.add_component(world.player_entity, ShowInventory(title="Throw which item?", purpose='throw'))
                elif event.key == pygame.K_e: # Equip/Unequip
                    inventory = world.get_component(world.player_entity, Inventory)
                    if not inventory or not inventory.items:
                        world.log.append("Your inventory is empty.")
                    else:
                        world.add_component(world.player_entity, ShowInventory(title="Equip/Unequip which item?", purpose='equip'))
                elif event.key == pygame.K_g: # Drop (g for "give" or "get rid of")
                    inventory = world.get_component(world.player_entity, Inventory)
                    if not inventory or not inventory.items:
                        world.log.append("Your inventory is empty.")
                    else:
                        world.add_component(world.player_entity, ShowInventory(title="Drop which item?", purpose='drop'))
                elif event.key == pygame.K_c: # Character screen
                    world.add_component(world.player_entity, ShowCharacterScreen())
                    # This action does not take a turn
                elif event.key == pygame.K_v: # Cast spell
                    spell = world.get_component(world.player_entity, MagicSpell)
                    cooldown = world.get_component(world.player_entity, OnCooldown)
                    mana = world.get_component(world.player_entity, Mana)
                    if not spell:
                        world.log.append("You don't know any spells.")
                    elif cooldown and cooldown.turns > 0:
                        world.log.append(f"You can't cast {spell.name} yet. Cooldown: {cooldown.turns} turns.")
                    elif mana and mana.current < spell.mana_cost:
                        world.log.append("You don't have enough mana to cast that spell.")
                    else:
                        world.log.append("Select a target. [Left-Click] to cast, [Escape] to cancel.")
                        world.add_component(world.player_entity, Targeting(range=spell.range, purpose='cast', spell=spell))
                    # This action does not take a turn itself, it enters a mode
                elif event.key == pygame.K_f: # Fire
                    equipment = world.get_component(world.player_entity, Equipment)
                    weapon_id = equipment.slots.get(EquipmentSlot.WEAPON) if equipment else None

                    if weapon_id and world.get_component(weapon_id, Ranged) and world.get_component(weapon_id, RequiresAmmunition):
                        ranged_comp = world.get_component(weapon_id, Ranged)
                        world.log.append("Select a target. [Left-Click] to fire, [Escape] to cancel.")
                        world.add_component(world.player_entity, Targeting(range=ranged_comp.range, purpose='shoot'))
                    else:
                        world.log.append("You don't have a ranged weapon equipped.")
                    # This action does not take a turn itself, it enters a mode
                elif event.key == pygame.K_GREATER or (event.key == pygame.K_PERIOD and pygame.key.get_mods() & pygame.KMOD_SHIFT):
                    stairs_locations = {
                        (world.get_component(e, Position).x, world.get_component(e, Position).y): e
                        for e in world.get_entities_with(Position, Stairs)
                    }
                    player_pos = world.get_component(world.player_entity, Position)
                    if (player_pos.x, player_pos.y) in stairs_locations:
                        world.log.append("You descend the stairs...")
                        world.add_component(world.player_entity, WantsToDescend())
                        action_taken = True
                    else:
                        world.log.append("You see no stairs here.")
                        # No turn is taken if there are no stairs

                elif event.key == pygame.K_q:
                    world.running = False
                    return

                if action_taken:
                    world.player_took_turn = True
                    world.turn += 1
                    # Обрабатываем только одно действие за кадр
                    break
                elif event.key == pygame.K_LESS or (event.key == pygame.K_COMMA and pygame.key.get_mods() & pygame.KMOD_SHIFT):
                    stairs_locations = {
                        (world.get_component(e, Position).x, world.get_component(e, Position).y): e
                        for e in world.get_entities_with(Position, StairsUp)
                    }
                    player_pos = world.get_component(world.player_entity, Position)
                    if (player_pos.x, player_pos.y) in stairs_locations:
                        world.log.append("You ascend the stairs...")
                        world.add_component(world.player_entity, WantsToAscend())
                        action_taken = True
                    else:
                        world.log.append("You see no stairs leading up here.")

                if action_taken:
                    world.player_took_turn = True
                    world.turn += 1
                    # Обрабатываем только одно действие за кадр
                    break

class RestingSystem(System):
    def update(self, world: World):
        for entity in list(world.get_entities_with(WantsToRest)):
            health = world.get_component(entity, Health)
            if health:
                health.current = health.max
                world.log.append("You rest and feel refreshed.")
            del world.components[WantsToRest][entity]

class TradingSystem(System):
    def update(self, world: World):
        for entity in list(world.get_entities_with(WantsToTrade)):
            inventory = world.get_component(entity, Inventory)
            if inventory:
                potion = create_healing_potion(world, -1, -1)
                inventory.items.append(potion)
                world.log.append("The merchant gives you a healing potion.")
            del world.components[WantsToTrade][entity]
            # Обрабатываем только одно действие за кадр
            break

@dataclass
class Camera:
    x: int
    y: int
    width: int
    height: int

    def update(self, target_pos: Position, world_cfg: GameConfig):
        # Центрирование камеры на цели (игроке)
        self.x = target_pos.x * world_cfg.cell_size - self.width // 2
        self.y = target_pos.y * world_cfg.cell_size - self.height // 2
        # Ограничение камеры границами мира
        self.x = max(0, min(self.x, world_cfg.grid_width * world_cfg.cell_size - self.width))
        self.y = max(0, min(self.y, world_cfg.grid_height * world_cfg.cell_size - self.height))

class PygameRenderSystem(System):
    def __init__(self, config: GameConfig):
        self.config = config
        pygame.init()
        self.screen = pygame.display.set_mode((config.screen_width, config.screen_height))
        pygame.display.set_caption("ECS Game")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('Arial', 16)
        
        self.colors = {
            'black': (0, 0, 0),
            'red': (255, 0, 0),
            'green': (0, 255, 0),
            'dark_green': (0, 100, 0),
            'yellow': (255, 255, 0),
            'log_text': (200, 200, 200),
            'blue': (0, 0, 255),
            'white': (255, 255, 255),
            'gray': (50, 50, 50),
            'silver': (192, 192, 192),
            'fog_explored': (25, 25, 25),
            'wall_fg': (130, 110, 90),
            'cyan': (0, 255, 255),
            'brown': (139, 69, 19),
            'door_fg_closed': (150, 110, 50),
            'door_fg_open': (255, 255, 150),
            'fog_unseen': (0, 0, 0),
        }
        
        # Кэш для рендеринга текста
        self.text_cache: Dict[Tuple[str, str], pygame.Surface] = {}
        # Определяем высоту игрового поля, исключая инфо-панель
        game_viewport_height = config.screen_height - config.info_panel_height
        self.camera = Camera(0, 0, config.screen_width, game_viewport_height)

    def update(self, world: World):
        # Обновляем камеру, чтобы она следовала за игроком, ПЕРЕД отрисовкой
        if world.player_entity is not None:
            player_pos = world.get_component(world.player_entity, Position)
            if player_pos:
                self.camera.update(player_pos, world.config)

        self.screen.fill(self.colors['black'])
        
        self.draw_grid(world)
        self.draw_entities(world)
        self.draw_info_panel(world)

        # Отрисовываем элементы интерфейса поверх игрового мира
        self.draw_inventory_menu(world)
        self.draw_character_screen(world)
        self.draw_help_screen(world)

        pygame.display.flip()
        self.clock.tick(self.config.fps)


    def draw_grid(self, world: World):
        grid_color = self.colors['gray']
        cs = self.config.cell_size
        cam = self.camera

        # Определяем, какая часть карты на экране
        start_col = self.camera.x // cs
        end_col = (self.camera.x + self.camera.width) // cs + 2
        start_row = self.camera.y // cs
        end_row = (self.camera.y + self.camera.height) // cs + 2

        color_visible_border = self.colors['gray']
        color_explored = self.colors['fog_explored']
        color_unseen = self.colors['black']

        for y in range(start_row, end_row):
            for x in range(start_col, end_col):
                if not (0 <= x < world.config.grid_width and 0 <= y < world.config.grid_height):
                    continue

                visibility = world.visibility_map[y, x]
                screen_x = x * cs - cam.x
                screen_y = y * cs - cam.y
                rect = pygame.Rect(screen_x, screen_y, cs, cs)

                if visibility == 2:  # Видимая клетка
                    pygame.draw.rect(self.screen, color_visible_border, rect, 1)
                elif visibility == 1:  # Исследованная клетка
                    pygame.draw.rect(self.screen, color_explored, rect)
                else:  # Невидимая клетка
                    pygame.draw.rect(self.screen, color_unseen, rect)

    def draw_entities(self, world: World):
        cs = self.config.cell_size
        half_cs = cs // 2

        entities_to_render = world.get_entities_with(Position, Renderable)

        for entity in entities_to_render:
            pos = world.get_component(entity, Position)
            render = world.get_component(entity, Renderable)

            if not render.is_visible: continue

            visibility = world.visibility_map[pos.y, pos.x]
            is_mobile = world.get_component(entity, Velocity) is not None
            color = self.colors.get(render.color.lower(), self.colors['white'])

            if visibility == 2: # Видимая клетка
                pass # Отрисовка в обычном цвете
            elif visibility == 1 and not is_mobile: # Исследованная и статичная
                r, g, b = color
                color = (r // 2, g // 2, b // 2) # Тусклый цвет
            else: # Невидимая или неисследованная
                continue

            screen_x = pos.x * cs - self.camera.x
            screen_y = pos.y * cs - self.camera.y

            if not (0 <= screen_x < self.camera.width and 0 <= screen_y < self.camera.height):
                continue

            # Отрисовываем все сущности как текст, используя их символ.
            # Ключ кэша должен включать итоговый цвет, т.к. он может быть затемнен.
            cache_key = (render.char, color)
            if cache_key not in self.text_cache:
                self.text_cache[cache_key] = self.font.render(render.char, True, color)
            text_surface = self.text_cache[cache_key]
            self.screen.blit(text_surface, text_surface.get_rect(center=(screen_x + half_cs, screen_y + half_cs)))

        # --- Draw targeting indicators on top ---
        for entity in world.get_entities_with(Position, TargetingIndicator):
            pos = world.get_component(entity, Position)
            indicator = world.get_component(entity, TargetingIndicator)
            
            screen_x = pos.x * cs - self.camera.x
            screen_y = pos.y * cs - self.camera.y

            if not (0 <= screen_x < self.camera.width and 0 <= screen_y < self.camera.height):
                continue
            
            color = self.colors.get(indicator.color.lower(), self.colors['white'])
            rect_surface = pygame.Surface((cs, cs), pygame.SRCALPHA)
            rect_surface.fill((*color, 100))
            self.screen.blit(rect_surface, (screen_x, screen_y))

    def draw_info_panel(self, world: World):
        panel_y = self.config.screen_height - self.config.info_panel_height
        panel = pygame.Rect(0, panel_y, 
                           self.config.screen_width, 
                           self.config.info_panel_height)
        
        pygame.draw.rect(self.screen, self.colors['gray'], panel)
        
        # --- Отрисовка лога ---
        log_y_start = panel_y + 5
        log_x_start = 20
        log_messages = world.log[-5:] # Показываем последние 5 сообщений
        for i, msg in enumerate(log_messages):
            log_surface = self.font.render(msg, True, self.colors['log_text'])
            self.screen.blit(log_surface, (log_x_start, log_y_start + i * 20))

    def draw_inventory_menu(self, world: World):
        show_inventory = world.get_component(world.player_entity, ShowInventory)
        if not show_inventory:
            return

        inventory = world.get_component(world.player_entity, Inventory)
        if not inventory or not inventory.items:
            return

        num_items = len(inventory.items)
        menu_width = 450
        menu_height = (num_items + 2) * 25
        menu_x = (self.config.screen_width - menu_width) // 2
        menu_y = (self.config.screen_height - self.config.info_panel_height - menu_height) // 2

        # Рисуем фон и рамку меню
        menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, self.colors['black'], menu_rect)
        pygame.draw.rect(self.screen, self.colors['white'], menu_rect, 2)

        # Рисуем заголовок
        title_surface = self.font.render(show_inventory.title, True, self.colors['yellow'])
        self.screen.blit(title_surface, (menu_x + 10, menu_y + 10))

        # Рисуем предметы
        y_offset = 35
        for i, item_id in enumerate(inventory.items):
            item_char = chr(ord('a') + i)
            item_name = world.get_component(item_id, Name).name
            item_info = " (equipped)" if world.get_component(item_id, Equipped) else ""
            item_text = f"({item_char}) {item_name}{item_info}"
            item_surface = self.font.render(item_text, True, self.colors['white'])
            self.screen.blit(item_surface, (menu_x + 15, menu_y + y_offset))
            y_offset += 25

    def draw_character_screen(self, world: World):
        if not world.get_component(world.player_entity, ShowCharacterScreen):
            return

        menu_width = 550
        menu_height = 500
        menu_x = (self.config.screen_width - menu_width) // 2
        menu_y = (self.config.screen_height - self.config.info_panel_height - menu_height) // 2

        # Draw menu background and border
        menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, self.colors['black'], menu_rect)
        pygame.draw.rect(self.screen, self.colors['white'], menu_rect, 2)

        # Title
        title_surface = self.font.render("Character Information (Press ESC to close)", True, self.colors['yellow'])
        self.screen.blit(title_surface, (menu_x + 10, menu_y + 10))

        # --- Prepare info texts ---
        info_texts = []
        y_offset = 40

        # Level and XP
        player_xp = world.get_component(world.player_entity, Experience)
        if player_xp:
            info_texts.append(f"Level: {player_xp.level}")
            info_texts.append(f"Experience: {player_xp.current_xp} / {player_xp.xp_to_next_level}")
        
        # HP
        player_health = world.get_component(world.player_entity, Health)
        if player_health:
            info_texts.append(f"Health: {player_health.current} / {player_health.max}")
        
        # Mana
        player_mana = world.get_component(world.player_entity, Mana)
        if player_mana:
            info_texts.append(f"Mana:   {player_mana.current} / {player_mana.max}")

        info_texts.append("") # Spacer

        # Stats
        player_stats = world.get_component(world.player_entity, CombatStats)
        if player_stats:
            power_base, defense_base = player_stats.power, player_stats.defense
            power_bonus, defense_bonus = 0, 0
            
            equipment = world.get_component(world.player_entity, Equipment)
            if equipment:
                for item_id in equipment.slots.values():
                    equippable = world.get_component(item_id, Equippable)
                    if equippable:
                        power_bonus += equippable.power_bonus
                        defense_bonus += equippable.defense_bonus
            
            info_texts.append(f"Power: {power_base + power_bonus} ({power_base} +{power_bonus})")
            info_texts.append(f"Defense: {defense_base + defense_bonus} ({defense_base} +{defense_bonus})")
        
        info_texts.append(f"Dungeon Level: {world.dungeon_level}")
        info_texts.append("") # Spacer

        # Equipped items
        info_texts.append("Equipped Items:")
        player_equipment = world.get_component(world.player_entity, Equipment)
        if player_equipment and player_equipment.slots:
            for slot, item_id in sorted(player_equipment.slots.items(), key=lambda item: item[0].name):
                item_name = world.get_component(item_id, Name).name
                info_texts.append(f"  {slot.name.capitalize()}: {item_name}")
        else:
            info_texts.append("  (nothing equipped)")
        info_texts.append("") # Spacer

        # Inventory
        info_texts.append("Inventory:")
        player_inventory = world.get_component(world.player_entity, Inventory)
        if player_inventory:
            unequipped_items = [
                item_id for item_id in player_inventory.items
                if not world.get_component(item_id, Equipped)
            ]
            if unequipped_items:
                for item_id in unequipped_items:
                    item_name = world.get_component(item_id, Name).name
                    info_texts.append(f"  - {item_name}")
            else:
                info_texts.append("  (empty)")
        else:
            info_texts.append("  (empty)")

        # --- Render info texts ---
        for text in info_texts:
            text_surface = self.font.render(text, True, self.colors['white'])
            self.screen.blit(text_surface, (menu_x + 15, menu_y + y_offset))
            y_offset += 20

    def draw_help_screen(self, world: World):
        if not world.get_component(world.player_entity, ShowHelpScreen):
            return

        menu_width = 600
        menu_height = 500
        menu_x = (self.config.screen_width - menu_width) // 2
        menu_y = (self.config.screen_height - self.config.info_panel_height - menu_height) // 2

        # Draw menu background and border
        menu_rect = pygame.Rect(menu_x, menu_y, menu_width, menu_height)
        pygame.draw.rect(self.screen, self.colors['black'], menu_rect)
        pygame.draw.rect(self.screen, self.colors['white'], menu_rect, 2)

        # Title
        title_surface = self.font.render("Help (Press F1 or ESC to close)", True, self.colors['yellow'])
        self.screen.blit(title_surface, (menu_x + 10, menu_y + 10))

        # --- Prepare help texts ---
        help_texts = [
            "== Movement ==",
            "W, A, S, D: Move",
            "Space: Wait a turn",
            "Bump into doors to open/close them.",
            "Bump into enemies to attack.",
            "Bump into NPCs to interact.",
            "",
            "== Actions ==",
            "U: Use item from inventory",
            "T: Throw item from inventory",
            "E: Equip/Unequip item",
            "G: Drop item from inventory",
            "V: Cast a spell",
            "F: Fire equipped ranged weapon",
            "",
            "== World Interaction ==",
            "> (Shift + .): Descend stairs",
            "< (Shift + ,): Ascend stairs/return to town",
            "",
            "== UI ==",
            "C: View character screen",
            "F1: Show this help screen",
            "Q: Quit game",
            "ESC: Cancel targeting or close menus",
            "Left Mouse Click: Confirm target",
        ]
        
        y_offset = 40
        # --- Render help texts ---
        for text in help_texts:
            text_surface = self.font.render(text, True, self.colors['white'])
            self.screen.blit(text_surface, (menu_x + 15, menu_y + y_offset))
            y_offset += 20