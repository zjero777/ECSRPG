from dataclasses import dataclass

@dataclass
class GameConfig:
    screen_width: int = 1024
    screen_height: int = 800
    grid_width: int = 80
    grid_height: int = 80
    cell_size: int = 18
    info_panel_height: int = 120
    fps: int = 60
    fov_radius: int = 8
    map_generation_type: str = 'rooms' # 'caves' or 'rooms'