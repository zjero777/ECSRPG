import numpy as np
import random
from dataclasses import dataclass
from typing import Tuple, List

@dataclass
class Rect:
    """A rectangle on the map. used for rooms."""
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def center(self) -> Tuple[int, int]:
        """Returns the center coordinates of the rectangle."""
        center_x = (self.x1 + self.x2) // 2
        center_y = (self.y1 + self.y2) // 2
        return center_x, center_y

    def intersects(self, other: "Rect") -> bool:
        """Returns true if this rectangle intersects with another one."""
        return (self.x1 <= other.x2 and self.x2 >= other.x1 and
                self.y1 <= other.y2 and self.y2 >= other.y1)

class MapGenerator:
    """
    Генерирует карту, используя различные алгоритмы.
    """
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.map = np.ones((height, width), dtype=np.uint8)  # 1 - стена, 0 - пол

    def generate(self, generation_type: str, **kwargs) -> np.ndarray:
        """Генерирует карту на основе выбранного типа."""
        if generation_type == 'caves':
            self._generate_caves(**kwargs)
        elif generation_type == 'rooms':
            self._generate_rooms_and_corridors(**kwargs)
        else:
            raise ValueError(f"Unknown map generation type: {generation_type}")
        return self.map

    def _generate_caves(self, initial_wall_chance: float = 0.45, simulation_steps: int = 4, border_size: int = 1):
        """Генерирует пещеры с помощью клеточных автоматов."""
        self.map = (np.random.rand(self.height, self.width) < initial_wall_chance).astype(np.uint8)
        for _ in range(simulation_steps):
            self._simulation_step()
        if border_size > 0:
            self.map[0:border_size, :] = 1
            self.map[-border_size:, :] = 1
            self.map[:, 0:border_size] = 1
            self.map[:, -border_size:] = 1

    def _simulation_step(self):
        """Выполняет один шаг симуляции клеточного автомата."""
        new_map = self.map.copy()
        for y in range(1, self.height - 1):
            for x in range(1, self.width - 1):
                wall_neighbors = np.sum(self.map[y-1:y+2, x-1:x+2]) - self.map[y, x]
                if wall_neighbors > 4:
                    new_map[y, x] = 1
                elif wall_neighbors < 4:
                    new_map[y, x] = 0
        self.map = new_map

    def _generate_rooms_and_corridors(self, max_rooms: int = 30, room_min_size: int = 6, room_max_size: int = 10, border_size: int = 1):
        """Генерирует карту с комнатами и коридорами."""
        self.map.fill(1)
        rooms: List[Rect] = []

        for _ in range(max_rooms):
            w = random.randint(room_min_size, room_max_size)
            h = random.randint(room_min_size, room_max_size)
            x = random.randint(border_size, self.width - w - border_size - 1)
            y = random.randint(border_size, self.height - h - border_size - 1)
            new_room = Rect(x, y, x + w, y + h)

            if not any(new_room.intersects(other_room) for other_room in rooms):
                self._create_room(new_room)
                if rooms:
                    prev_x, prev_y = rooms[-1].center
                    new_x, new_y = new_room.center
                    if random.randint(0, 1) == 1:
                        self._create_h_tunnel(prev_x, new_x, prev_y)
                        self._create_v_tunnel(prev_y, new_y, new_x)
                    else:
                        self._create_v_tunnel(prev_y, new_y, prev_x)
                        self._create_h_tunnel(prev_x, new_x, new_y)
                rooms.append(new_room)

    def _create_room(self, room: Rect):
        self.map[room.y1:room.y2, room.x1:room.x2] = 0

    def _create_h_tunnel(self, x1: int, x2: int, y: int):
        self.map[y, min(x1, x2):max(x1, x2) + 1] = 0

    def _create_v_tunnel(self, y1: int, y2: int, x: int):
        self.map[min(y1, y2):max(y1, y2) + 1, x] = 0

    def find_random_floor_tile(self) -> Tuple[int, int]:
        """Находит случайную проходимую клетку на карте."""
        floor_indices = np.argwhere(self.map == 0)
        if len(floor_indices) == 0:
            raise RuntimeError("Генерация карты провалилась, не найдено ни одной клетки пола.")
        
        random_index = np.random.randint(0, len(floor_indices))
        y, x = floor_indices[random_index]
        return int(x), int(y)