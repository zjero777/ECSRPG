import random
from ecs import World, Entity
from components import (Position, Velocity, Renderable, Health, Player, Enemy, BlocksMovement, Wall, CombatStats, Name, Item, Inventory, Consumable, ProvidesHealing, Door, Experience, GivesExperience, Stairs, Ranged, AreaOfEffect, InflictsDamage,
                        ProvidesTeleportation, StairsUp, ProvidesFullHealing, ProvidesSupplies)
from components import (Equipment, Equippable, EquipmentSlot, Equipped, Trap, Hidden, InflictsPoison, MagicSpell, OnCooldown, Mana,
                        Ammunition, RequiresAmmunition)

def create_player(world: World, x: int, y: int) -> Entity:
    player = world.create_entity()
    world.add_component(player, Position(x, y))
    world.add_component(player, Velocity())
    world.add_component(player, Renderable("@", "red"))
    world.add_component(player, Health(50, 50))
    world.add_component(player, Player())
    world.add_component(player, BlocksMovement())
    world.add_component(player, Inventory())
    world.add_component(player, Equipment())
    world.add_component(player, CombatStats(power=5, defense=2))
    world.add_component(player, Name("Player"))
    world.add_component(player, Experience(level=1, current_xp=0, xp_to_next_level=100, max_dungeon_level=1))
    world.add_component(player, Mana(current=20, max=20))
    world.add_component(player, MagicSpell(name="Magic Missile", damage=6, range=5, cooldown=2, mana_cost=4))
    world.add_component(player, OnCooldown(turns=0))
    world.player_entity = player # Сохраняем ссылку на игрока
    return player

def create_goblin(world: World, x: int, y: int) -> Entity:
    enemy = world.create_entity()
    world.add_component(enemy, Position(x, y))
    world.add_component(enemy, Velocity())
    world.add_component(enemy, Renderable("g", "green"))
    world.add_component(enemy, Health(10, 10))
    world.add_component(enemy, Enemy())
    world.add_component(enemy, BlocksMovement())
    world.add_component(enemy, CombatStats(power=3, defense=0))
    world.add_component(enemy, Name("Goblin"))
    world.add_component(enemy, GivesExperience(amount=35))

    # --- Equipment and Inventory Logic for Goblin ---
    inventory = Inventory()
    equipment = Equipment()
    world.add_component(enemy, inventory)
    world.add_component(enemy, equipment)

    # 25% chance to have a dagger
    if random.random() < 0.25:
        dagger = create_dagger(world, -1, -1)
        world.components[Position].pop(dagger, None)
        inventory.items.append(dagger)
        equipment.slots[EquipmentSlot.WEAPON] = dagger
        world.add_component(dagger, Equipped(owner=enemy, slot=EquipmentSlot.WEAPON))

    # 15% chance to have leather armor
    if random.random() < 0.15:
        armor = create_leather_armor(world, -1, -1)
        world.components[Position].pop(armor, None)
        inventory.items.append(armor)
        equipment.slots[EquipmentSlot.ARMOR] = armor
        world.add_component(armor, Equipped(owner=enemy, slot=EquipmentSlot.ARMOR))

    # 10% chance to have a healing potion
    if random.random() < 0.10:
        potion = create_healing_potion(world, -1, -1)
        world.components[Position].pop(potion, None) # Remove position, item is in inventory
        inventory.items.append(potion)

    return enemy

def create_orc(world: World, x: int, y: int) -> Entity:
    enemy = world.create_entity()
    world.add_component(enemy, Position(x, y))
    world.add_component(enemy, Velocity())
    world.add_component(enemy, Renderable("o", "dark_green"))
    world.add_component(enemy, Health(16, 16))
    world.add_component(enemy, Enemy())
    world.add_component(enemy, BlocksMovement())
    world.add_component(enemy, CombatStats(power=4, defense=1))
    world.add_component(enemy, Name("Orc"))
    world.add_component(enemy, GivesExperience(amount=100))

    # --- Equipment and Inventory Logic for Orc ---
    inventory = Inventory()
    equipment = Equipment()
    world.add_component(enemy, inventory)
    world.add_component(enemy, equipment)

    # 50% chance to have a sword
    if random.random() < 0.50:
        sword = create_sword(world, -1, -1)
        world.components[Position].pop(sword, None)
        inventory.items.append(sword)
        equipment.slots[EquipmentSlot.WEAPON] = sword
        world.add_component(sword, Equipped(owner=enemy, slot=EquipmentSlot.WEAPON))

    # 30% chance to have chain mail
    if random.random() < 0.30:
        armor = create_chain_mail(world, -1, -1)
        world.components[Position].pop(armor, None)
        inventory.items.append(armor)
        equipment.slots[EquipmentSlot.ARMOR] = armor
        world.add_component(armor, Equipped(owner=enemy, slot=EquipmentSlot.ARMOR))

    # 25% chance to have a healing potion
    if random.random() < 0.25:
        potion = create_healing_potion(world, -1, -1)
        world.components[Position].pop(potion, None) # Remove position, item is in inventory
        inventory.items.append(potion)

    return enemy

def create_skeleton(world: World, x: int, y: int) -> Entity:
    enemy = world.create_entity()
    world.add_component(enemy, Position(x, y))
    world.add_component(enemy, Velocity())
    world.add_component(enemy, Renderable("s", "white"))
    world.add_component(enemy, Health(12, 12))
    world.add_component(enemy, Enemy())
    world.add_component(enemy, BlocksMovement())
    world.add_component(enemy, CombatStats(power=4, defense=1))
    world.add_component(enemy, Name("Skeleton"))
    world.add_component(enemy, GivesExperience(amount=50))
    # Skeletons are simple, no inventory for now.
    return enemy

def create_mage(world: World, x: int, y: int) -> Entity:
    enemy = world.create_entity()
    world.add_component(enemy, Position(x, y))
    world.add_component(enemy, Velocity())
    world.add_component(enemy, Renderable("M", "magenta"))
    world.add_component(enemy, Health(12, 12))
    world.add_component(enemy, Enemy())
    world.add_component(enemy, BlocksMovement())
    world.add_component(enemy, CombatStats(power=2, defense=1)) # Weak in melee
    world.add_component(enemy, Name("Mage"))
    world.add_component(enemy, GivesExperience(amount=150))
    world.add_component(enemy, Mana(current=30, max=30))
    world.add_component(enemy, MagicSpell(name="Magic Missile", damage=8, range=6, cooldown=3, mana_cost=5))
    world.add_component(enemy, OnCooldown(turns=0))
    # Mages don't typically carry loot, but could add a scroll or potion chance
    return enemy

def create_healing_potion(world: World, x: int, y: int) -> Entity:
    item = world.create_entity()
    world.add_component(item, Position(x, y))
    world.add_component(item, Renderable("!", "yellow"))
    world.add_component(item, Item())
    world.add_component(item, Name("Healing Potion"))
    world.add_component(item, Consumable())
    world.add_component(item, ProvidesHealing(amount=10))
    return item

def create_teleport_scroll(world: World, x: int, y: int) -> Entity:
    scroll = world.create_entity()
    world.add_component(scroll, Position(x, y))
    world.add_component(scroll, Renderable("~", "magenta"))
    world.add_component(scroll, Name("Teleportation Scroll"))
    world.add_component(scroll, Item())
    world.add_component(scroll, Consumable())
    world.add_component(scroll, ProvidesTeleportation())
    return scroll

def create_fireball_scroll(world: World, x: int, y: int) -> Entity:
    scroll = world.create_entity()
    world.add_component(scroll, Position(x, y))
    world.add_component(scroll, Renderable("~", "red"))
    world.add_component(scroll, Name("Fireball Scroll"))
    world.add_component(scroll, Item())
    world.add_component(scroll, Consumable())
    world.add_component(scroll, Ranged(range=6))
    world.add_component(scroll, AreaOfEffect(radius=3))
    world.add_component(scroll, InflictsDamage(damage=12))
    return scroll

def create_sword(world: World, x: int, y: int) -> Entity:
    item = world.create_entity()
    world.add_component(item, Position(x, y))
    world.add_component(item, Renderable("/", "cyan"))
    world.add_component(item, Item())
    world.add_component(item, Name("Sword"))
    world.add_component(item, Equippable(slot=EquipmentSlot.WEAPON, power_bonus=2))
    return item

def create_dagger(world: World, x: int, y: int) -> Entity:
    item = world.create_entity()
    world.add_component(item, Position(x, y))
    world.add_component(item, Renderable("/", "gray"))
    world.add_component(item, Item())
    world.add_component(item, Name("Dagger"))
    world.add_component(item, Equippable(slot=EquipmentSlot.WEAPON, power_bonus=1))
    return item

def create_leather_armor(world: World, x: int, y: int) -> Entity:
    item = world.create_entity()
    world.add_component(item, Position(x, y))
    world.add_component(item, Renderable("[", "brown"))
    world.add_component(item, Item())
    world.add_component(item, Name("Leather Armor"))
    world.add_component(item, Equippable(slot=EquipmentSlot.ARMOR, defense_bonus=1))
    return item

def create_chain_mail(world: World, x: int, y: int) -> Entity:
    item = world.create_entity()
    world.add_component(item, Position(x, y))
    world.add_component(item, Renderable("[", "silver"))
    world.add_component(item, Item())
    world.add_component(item, Name("Chain Mail"))
    world.add_component(item, Equippable(slot=EquipmentSlot.ARMOR, defense_bonus=2))
    return item

def create_bow(world: World, x: int, y: int) -> Entity:
    item = world.create_entity()
    world.add_component(item, Position(x, y))
    world.add_component(item, Renderable("}", "brown"))
    world.add_component(item, Item())
    world.add_component(item, Name("Bow"))
    world.add_component(item, Equippable(slot=EquipmentSlot.WEAPON, power_bonus=0)) # No melee bonus
    world.add_component(item, Ranged(range=6))
    world.add_component(item, RequiresAmmunition(ammo_type="Arrow"))
    return item

def create_arrow(world: World, x: int, y: int) -> Entity:
    item = world.create_entity()
    world.add_component(item, Position(x, y))
    world.add_component(item, Renderable("-", "silver"))
    world.add_component(item, Item())
    world.add_component(item, Name("Arrow"))
    world.add_component(item, Consumable())
    world.add_component(item, Ammunition(ammo_type="Arrow"))
    world.add_component(item, InflictsDamage(damage=4)) # Damage is on the arrow
    return item

def create_wall(world: World, x: int, y: int) -> Entity:
    wall = world.create_entity()
    world.add_component(wall, Position(x, y))
    world.add_component(wall, Renderable("#", "wall_fg"))
    world.add_component(wall, BlocksMovement())
    world.add_component(wall, Wall())
    return wall

def create_door(world: World, x: int, y: int, is_open: bool = False) -> Entity:
    door = world.create_entity()
    world.add_component(door, Position(x, y))
    world.add_component(door, Door(is_open=is_open))
    world.add_component(door, Name("Door"))
    if is_open:
        world.add_component(door, Renderable("'", "door_fg_open"))
    else:
        world.add_component(door, Renderable("+", "door_fg_closed"))
        world.add_component(door, BlocksMovement())
        world.add_component(door, Wall()) # Closed doors block sight
    return door

def create_stairs(world: World, x: int, y: int) -> Entity:
    stairs = world.create_entity()
    world.add_component(stairs, Position(x, y))
    world.add_component(stairs, Renderable(">", "white"))
    world.add_component(stairs, Name("Stairs to the next level"))
    world.add_component(stairs, Stairs())
    return stairs

def create_up_stairs(world: World, x: int, y: int) -> Entity:
    stairs = world.create_entity()
    world.add_component(stairs, Position(x, y))
    world.add_component(stairs, Renderable("<", "white"))
    world.add_component(stairs, Name("Stairs to the town"))
    world.add_component(stairs, StairsUp())
    return stairs

def create_innkeeper(world: World, x: int, y: int) -> Entity:
    npc = world.create_entity()
    world.add_component(npc, Position(x, y))
    world.add_component(npc, Renderable("H", "yellow"))
    world.add_component(npc, Name("Innkeeper"))
    world.add_component(npc, BlocksMovement())
    world.add_component(npc, ProvidesFullHealing())
    return npc

def create_merchant(world: World, x: int, y: int) -> Entity:
    npc = world.create_entity()
    world.add_component(npc, Position(x, y))
    world.add_component(npc, Renderable("$", "green"))
    world.add_component(npc, Name("Merchant"))
    world.add_component(npc, BlocksMovement())
    world.add_component(npc, ProvidesSupplies())
    return npc

def create_damage_trap(world: World, x: int, y: int) -> Entity:
    trap = world.create_entity()
    world.add_component(trap, Position(x, y))
    world.add_component(trap, Renderable("^", "magenta", is_visible=False))
    world.add_component(trap, Name("Spike Trap"))
    world.add_component(trap, Trap(damage=10))
    world.add_component(trap, Hidden())
    return trap

def create_poison_trap(world: World, x: int, y: int) -> Entity:
    trap = world.create_entity()
    world.add_component(trap, Position(x, y))
    world.add_component(trap, Renderable("^", "dark_green", is_visible=False))
    world.add_component(trap, Name("Poison Dart Trap"))
    world.add_component(trap, Trap(damage=1)) # Small initial damage
    world.add_component(trap, InflictsPoison(damage=2, duration=5))
    world.add_component(trap, Hidden())
    return trap