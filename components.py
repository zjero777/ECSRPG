from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Callable, Tuple, Dict
from enum import Enum, auto
if TYPE_CHECKING:
    from ecs import Entity, World

# Компоненты - чистые данные
@dataclass
class Position:
    x: int
    y: int

@dataclass
class Velocity:
    dx: int = 0
    dy: int = 0

@dataclass
class Renderable:
    char: str
    color: str
    is_visible: bool = True

@dataclass
class Health:
    current: int
    max: int

@dataclass
class Player:
    pass

@dataclass
class Enemy:
    pass

@dataclass
class BlocksMovement:
    pass

@dataclass
class Wall:
    pass

@dataclass
class CombatStats:
    power: int
    defense: int

@dataclass
class WantsToAttack:
    target: Entity

@dataclass
class Name:
    name: str

@dataclass
class Item:
    pass

@dataclass
class Inventory:
    items: List[Entity] = field(default_factory=list)

@dataclass
class Consumable:
    pass

@dataclass
class ProvidesHealing:
    amount: int

@dataclass
class ProvidesTeleportation:
    pass

@dataclass
class WantsToUseItem:
    item: Entity

@dataclass
class Door:
    is_open: bool = False

@dataclass
class ToggleDoorState:
    # Marker component added to a door to signal it should be toggled.
    pass

@dataclass
class Experience:
    level: int = 1
    current_xp: int = 0
    xp_to_next_level: int = 100
    max_dungeon_level: int = 1


@dataclass
class GivesExperience:
    amount: int

@dataclass
class Stairs:
    pass

@dataclass
class StairsUp:
    pass

@dataclass
class WantsToDescend:
    pass

@dataclass
class Ranged:
    range: int

@dataclass
class AreaOfEffect:
    radius: int

@dataclass
class InflictsDamage:
    damage: int

@dataclass
class Targeting:
    range: int
    purpose: str  # 'throw', 'shoot', or 'cast'
    item: Entity | None = None # For throwing items
    spell: MagicSpell | None = None # For casting spells

@dataclass
class WantsToShoot:
    target: Entity

@dataclass
class Mana:
    current: int
    max: int

@dataclass
class WantsToCastSpell:
    target: Entity

@dataclass
class MagicSpell:
    name: str
    damage: int
    range: int
    cooldown: int
    mana_cost: int

@dataclass
class OnCooldown:
    turns: int

@dataclass
class WantsToThrow:
    item: Entity
    target_x: int
    target_y: int

@dataclass
class TargetingIndicator:
    color: str

@dataclass
class Projectile:
    path: List[Tuple[int, int]]

class EquipmentSlot(Enum):
    WEAPON = auto()
    ARMOR = auto()

@dataclass
class Equippable:
    slot: EquipmentSlot
    power_bonus: int = 0
    defense_bonus: int = 0

@dataclass
class Equipped:
    owner: Entity
    slot: EquipmentSlot

@dataclass
class Equipment:
    # Maps slot to the equipped entity
    slots: Dict[EquipmentSlot, Entity] = field(default_factory=dict)

@dataclass
class WantsToEquip:
    item: Entity

@dataclass
class WantsToDropItem:
    item: Entity

@dataclass
class ShowInventory:
    """Сигнализирует о том, что нужно показать инвентарь для выбора предмета."""
    title: str
    purpose: str  # 'use', 'equip', 'drop', 'throw'
    first_frame: bool = True

@dataclass
class ShowCharacterScreen:
    """Сигнализирует о том, что нужно показать экран персонажа."""
    first_frame: bool = True

@dataclass
class ShowHelpScreen:
    """Сигнализирует о том, что нужно показать экран помощи."""
    first_frame: bool = True

@dataclass
class WantsToFlee:
    """Сигнализирует о том, что сущность хочет убежать."""
    pass

@dataclass
class Trap:
    damage: int = 0

@dataclass
class Hidden:
    pass

@dataclass
class Triggered:
    pass

@dataclass
class InflictsPoison:
    damage: int = 1
    duration: int = 5

@dataclass
class Poisoned:
    duration: int
    damage: int

@dataclass
class WantsToAscend:
    pass

@dataclass
class ProvidesFullHealing:
    pass

@dataclass
class WantsToRest:
    pass

@dataclass
class ProvidesSupplies:
    pass

@dataclass
class WantsToTrade:
    pass

@dataclass
class Ammunition:
    ammo_type: str

@dataclass
class RequiresAmmunition:
    ammo_type: str