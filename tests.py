import unittest
import os
import sys
import unittest.mock as mock

import numpy as np
# Мокаем pygame перед его импортом игровыми модулями.
# Это предотвращает ModuleNotFoundError, если pygame не установлен в тестовом
# окружении или при запуске на системе без дисплея.
sys.modules['pygame'] = mock.Mock()
sys.modules['pygame.event'] = mock.Mock()

# Теперь, когда pygame замокан, мы можем его импортировать для доступа к константам
import pygame

# Добавляем корневую папку проекта в путь, чтобы можно было импортировать модули игры
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from config import GameConfig
from game_state import GameState
from ecs import World
from systems import (MovementSystem, MeleeCombatSystem, DeathSystem, ItemPickupSystem, RangedCombatSystem, MagicSystem,
                     ItemUseSystem, EquipSystem, DropItemSystem, LevelUpSystem, RestingSystem, TradingSystem, PygameRenderSystem,
                     PoisonSystem, TrapSystem, NextLevelSystem, EnemyAISystem, DoorSystem, ShootingSystem, TargetingSystem,
                     ProjectileSystem)
from entities import (create_player, create_goblin, create_healing_potion, create_sword, create_innkeeper, create_merchant, create_orc, create_mage,
                      create_wall, create_damage_trap, create_poison_trap, create_door, create_leather_armor, create_bow,
                      create_arrow, create_fireball_scroll, create_teleport_scroll)
from components import (Position, Velocity, Health, WantsToAttack, Name, Item, Inventory,
                        WantsToUseItem, ProvidesHealing, WantsToEquip, Equippable, MagicSpell, OnCooldown, WantsToCastSpell, Mana,
                        EquipmentSlot, Equipped, Equipment, WantsToDropItem, Experience, WantsToRest, WantsToTrade, Enemy, Targeting,
                        GivesExperience, Poisoned, WantsToDescend, Hidden, Door, ToggleDoorState,
                        BlocksMovement, CombatStats, WantsToShoot, WantsToThrow, Ranged, AreaOfEffect,
                        InflictsDamage, Projectile, Ammunition, RequiresAmmunition, ProvidesTeleportation)
from main import extract_player_data, generate_world, recreate_player_in_world
from level_themes import GOBLIN_CAVES

class TestGameMechanics(unittest.TestCase):

    def setUp(self):
        """Настраивает новый мир и конфигурацию для каждого теста."""
        self.config = GameConfig()
        # Уменьшаем размер сетки для ускорения тестов
        self.config.grid_width = 20
        self.config.grid_height = 20
        self.game_state = GameState()
        self.world = World(self.config, self.game_state)
        # В тестах мы вручную устанавливаем этот флаг, чтобы симулировать ход
        self.world.player_took_turn = True

    def run_system(self, system):
        """Вспомогательная функция для запуска одной системы."""
        system.update(self.world)

    def test_movement_and_collision(self):
        """Тестирует движение игрока и столкновения с объектами."""
        player = create_player(self.world, 5, 5)
        wall = create_wall(self.world, 5, 6)
        goblin = create_goblin(self.world, 6, 5)
        door = create_door(self.world, 5, 4, is_open=False)

        movement_system = MovementSystem()
        player_pos = self.world.get_component(player, Position)
        player_vel = self.world.get_component(player, Velocity)

        # 1. Попытка движения в стену
        player_vel.dy = 1
        self.run_system(movement_system)
        self.assertEqual((player_pos.x, player_pos.y), (5, 5), "Игрок не должен проходить сквозь стены")

        # 2. Попытка движения во врага (должна инициировать атаку)
        player_vel.dx, player_vel.dy = 1, 0
        self.run_system(movement_system)
        self.assertEqual((player_pos.x, player_pos.y), (5, 5), "Игрок не должен двигаться на врага, а атаковать")
        self.assertIsNotNone(self.world.get_component(player, WantsToAttack), "Игрок должен хотеть атаковать врага")
        self.world.components[WantsToAttack].pop(player) # Очищаем для следующего теста

        # 3. Попытка движения в закрытую дверь (должна инициировать открытие)
        player_vel.dx, player_vel.dy = 0, -1
        self.run_system(movement_system)
        self.assertEqual((player_pos.x, player_pos.y), (5, 5), "Игрок не должен проходить сквозь закрытую дверь")
        self.assertIsNotNone(self.world.get_component(door, ToggleDoorState), "Дверь должна получить намерение на открытие/закрытие")

        # 4. Успешное движение в пустую клетку
        player_vel.dx, player_vel.dy = -1, 0
        self.run_system(movement_system)
        self.assertEqual((player_pos.x, player_pos.y), (4, 5), "Игрок должен был переместиться в пустую клетку")

    def test_door_system(self):
        """Тестирует открытие и закрытие дверей."""
        door_entity = create_door(self.world, 5, 5, is_open=False)
        self.assertIsNotNone(self.world.get_component(door_entity, BlocksMovement))

        door_system = DoorSystem()
        self.world.add_component(door_entity, ToggleDoorState())
        self.run_system(door_system)

        door_comp = self.world.get_component(door_entity, Door)
        self.assertTrue(door_comp.is_open, "Дверь должна была открыться")
        self.assertIsNone(self.world.get_component(door_entity, BlocksMovement), "Открытая дверь не должна блокировать движение")
        self.assertIsNone(self.world.get_component(door_entity, ToggleDoorState), "Намерение должно быть удалено после обработки")

    def test_combat_death_and_xp(self):
        """Тестирует боевую систему, смерть и получение опыта."""
        player = create_player(self.world, 5, 5)
        goblin = create_goblin(self.world, 6, 5)
        
        # Устанавливаем здоровье гоблина на 1, чтобы он умер от одного удара
        self.world.get_component(goblin, Health).current = 1
        
        combat_system = MeleeCombatSystem()
        death_system = DeathSystem()
        
        # Игрок атакует гоблина
        self.world.add_component(player, WantsToAttack(target=goblin))
        self.run_system(combat_system)

        goblin_health = self.world.get_component(goblin, Health)
        self.assertLessEqual(goblin_health.current, 0, "Здоровье гоблина должно быть 0 или меньше после атаки")

        # Получаем компонент опыта ПЕРЕД тем, как система смерти удалит сущность
        goblin_xp_gain = self.world.get_component(goblin, GivesExperience)

        # Запускаем систему смерти
        self.run_system(death_system)

        self.assertNotIn(goblin, self.world.entities, "Мертвый гоблин должен быть удален из мира")
        
        player_xp = self.world.get_component(player, Experience)
        self.assertEqual(player_xp.current_xp, goblin_xp_gain.amount, "Игрок должен получить опыт за убийство")

    def test_item_pickup_and_drop(self):
        """Тестирует подбор и выбрасывание предметов."""
        player = create_player(self.world, 5, 5)
        sword = create_sword(self.world, 5, 5)

        pickup_system = ItemPickupSystem()
        drop_system = DropItemSystem()
        player_inventory = self.world.get_component(player, Inventory)

        # 1. Подбор предмета
        self.run_system(pickup_system)
        self.assertIn(sword, player_inventory.items, "Меч должен быть в инвентаре игрока")
        self.assertIsNone(self.world.get_component(sword, Position), "У подобранного предмета не должно быть позиции на карте")

        # 2. Выбрасывание предмета
        self.world.add_component(player, WantsToDropItem(item=sword))
        self.run_system(drop_system)
        self.assertNotIn(sword, player_inventory.items, "Меч не должен быть в инвентаре после выбрасывания")
        sword_pos = self.world.get_component(sword, Position)
        player_pos = self.world.get_component(player, Position)
        self.assertIsNotNone(sword_pos, "У выброшенного предмета должна быть позиция")
        self.assertEqual((sword_pos.x, sword_pos.y), (player_pos.x, player_pos.y), "Предмет должен появиться на позиции игрока")

    def test_item_use_healing_potion(self):
        """Тестирует использование лечебного зелья."""
        player = create_player(self.world, 5, 5)
        potion = create_healing_potion(self.world, -1, -1) # Создаем без позиции

        player_health = self.world.get_component(player, Health)
        player_inventory = self.world.get_component(player, Inventory)
        
        player_health.current = 10
        player_inventory.items.append(potion)

        use_system = ItemUseSystem()
        self.world.add_component(player, WantsToUseItem(item=potion))
        self.run_system(use_system)

        self.assertEqual(player_health.current, 20, "Здоровье игрока должно восстановиться")
        self.assertNotIn(potion, player_inventory.items, "Зелье должно быть использовано и удалено из инвентаря")
        self.assertNotIn(potion, self.world.entities, "Использованное зелье должно быть удалено из мира")

    def test_equip_and_unequip(self):
        """Тестирует экипировку и снятие предметов."""
        player = create_player(self.world, 5, 5)
        sword = create_sword(self.world, -1, -1)
        armor = create_leather_armor(self.world, -1, -1)
        
        self.world.get_component(player, Inventory).items.extend([sword, armor])
        
        equip_system = EquipSystem()
        player_equipment = self.world.get_component(player, Equipment)

        # 1. Экипировать меч
        self.world.add_component(player, WantsToEquip(item=sword))
        self.run_system(equip_system)
        self.assertEqual(player_equipment.slots.get(EquipmentSlot.WEAPON), sword, "Меч должен быть экипирован в слот оружия")
        self.assertIsNotNone(self.world.get_component(sword, Equipped), "У меча должен быть компонент Equipped")

        # 2. Экипировать броню
        self.world.add_component(player, WantsToEquip(item=armor))
        self.run_system(equip_system)
        self.assertEqual(player_equipment.slots.get(EquipmentSlot.ARMOR), armor, "Броня должна быть экипирована")

        # 3. Снять меч (повторная команда на экипировку уже экипированного предмета)
        self.world.add_component(player, WantsToEquip(item=sword))
        self.run_system(equip_system)
        self.assertIsNone(player_equipment.slots.get(EquipmentSlot.WEAPON), "Меч должен быть снят")
        self.assertIsNone(self.world.get_component(sword, Equipped), "У снятого меча не должно быть компонента Equipped")

    def test_level_up_system(self):
        """Тестирует систему повышения уровня."""
        player = create_player(self.world, 5, 5)
        player_xp = self.world.get_component(player, Experience)
        player_health = self.world.get_component(player, Health)
        player_stats = self.world.get_component(player, CombatStats)

        player_xp.xp_to_next_level = 100
        player_xp.current_xp = 90
        player_health.current = 5 # Чтобы проверить полное исцеление

        # Симулируем получение опыта
        player_xp.current_xp += 35 # 90 + 35 = 125, должно хватить для уровня

        levelup_system = LevelUpSystem()
        self.run_system(levelup_system)

        self.assertEqual(player_xp.level, 2, "Уровень игрока должен стать 2")
        self.assertEqual(player_xp.current_xp, 25, "Остаток опыта должен быть правильным")
        self.assertGreater(player_xp.xp_to_next_level, 100, "Требование к следующему уровню должно вырасти")
        self.assertEqual(player_health.current, player_health.max, "Здоровье должно полностью восстановиться")
        self.assertEqual(player_stats.power, 6, "Сила должна увеличиться") # 5 + 1
        self.assertEqual(player_stats.defense, 3, "Защита должна увеличиться") # 2 + 1

    def test_trap_and_poison_system(self):
        """Тестирует срабатывание ловушек и эффект отравления."""
        player = create_player(self.world, 5, 5)
        trap = create_damage_trap(self.world, 6, 5)
        
        trap_system = TrapSystem()
        poison_system = PoisonSystem()
        movement_system = MovementSystem()

        player_health = self.world.get_component(player, Health)
        initial_health = player_health.current

        # 1. Движение на ловушку
        self.world.get_component(player, Velocity).dx = 1
        self.run_system(movement_system)
        self.run_system(trap_system)

        self.assertEqual(player_health.current, initial_health - 10, "Игрок должен получить урон от ловушки")
        self.assertIsNone(self.world.get_component(trap, Hidden), "Сработавшая ловушка не должна быть скрытой")

        # 2. Тест отравления
        self.world.add_component(player, Poisoned(duration=2, damage=5))
        self.run_system(poison_system)
        self.assertEqual(player_health.current, initial_health - 10 - 5, "Игрок должен получить урон от яда")
        
        poison_comp = self.world.get_component(player, Poisoned)
        self.assertEqual(poison_comp.duration, 1, "Длительность яда должна уменьшиться")

        self.run_system(poison_system)
        self.assertIsNone(self.world.get_component(player, Poisoned), "Эффект яда должен закончиться")

    @mock.patch('random.randint', return_value=1) # Заставим врага всегда двигаться вправо-вниз
    def test_enemy_ai_system(self, mock_randint):
        """Тестирует базовый ИИ врага: преследование, бегство и блуждание."""
        player = create_player(self.world, 5, 5)
        goblin = create_goblin(self.world, 10, 10)
        
        # Очищаем инвентарь и экипировку гоблина, чтобы тест был детерминированным.
        # Иначе он может попытаться использовать зелье вместо бегства.
        goblin_inventory = self.world.get_component(goblin, Inventory)
        if goblin_inventory:
            goblin_inventory.items.clear()
        goblin_equipment = self.world.get_component(goblin, Equipment)
        if goblin_equipment:
            goblin_equipment.slots.clear()
        
        ai_system = EnemyAISystem()
        goblin_vel = self.world.get_component(goblin, Velocity)
        goblin_health = self.world.get_component(goblin, Health)

        # 1. Преследование (игрок видим)
        self.world.visibility_map[10, 10] = 2 # Делаем клетку с гоблином видимой для него самого
        self.run_system(ai_system)
        self.assertEqual((goblin_vel.dx, goblin_vel.dy), (-1, -1), "Гоблин должен двигаться в сторону игрока")

        # 2. Бегство (игрок видим, мало здоровья)
        goblin_health.current = 1
        self.run_system(ai_system)
        self.assertEqual((goblin_vel.dx, goblin_vel.dy), (1, 1), "Гоблин с низким здоровьем должен убегать от игрока")

        # 3. Блуждание (игрок не видим)
        goblin_health.current = goblin_health.max # Восстанавливаем здоровье
        self.world.visibility_map[10, 10] = 0 # Делаем клетку невидимой
        self.run_system(ai_system)
        # mock_randint заставляет его двигаться в (1, 1)
        self.assertEqual((goblin_vel.dx, goblin_vel.dy), (1, 1), "Гоблин должен блуждать, когда не видит игрока")

    # Мокаем pygame, так как он не нужен для логики этого теста, но используется в PygameRenderSystem
    @mock.patch('pygame.display.set_mode')
    @mock.patch('pygame.display.set_caption')
    @mock.patch('pygame.font.SysFont')
    @mock.patch('pygame.init')
    def test_level_transition_data_persistence(self, mock_init, mock_font, mock_caption, mock_set_mode):
        """Тестирует сохранение данных игрока при переходе на следующий уровень."""
        # --- Настройка мира уровня 1 ---
        world1 = self.world
        player = create_player(world1, 5, 5)
        sword = create_sword(world1, -1, -1)
        
        # Даем игроку меч и экипируем его
        world1.get_component(player, Inventory).items.append(sword)
        world1.add_component(player, WantsToEquip(item=sword))
        self.run_system(EquipSystem())

        # Устанавливаем нестандартные значения для проверки
        world1.get_component(player, Health).current = 15
        world1.get_component(player, Experience).current_xp = 50

        # --- Извлекаем данные ---
        player_data = extract_player_data(world1)

        # Проверяем, что данные извлечены корректно
        self.assertEqual(player_data['health'].current, 15)
        self.assertEqual(player_data['experience'].current_xp, 50)
        self.assertEqual(len(player_data['inventory_items']), 1)
        self.assertIn(EquipmentSlot.WEAPON, player_data['equipped_slots'])

        # --- Генерируем мир уровня 2 с данными игрока ---
        # Мокаем find_random_floor_tile, чтобы избежать ошибок при генерации карты без пола
        # и чтобы контролировать размещение объектов.
        # Используем side_effect, чтобы возвращать разные значения при каждом вызове
        # и избежать бесконечного цикла при поиске места для лестницы.
        mock_tile_finder = mock.Mock(side_effect=[
            (10, 10), (11, 11), # Player, Stairs
            (12, 12), (13, 13), (14, 14), (15, 15), (10, 11) # Enemies, items, etc.
        ] * 5) # Повторяем, чтобы хватило на все вызовы
        with mock.patch('map_generator.MapGenerator.find_random_floor_tile', mock_tile_finder):
            # Создаем состояние игры для нового уровня
            next_level_state = GameState(
                current_level=2,
                player_data=player_data
            )
            world2 = generate_world(self.config, next_level_state, GOBLIN_CAVES)

        # --- Проверяем состояние игрока в новом мире ---
        new_player = world2.player_entity
        self.assertIsNotNone(new_player)

        new_health = world2.get_component(new_player, Health)
        new_xp = world2.get_component(new_player, Experience)
        new_inventory = world2.get_component(new_player, Inventory)
        new_equipment = world2.get_component(new_player, Equipment)

        self.assertEqual(new_health.current, 15, "Здоровье должно перенестись")
        self.assertEqual(new_xp.current_xp, 50, "Опыт должен перенестись")
        self.assertEqual(len(new_inventory.items), 1, "Предметы в инвентаре должны перенестись")

        # Проверяем, что предмет в новом мире экипирован
        equipped_item = new_equipment.slots.get(EquipmentSlot.WEAPON)
        self.assertIsNotNone(equipped_item, "Оружие должно быть экипировано в новом мире")
        self.assertIn(equipped_item, new_inventory.items, "Экипированный предмет должен быть в инвентаре")
        
        item_name = world2.get_component(equipped_item, Name).name
        self.assertEqual(item_name, "Sword", "Перенесенный предмет должен быть мечом")

    def test_resting_system(self):
        """Тестирует систему отдыха (восстановления здоровья у трактирщика)."""
        player = create_player(self.world, 5, 5)
        player_health = self.world.get_component(player, Health)
        player_health.current = 10 # Устанавливаем неполное здоровье

        resting_system = RestingSystem()

        # Симулируем желание отдохнуть
        self.world.add_component(player, WantsToRest())
        self.run_system(resting_system)

        self.assertEqual(player_health.current, player_health.max, "Здоровье игрока должно полностью восстановиться")
        self.assertIsNone(self.world.get_component(player, WantsToRest), "Намерение отдохнуть должно быть удалено")

    def test_trading_system(self):
        """Тестирует систему торговли (получения предметов у торговца)."""
        player = create_player(self.world, 5, 5)
        player_inventory = self.world.get_component(player, Inventory)
        initial_item_count = len(player_inventory.items)

        trading_system = TradingSystem()

        # Симулируем желание торговать
        self.world.add_component(player, WantsToTrade())
        self.run_system(trading_system)

        self.assertEqual(len(player_inventory.items), initial_item_count + 1, "В инвентаре должен появиться новый предмет")
        
        new_item = player_inventory.items[-1]
        item_name = self.world.get_component(new_item, Name).name
        self.assertEqual(item_name, "Healing Potion", "Новый предмет должен быть лечебным зельем")
        self.assertIsNone(self.world.get_component(player, WantsToTrade), "Намерение торговать должно быть удалено")

    @mock.patch('pygame.display.set_mode')
    @mock.patch('pygame.display.set_caption')
    @mock.patch('pygame.font.SysFont')
    @mock.patch('pygame.init')
    def test_world_caching_and_recreation(self, mock_init, mock_font, mock_caption, mock_set_mode):
        """Тестирует сохранение состояния мира и воссоздание игрока при возвращении на уровень."""
        # --- 1. Создаем и модифицируем мир ---
        # Используем generate_world для создания начального состояния
        mock_tile_finder = mock.Mock(side_effect=[
            (10, 10), (11, 11), # Player, Stairs
            (5, 5), (6, 6), (7, 7), (8, 8), (9, 9) # Enemies, items, etc.
        ] * 5)
        with mock.patch('map_generator.MapGenerator.find_random_floor_tile', mock_tile_finder):
            initial_state = GameState(current_level=1)
            world1 = generate_world(self.config, initial_state, GOBLIN_CAVES)

        # Убедимся, что в мире есть враги
        initial_enemies = world1.get_entities_with(Enemy)
        self.assertGreater(len(initial_enemies), 0, "В мире должны быть враги для теста")
        enemy_to_kill = initial_enemies[0]
        
        # Убиваем одного врага, чтобы изменить состояние мира
        world1.get_component(enemy_to_kill, Health).current = 0
        DeathSystem().update(world1)
        
        # Проверяем, что враг мертв и удален
        self.assertNotIn(enemy_to_kill, world1.entities)
        num_enemies_after_kill = len(world1.get_entities_with(Enemy))

        # --- 2. Симулируем уход игрока с уровня ---
        player_data = extract_player_data(world1)
        player_entity = world1.player_entity
        world1.destroy_entity(player_entity)
        world1.player_entity = None

        # --- 3. "Кэшируем" мир (просто сохраняем ссылку) ---
        cached_world = world1

        # --- 4. Воссоздаем игрока в кэшированном мире ---
        recreate_player_in_world(cached_world, player_data)

        # --- 5. Проверяем состояние ---
        self.assertIsNotNone(cached_world.player_entity, "Игрок должен быть воссоздан")
        self.assertEqual(len(cached_world.get_entities_with(Enemy)), num_enemies_after_kill, "Количество врагов не должно меняться")
        self.assertNotIn(enemy_to_kill, cached_world.entities, "Убитый враг не должен появиться снова")
        self.assertEqual(cached_world.get_component(cached_world.player_entity, Health).current, player_data['health'].current, "Данные игрока должны быть восстановлены")

    def test_ranged_combat_shooting(self):
        """Тестирует стрельбу из лука, потребление стрел и нанесение урона."""
        player = create_player(self.world, 5, 5)
        goblin = create_goblin(self.world, 10, 5)
        bow = create_bow(self.world, -1, -1)
        arrow = create_arrow(self.world, -1, -1)

        player_inventory = self.world.get_component(player, Inventory)
        player_inventory.items.extend([bow, arrow])

        # Экипируем лук
        self.world.add_component(player, WantsToEquip(item=bow))
        self.run_system(EquipSystem())

        # Симулируем намерение выстрелить
        self.world.add_component(player, WantsToShoot(target=goblin))

        shooting_system = ShootingSystem()
        projectile_system = ProjectileSystem()

        initial_arrow_count = len([i for i in player_inventory.items if self.world.get_component(i, Ammunition)])
        self.run_system(shooting_system)

        # Проверяем, что стрела потрачена
        final_arrow_count = len([i for i in player_inventory.items if self.world.get_component(i, Ammunition)])
        self.assertEqual(final_arrow_count, initial_arrow_count - 1, "Стрела должна быть потрачена при выстреле")

        # Проверяем, что создан снаряд
        projectiles = self.world.get_entities_with(Projectile)
        self.assertEqual(len(projectiles), 1, "Должен быть создан один снаряд (стрела)")

        # Прогоняем систему снарядов до тех пор, пока снаряд не достигнет цели или не исчезнет
        goblin_health = self.world.get_component(goblin, Health)
        initial_goblin_health = goblin_health.current
        
        # Карта нужна для ProjectileSystem, чтобы снаряд не врезался в "стену" из-за отсутствия карты
        self.world.game_map = np.zeros((self.config.grid_height, self.config.grid_width), dtype=np.uint8)

        for _ in range(10): # Максимум 10 шагов для снаряда
            self.run_system(projectile_system)
            if not self.world.get_entities_with(Projectile):
                break
        
        self.assertLess(goblin_health.current, initial_goblin_health, "Гоблин должен получить урон от стрелы")

    def test_ranged_combat_aoe_throw(self):
        """Тестирует бросок предмета с уроном по области (свиток огненного шара)."""
        player = create_player(self.world, 5, 5)
        goblin1 = create_goblin(self.world, 10, 10)
        goblin2 = create_goblin(self.world, 11, 10)
        scroll = create_fireball_scroll(self.world, -1, -1)

        player_inventory = self.world.get_component(player, Inventory)
        player_inventory.items.append(scroll)

        goblin1_health = self.world.get_component(goblin1, Health)
        goblin2_health = self.world.get_component(goblin2, Health)
        initial_health1 = goblin1_health.current
        initial_health2 = goblin2_health.current

        # Симулируем бросок в точку (10, 10)
        self.world.add_component(player, WantsToThrow(item=scroll, target_x=10, target_y=10))
        
        ranged_combat_system = RangedCombatSystem()
        self.run_system(ranged_combat_system)

        # Проверяем, что оба гоблина получили урон
        self.assertLess(goblin1_health.current, initial_health1, "Гоблин 1 должен получить урон")
        self.assertLess(goblin2_health.current, initial_health2, "Гоблин 2 в радиусе действия должен получить урон")

        # Проверяем, что свиток использован
        self.assertNotIn(scroll, player_inventory.items, "Свиток должен быть удален из инвентаря после использования")

    @mock.patch('random.choice', return_value=(15, 15))
    def test_item_use_teleport_scroll(self, mock_random_choice):
        """Тестирует использование свитка телепортации."""
        player = create_player(self.world, 5, 5)
        scroll = create_teleport_scroll(self.world, -1, -1)
        
        player_inventory = self.world.get_component(player, Inventory)
        player_inventory.items.append(scroll)
        
        # Создаем простую карту с полом, чтобы было куда телепортироваться
        self.world.game_map = np.zeros((self.config.grid_height, self.config.grid_width), dtype=np.uint8)
        self.world.game_map[15, 15] = 0 # Убедимся, что целевая точка проходима

        player_pos = self.world.get_component(player, Position)
        
        self.world.add_component(player, WantsToUseItem(item=scroll))
        self.run_system(ItemUseSystem())

        self.assertEqual((player_pos.x, player_pos.y), (15, 15), "Игрок должен был телепортироваться в выбранную точку")
        self.assertNotIn(scroll, player_inventory.items, "Свиток телепортации должен быть использован")
        mock_random_choice.assert_called_once()

    def test_drop_equipped_item(self):
        """Тестирует выбрасывание экипированного предмета."""
        player = create_player(self.world, 5, 5)
        sword = create_sword(self.world, -1, -1)
        
        player_inventory = self.world.get_component(player, Inventory)
        player_equipment = self.world.get_component(player, Equipment)
        player_inventory.items.append(sword)

        # Экипируем меч
        self.world.add_component(player, WantsToEquip(item=sword))
        self.run_system(EquipSystem())
        self.assertIn(EquipmentSlot.WEAPON, player_equipment.slots)

        # Выбрасываем экипированный меч
        self.world.add_component(player, WantsToDropItem(item=sword))
        self.run_system(DropItemSystem())

        self.assertNotIn(sword, player_inventory.items, "Меч должен быть удален из инвентаря")
        self.assertNotIn(EquipmentSlot.WEAPON, player_equipment.slots, "Слот оружия должен быть пуст после выбрасывания")
        self.assertIsNone(self.world.get_component(sword, Equipped), "У выброшенного меча не должно быть компонента Equipped")
        self.assertIsNotNone(self.world.get_component(sword, Position), "У выброшенного меча должна быть позиция на карте")

    def test_enemy_ai_uses_healing_potion(self):
        """Тестирует, что ИИ использует лечебное зелье при низком здоровье."""
        player = create_player(self.world, 5, 5)
        orc = create_orc(self.world, 10, 10)
        potion = create_healing_potion(self.world, -1, -1)

        orc_inventory = self.world.get_component(orc, Inventory)
        orc_inventory.items.clear() # Очищаем инвентарь от случайно сгенерированных предметов
        orc_inventory.items.append(potion)
        
        orc_health = self.world.get_component(orc, Health)
        orc_health.current = 2 # Низкое здоровье

        # Делаем игрока видимым для орка
        self.world.visibility_map[10, 10] = 2

        ai_system = EnemyAISystem()
        item_use_system = ItemUseSystem()

        # Запускаем ИИ
        self.run_system(ai_system)

        # Проверяем, что орк решил использовать зелье
        wants_to_use = self.world.get_component(orc, WantsToUseItem)
        self.assertIsNotNone(wants_to_use, "Орк должен хотеть использовать предмет")
        self.assertEqual(wants_to_use.item, potion, "Орк должен хотеть использовать зелье")

        # Получаем количество лечения ДО того, как зелье будет использовано и удалено
        healed_amount = self.world.get_component(potion, ProvidesHealing).amount

        # Запускаем систему использования предметов
        self.run_system(item_use_system)

        # Проверяем результат
        self.assertEqual(orc_health.current, 2 + healed_amount, "Здоровье орка должно восстановиться")
        self.assertNotIn(potion, orc_inventory.items, "Зелье должно быть удалено из инвентаря орка")

    def test_mage_ai_and_magic_system(self):
        """Тестирует ИИ мага, использование заклинаний и систему магии."""
        player = create_player(self.world, 5, 5)
        mage = create_mage(self.world, 10, 5) # На расстоянии 5 клеток

        ai_system = EnemyAISystem()
        magic_system = MagicSystem()
        projectile_system = ProjectileSystem()

        mage_spell = self.world.get_component(mage, MagicSpell)
        mage_cooldown = self.world.get_component(mage, OnCooldown)
        player_health = self.world.get_component(player, Health)
        initial_player_health = player_health.current

        # Карта нужна для AI (проверка линии видимости) и ProjectileSystem.
        self.world.game_map = np.zeros((self.config.grid_height, self.config.grid_width), dtype=np.uint8)

        # 1. Тест: Маг должен захотеть применить заклинание, если игрок в радиусе и видим
        self.world.visibility_map[5, 10] = 2 # Делаем мага "видящим" игрока
        mage_cooldown.turns = 0 # Убедимся, что заклинание не на перезарядке
        self.run_system(ai_system)

        self.assertIsNotNone(self.world.get_component(mage, WantsToCastSpell), "Маг должен хотеть применить заклинание")
        self.assertEqual(mage_cooldown.turns, mage_spell.cooldown, "Перезарядка заклинания должна быть установлена")

        # 2. Тест: Система магии должна создать снаряд
        self.run_system(magic_system)
        self.assertIsNone(self.world.get_component(mage, WantsToCastSpell), "Намерение применить заклинание должно быть удалено")
        
        projectiles = self.world.get_entities_with(Projectile)
        self.assertEqual(len(projectiles), 1, "Должен быть создан один магический снаряд")

        # 3. Тест: Снаряд должен долететь и нанести урон
        for _ in range(10): # Максимум 10 шагов для снаряда
            self.run_system(projectile_system)
            if not self.world.get_entities_with(Projectile):
                break
        
        self.assertLess(player_health.current, initial_player_health, "Игрок должен получить урон от заклинания")
        self.assertEqual(len(self.world.get_entities_with(Projectile)), 0, "Снаряд должен исчезнуть после попадания")

        # 4. Тест: Маг на перезарядке не должен атаковать
        self.assertGreater(mage_cooldown.turns, 0)
        self.run_system(ai_system)
        self.assertIsNone(self.world.get_component(mage, WantsToCastSpell), "Маг на перезарядке не должен пытаться применить заклинание")

        # 5. Тест: Перезарядка должна уменьшаться, когда игрок не виден
        mage_cooldown.turns = 1
        # Делаем игрока невидимым, чтобы маг не атаковал, а только уменьшил перезарядку
        self.world.visibility_map[5, 10] = 0
        self.run_system(ai_system)
        self.assertEqual(mage_cooldown.turns, 0, "Перезарядка должна уменьшиться до 0")
        self.assertIsNone(self.world.get_component(mage, WantsToCastSpell), "Маг не должен атаковать, если не видит игрока")

        # 6. Тест: Маг атакует, как только перезарядка закончилась и он видит игрока
        # Снова делаем игрока видимым
        self.world.visibility_map[5, 10] = 2
        self.run_system(ai_system)
        self.assertIsNotNone(self.world.get_component(mage, WantsToCastSpell), "Маг должен снова атаковать после окончания перезарядки")
        self.assertEqual(mage_cooldown.turns, mage_spell.cooldown, "Перезарядка должна сброситься после новой атаки")

    @mock.patch('pygame.display.set_mode')
    @mock.patch('pygame.display.set_caption')
    @mock.patch('pygame.font.SysFont')
    @mock.patch('pygame.init')
    def test_player_spell_casting(self, mock_init, mock_font, mock_caption, mock_set_mode):
        """Тестирует использование заклинаний игроком, включая прицеливание, затраты маны и эффект."""
        # --- Setup ---
        player = create_player(self.world, 5, 5)
        enemy = create_goblin(self.world, 10, 5)
        
        # Mock PygameRenderSystem and its camera for TargetingSystem
        render_system = PygameRenderSystem(self.config)
        render_system.camera.x = 0
        render_system.camera.y = 0
        self.world.systems.append(render_system)

        targeting_system = TargetingSystem()
        magic_system = MagicSystem()
        projectile_system = ProjectileSystem()

        player_mana = self.world.get_component(player, Mana)
        player_cooldown = self.world.get_component(player, OnCooldown)
        player_spell = self.world.get_component(player, MagicSpell)
        enemy_health = self.world.get_component(enemy, Health)

        initial_mana = player_mana.current
        initial_enemy_health = enemy_health.current
        player_cooldown.turns = 0 # Ensure spell is not on cooldown

        # --- Part 1: Targeting and Cost ---
        self.world.add_component(player, Targeting(range=player_spell.range, purpose='cast', spell=player_spell))

        enemy_pos = self.world.get_component(enemy, Position)
        screen_x = enemy_pos.x * self.config.cell_size
        screen_y = enemy_pos.y * self.config.cell_size
        
        with mock.patch('pygame.mouse.get_pos', return_value=(screen_x, screen_y)):
            # MOUSEBUTTONDOWN is usually 4, but we use a mock object
            self.world.events = [mock.Mock(type=pygame.MOUSEBUTTONDOWN, button=1)]
            self.run_system(targeting_system)

        self.assertIsNotNone(self.world.get_component(player, WantsToCastSpell), "Игрок должен хотеть применить заклинание после прицеливания")
        self.assertIsNone(self.world.get_component(player, Targeting), "Режим прицеливания должен быть выключен")
        self.assertEqual(player_mana.current, initial_mana - player_spell.mana_cost, "Мана должна быть потрачена")
        self.assertEqual(player_cooldown.turns, player_spell.cooldown, "Перезарядка заклинания должна быть установлена")

        # --- Part 2: Spell Effect ---
        self.run_system(magic_system)
        self.assertIsNone(self.world.get_component(player, WantsToCastSpell), "Намерение применить заклинание должно быть удалено после обработки")
        self.assertEqual(len(self.world.get_entities_with(Projectile)), 1, "Должен быть создан один магический снаряд")

        self.world.game_map = np.zeros((self.config.grid_height, self.config.grid_width), dtype=np.uint8)
        for _ in range(10):
            self.run_system(projectile_system)
            if not self.world.get_entities_with(Projectile): break
        
        self.assertLess(enemy_health.current, initial_enemy_health, "Враг должен получить урон от заклинания")
        self.assertEqual(len(self.world.get_entities_with(Projectile)), 0, "Снаряд должен исчезнуть после попадания")

if __name__ == '__main__':
    unittest.main()