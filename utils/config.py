"""
Configuration manager for wargame simulation.
Centralizes all configuration loading and provides typed access to settings.
"""
import configparser
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

from utils.logger import get_logger


@dataclass
class SimulationConfig:
    """Simulation configuration settings."""
    hex_size: float = 30.0
    turn_duration: float = 30.0
    random_seed: int = 0


@dataclass 
class DisplayConfig:
    """Display configuration settings."""
    default_display_mode: str = "terrain"
    show_grid: bool = True
    show_coordinates: bool = False
    antialiasing: bool = True


@dataclass
class PerformanceConfig:
    """Performance configuration settings."""
    los_cache_size: int = 10000
    animation_fps: int = 20
    max_pathfinding_iterations: int = 10000


@dataclass
class UnitsConfig:
    """Units configuration settings."""
    default_infantry_movement: float = 10.0
    default_vehicle_movement: float = 15.0
    default_sensor_range: float = 500.0


@dataclass
class TerrainConfig:
    """Terrain configuration settings."""
    forest_height: float = 15.0
    building_height: float = 10.0
    max_slope_for_vehicles: float = 45.0


@dataclass
class UIConfig:
    """UI configuration settings."""
    window_width: int = 1200
    window_height: int = 800
    map_view_ratio: float = 0.75
    side_panel_width: int = 300
    default_font_family: str = "Arial"
    default_font_size: int = 9


class ConfigManager:
    """
    Centralized configuration manager that loads and provides typed access to all settings.
    """
    
    _instance: Optional['ConfigManager'] = None
    
    def __new__(cls) -> 'ConfigManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self.logger = get_logger('config')
        self.config_file = Path("config.ini")
        self.config = configparser.ConfigParser()
        
        # Configuration sections
        self.simulation = SimulationConfig()
        self.display = DisplayConfig()
        self.performance = PerformanceConfig()
        self.units = UnitsConfig()
        self.terrain = TerrainConfig()
        self.ui = UIConfig()
        
        self._load_config()
        self._initialized = True
    
    def _load_config(self):
        """Load configuration from file."""
        try:
            if self.config_file.exists():
                self.config.read(self.config_file)
                self.logger.info(f"Loaded configuration from {self.config_file}")
            else:
                # Try example file
                example_file = Path("config.ini.example")
                if example_file.exists():
                    self.config.read(example_file)
                    self.logger.info(f"Loaded configuration from {example_file}")
                else:
                    self.logger.warning("No configuration file found, using defaults")
                    return
            
            # Load simulation config
            if self.config.has_section('Simulation'):
                self.simulation.hex_size = self.config.getfloat('Simulation', 'hex_size', fallback=30.0)
                self.simulation.turn_duration = self.config.getfloat('Simulation', 'turn_duration', fallback=30.0)
                self.simulation.random_seed = self.config.getint('Simulation', 'random_seed', fallback=0)
            
            # Load display config
            if self.config.has_section('Display'):
                self.display.default_display_mode = self.config.get('Display', 'default_display_mode', fallback='terrain')
                self.display.show_grid = self.config.getboolean('Display', 'show_grid', fallback=True)
                self.display.show_coordinates = self.config.getboolean('Display', 'show_coordinates', fallback=False)
                self.display.antialiasing = self.config.getboolean('Display', 'antialiasing', fallback=True)
            
            # Load performance config
            if self.config.has_section('Performance'):
                self.performance.los_cache_size = self.config.getint('Performance', 'los_cache_size', fallback=10000)
                self.performance.animation_fps = self.config.getint('Performance', 'animation_fps', fallback=20)
                self.performance.max_pathfinding_iterations = self.config.getint('Performance', 'max_pathfinding_iterations', fallback=10000)
            
            # Load units config
            if self.config.has_section('Units'):
                self.units.default_infantry_movement = self.config.getfloat('Units', 'default_infantry_movement', fallback=10.0)
                self.units.default_vehicle_movement = self.config.getfloat('Units', 'default_vehicle_movement', fallback=15.0)
                self.units.default_sensor_range = self.config.getfloat('Units', 'default_sensor_range', fallback=500.0)
            
            # Load terrain config
            if self.config.has_section('Terrain'):
                self.terrain.forest_height = self.config.getfloat('Terrain', 'forest_height', fallback=15.0)
                self.terrain.building_height = self.config.getfloat('Terrain', 'building_height', fallback=10.0)
                self.terrain.max_slope_for_vehicles = self.config.getfloat('Terrain', 'max_slope_for_vehicles', fallback=45.0)
            
            # Load UI config
            if self.config.has_section('UI'):
                self.ui.window_width = self.config.getint('UI', 'window_width', fallback=1200)
                self.ui.window_height = self.config.getint('UI', 'window_height', fallback=800)
                self.ui.map_view_ratio = self.config.getfloat('UI', 'map_view_ratio', fallback=0.75)
                self.ui.side_panel_width = self.config.getint('UI', 'side_panel_width', fallback=300)
                self.ui.default_font_family = self.config.get('UI', 'default_font_family', fallback='Arial')
                self.ui.default_font_size = self.config.getint('UI', 'default_font_size', fallback=9)
            
            self.logger.info("Configuration loaded successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
    
    def reload(self):
        """Reload configuration from file."""
        self._load_config()
        self.logger.info("Configuration reloaded")
    
    def get_section_dict(self, section_name: str) -> Dict[str, Any]:
        """Get a section as a dictionary."""
        if section_name == 'Simulation':
            return {
                'hex_size': self.simulation.hex_size,
                'turn_duration': self.simulation.turn_duration,
                'random_seed': self.simulation.random_seed
            }
        elif section_name == 'Display':
            return {
                'default_display_mode': self.display.default_display_mode,
                'show_grid': self.display.show_grid,
                'show_coordinates': self.display.show_coordinates,
                'antialiasing': self.display.antialiasing
            }
        elif section_name == 'Performance':
            return {
                'los_cache_size': self.performance.los_cache_size,
                'animation_fps': self.performance.animation_fps,
                'max_pathfinding_iterations': self.performance.max_pathfinding_iterations
            }
        elif section_name == 'Units':
            return {
                'default_infantry_movement': self.units.default_infantry_movement,
                'default_vehicle_movement': self.units.default_vehicle_movement,
                'default_sensor_range': self.units.default_sensor_range
            }
        elif section_name == 'Terrain':
            return {
                'forest_height': self.terrain.forest_height,
                'building_height': self.terrain.building_height,
                'max_slope_for_vehicles': self.terrain.max_slope_for_vehicles
            }
        elif section_name == 'UI':
            return {
                'window_width': self.ui.window_width,
                'window_height': self.ui.window_height,
                'map_view_ratio': self.ui.map_view_ratio,
                'side_panel_width': self.ui.side_panel_width,
                'default_font_family': self.ui.default_font_family,
                'default_font_size': self.ui.default_font_size
            }
        else:
            return {}


# Global instance
def get_config() -> ConfigManager:
    """Get the global configuration manager instance."""
    return ConfigManager()