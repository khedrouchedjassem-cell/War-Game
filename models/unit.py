"""
Unit model for representing military units in the wargame simulation.
"""
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import uuid
import math

# Import config for unit defaults
from utils.config import get_config
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.hexcell import HexCell

class UnitType(Enum):
    """Enumeration of unit types with different capabilities."""
    INFANTRY = "infantry"
    ARMOR = "armor"
    TANK = "tank"
    ARTILLERY = "artillery"
    AIR_DEFENSE = "air_defense"
    RECON = "recon"
    ENGINEER = "engineer"
    COMMAND = "command"
    SUPPORT = "support"


class MovementType(Enum):
    """Types of movement affecting terrain traversal."""
    FOOT = "foot"
    WHEELED = "wheeled"
    TRACKED = "tracked"
    AIRCRAFT = "aircraft"


class UnitSide(Enum):
    """Sides in the conflict."""
    RED = "red"
    BLUE = "blue"
    NEUTRAL = "neutral"


@dataclass
class Weapon:
    """Represents a weapon system on a unit."""
    name: str
    max_range: float  # Maximum range in meters
    min_range: float = 0.0  # Minimum effective range
    accuracy: float = 0.8  # Base hit probability (0.0 to 1.0)
    damage: float = 1.0  # Damage potential
    ammunition: int = -1  # -1 for unlimited
    rate_of_fire: int = 1  # Shots per turn
    
    def can_engage(self, distance: float) -> bool:
        """Check if weapon can engage at given distance."""
        return self.min_range <= distance <= self.max_range
    
    def hit_probability(self, distance: float, target_cover: float = 0.0) -> float:
        """Calculate hit probability based on distance and target cover."""
        if not self.can_engage(distance):
            return 0.0
        
        # Range affects accuracy (linear falloff)
        range_factor = 1.0 - (distance / self.max_range) * 0.5
        
        # Cover reduces hit probability
        cover_factor = 1.0 - target_cover
        
        return max(0.0, min(1.0, self.accuracy * range_factor * cover_factor))


@dataclass
class Unit:
    """
    Represents a military unit in the simulation.
    
    Contains all attributes needed for movement, combat, detection,
    and interaction with the hex-based terrain system.
    """
    
    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Unknown Unit"
    unit_type: UnitType = UnitType.INFANTRY
    side: UnitSide = UnitSide.BLUE
    
    # Position and movement
    position: Optional['HexCell'] = None  # Current hex position
    facing: float = 0.0  # Direction in degrees (0 = North)
    movement_type: MovementType = MovementType.FOOT
    movement_points: float = 10.0  # Movement points per turn
    max_movement_points: float = 10.0
    
    # Physical characteristics
    size: float = 1.0  # Physical size multiplier
    height: float = 2.0  # Height in meters (affects LOS)
    stealth: float = 0.0  # Stealth rating (0.0 to 1.0)
    
    # Combat attributes
    strength: float = 100.0  # Current strength (0-100)
    max_strength: float = 100.0
    morale: float = 100.0  # Morale level (0-100)
    experience: float = 50.0  # Experience level (0-100)
    
    # Weapons and sensors
    weapons: List[Weapon] = field(default_factory=list)
    sensor_range: float = 500.0  # Detection range in meters
    communication_range: float = 1000.0  # Radio communication range
    
    # Status
    is_active: bool = True
    is_hidden: bool = False
    suppression_level: float = 0.0  # Suppression from enemy fire
    
    # AI and orders
    orders: Optional[Dict[str, Any]] = None
    target: Optional['Unit'] = None
    waypoints: List[Tuple[int, int]] = field(default_factory=list)  # List of (q, r) coordinates
    
    # Game state
    last_fired: int = 0  # Turn when unit last fired
    detected_enemies: Dict[str, int] = field(default_factory=dict)  # Enemy IDs and turn detected
    
    def __post_init__(self):
        """Initialize unit after creation."""
        if not self.weapons:
            self._setup_default_weapons()
        self._setup_unit_characteristics()
    
    def _setup_default_weapons(self):
        """Setup default weapons based on unit type."""
        weapon_configs = {
            UnitType.INFANTRY: [
                Weapon("Assault Rifles", max_range=400, accuracy=0.7, damage=0.8),
                Weapon("Grenade Launcher", max_range=300, min_range=50, accuracy=0.6, damage=1.2)
            ],
            UnitType.ARMOR: [
                Weapon("Main Gun", max_range=1800, accuracy=0.8, damage=2.5),
                Weapon("Machine Gun", max_range=800, accuracy=0.7, damage=0.6)
            ],
            UnitType.TANK: [
                Weapon("Main Gun", max_range=2000, accuracy=0.8, damage=3.0),
                Weapon("Machine Gun", max_range=800, accuracy=0.7, damage=0.6)
            ],
            UnitType.ARTILLERY: [
                Weapon("Howitzer", max_range=10000, min_range=500, accuracy=0.6, damage=4.0)
            ],
            UnitType.AIR_DEFENSE: [
                Weapon("SAM System", max_range=5000, accuracy=0.85, damage=3.5),
                Weapon("Anti-Aircraft Gun", max_range=2000, accuracy=0.75, damage=1.8)
            ],
            UnitType.RECON: [
                Weapon("Light Weapons", max_range=300, accuracy=0.6, damage=0.5),
                Weapon("Designated Marksman Rifle", max_range=800, accuracy=0.9, damage=1.0)
            ],
            UnitType.ENGINEER: [
                Weapon("Combat Tools", max_range=200, accuracy=0.5, damage=0.4),
                Weapon("Demolition Charges", max_range=100, accuracy=0.8, damage=2.0)
            ],
            UnitType.COMMAND: [
                Weapon("Personal Defense Weapons", max_range=250, accuracy=0.6, damage=0.6)
            ],
            UnitType.SUPPORT: [
                Weapon("Small Arms", max_range=200, accuracy=0.5, damage=0.5)
            ]
        }
        
        self.weapons = weapon_configs.get(self.unit_type, [
            Weapon("Small Arms", max_range=200, accuracy=0.5, damage=0.5)
        ])
    
    def _setup_unit_characteristics(self):
        """Setup unit-specific characteristics based on unit type."""
        config = get_config()
        
        # Use config defaults where available, fallback to hardcoded for specific unit variations
        characteristics = {
            UnitType.INFANTRY: {
                'movement_type': MovementType.FOOT,
                'movement_points': config.units.default_infantry_movement,
                'max_movement_points': config.units.default_infantry_movement,
                'sensor_range': config.units.default_sensor_range * 0.8,  # Infantry has slightly reduced range
                'size': 1.0,
                'height': 1.8,
                'stealth': 0.3,
                'max_strength': 100.0
            },
            UnitType.ARMOR: {
                'movement_type': MovementType.TRACKED,
                'movement_points': config.units.default_vehicle_movement * 0.8,  # Armor is slower than wheeled
                'max_movement_points': config.units.default_vehicle_movement * 0.8,
                'sensor_range': config.units.default_sensor_range * 2.4,  # Better sensors
                'size': 1.5,
                'height': 2.5,
                'stealth': 0.0,
                'max_strength': 150.0
            },
            UnitType.TANK: {
                'movement_type': MovementType.TRACKED,
                'movement_points': config.units.default_vehicle_movement * 0.67,  # Tanks are slower
                'max_movement_points': config.units.default_vehicle_movement * 0.67,
                'sensor_range': config.units.default_sensor_range * 3.0,  # Excellent sensors
                'size': 2.0,
                'height': 3.0,
                'stealth': 0.0,
                'max_strength': 180.0
            },
            UnitType.ARTILLERY: {
                'movement_type': MovementType.TRACKED,
                'movement_points': config.units.default_vehicle_movement * 0.53,  # Artillery is slowest
                'max_movement_points': config.units.default_vehicle_movement * 0.53,
                'sensor_range': config.units.default_sensor_range * 1.6,  # Good sensors for targeting
                'size': 1.8,
                'height': 2.8,
                'stealth': 0.0,
                'max_strength': 120.0
            },
            UnitType.AIR_DEFENSE: {
                'movement_type': MovementType.TRACKED,
                'movement_points': config.units.default_vehicle_movement * 0.6,  # AD systems are slow
                'max_movement_points': config.units.default_vehicle_movement * 0.6,
                'sensor_range': config.units.default_sensor_range * 4.0,  # Excellent air detection
                'size': 1.7,
                'height': 3.5,
                'stealth': 0.0,
                'max_strength': 130.0
            },
            UnitType.RECON: {
                'movement_type': MovementType.WHEELED,
                'movement_points': config.units.default_vehicle_movement,  # Full speed for recon
                'max_movement_points': config.units.default_vehicle_movement,
                'sensor_range': config.units.default_sensor_range * 4.0,  # Best sensors for recon
                'size': 1.2,
                'height': 2.0,
                'stealth': 0.4,
                'max_strength': 80.0
            },
            UnitType.ENGINEER: {
                'movement_type': MovementType.TRACKED,
                'movement_points': config.units.default_vehicle_movement * 0.53,  # Engineers are slow
                'max_movement_points': config.units.default_vehicle_movement * 0.53,
                'sensor_range': config.units.default_sensor_range,  # Standard sensors
                'size': 1.5,
                'height': 2.5,
                'stealth': 0.1,
                'max_strength': 110.0
            },
            UnitType.COMMAND: {
                'movement_type': MovementType.WHEELED,
                'movement_points': config.units.default_vehicle_movement * 0.8,  # Command vehicles moderately fast
                'max_movement_points': config.units.default_vehicle_movement * 0.8,
                'sensor_range': config.units.default_sensor_range * 2.0,  # Good sensors for situational awareness
                'communication_range': 3000.0,
                'size': 1.3,
                'height': 2.2,
                'stealth': 0.2,
                'max_strength': 90.0
            },
            UnitType.SUPPORT: {
                'movement_type': MovementType.WHEELED,
                'movement_points': config.units.default_vehicle_movement * 0.73,  # Support vehicles moderately fast
                'max_movement_points': config.units.default_vehicle_movement * 0.73,
                'sensor_range': config.units.default_sensor_range * 1.2,  # Slightly better sensors
                'size': 1.4,
                'height': 2.4,
                'stealth': 0.1,
                'max_strength': 100.0
            }
        }
        
        # Apply characteristics for this unit type
        if self.unit_type in characteristics:
            attrs = characteristics[self.unit_type]
            for attr_name, value in attrs.items():
                setattr(self, attr_name, value)
            
            # Set current values equal to max values
            self.movement_points = self.max_movement_points
            self.strength = self.max_strength
    
    @property
    def is_alive(self) -> bool:
        """Check if unit is still alive and operational."""
        return self.strength > 0 and self.is_active
    
    @property
    def is_mobile(self) -> bool:
        """Check if unit can move."""
        return self.is_alive and self.movement_points > 0 and self.suppression_level < 80.0
    
    @property
    def max_weapon_range(self) -> float:
        """Get maximum weapon range of all weapons."""
        if not self.weapons:
            return 0.0
        return max(weapon.max_range for weapon in self.weapons)
    
    @property
    def current_hex_coords(self) -> Optional[Tuple[int, int]]:
        """Get current hex coordinates as (q, r) tuple."""
        if self.position:
            return (self.position.q, self.position.r)
        return None
    
    def can_move_to(self, hex_cell: 'HexCell') -> bool:
        """Check if unit can move to a specific hex."""
        if not self.is_mobile:
            return False
        
        if not hex_cell.is_passable(self.movement_type.value):
            return False
        
        # Check if hex is already occupied by another unit
        if hex_cell.occupied_by and hex_cell.occupied_by != self:
            return False
        
        return True
    
    def movement_cost_to(self, hex_cell: 'HexCell') -> float:
        """Calculate movement cost to reach a hex."""
        if not self.can_move_to(hex_cell):
            return float('inf')
        
        return hex_cell.get_movement_cost(self.movement_type.value)
    
    def move_to(self, hex_cell: 'HexCell') -> bool:
        """Move unit to a new hex cell."""
        if not self.can_move_to(hex_cell):
            return False
        
        cost = self.movement_cost_to(hex_cell)
        if cost > self.movement_points:
            return False
        
        # Remove from current position
        if self.position:
            self.position.occupied_by = None
            # Check if any other units of same side are adjacent to maintain control
            # Otherwise, set to neutral
            self._update_hex_control(self.position)
        
        # Move to new position
        self.position = hex_cell
        hex_cell.occupied_by = self
        # Set control to this unit's side (use .value to get string)
        hex_cell.controlled_by = self.side.value
        self.movement_points -= cost
        
        return True
    
    def distance_to(self, target: 'Unit') -> float:
        """Calculate distance to another unit in meters."""
        if not self.position or not target.position:
            return float('inf')
        
        # Get hex centroids and calculate Euclidean distance
        x1, y1 = self.position.centroid
        x2, y2 = target.position.centroid
        return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    
    def hex_distance_to(self, target: 'Unit') -> int:
        """Calculate hex distance to another unit."""
        if not self.position or not target.position:
            return float('inf')
        
        return self.position.distance_to(target.position)
    
    def can_detect(self, target: 'Unit') -> bool:
        """Check if this unit can detect a target unit."""
        if not self.is_alive or not target.is_alive:
            return False
        
        distance = self.distance_to(target)
        if distance > self.sensor_range:
            return False
        
        # Stealth reduces detection probability
        detection_chance = 1.0 - target.stealth
        
        # Experience improves detection
        detection_chance *= (self.experience / 100.0)
        
        # Random element could be added here in actual simulation
        return detection_chance > 0.5  # Simplified for now
    
    def can_engage(self, target: 'Unit') -> bool:
        """Check if this unit can engage a target with any weapon."""
        if not self.is_alive or not target.is_alive:
            return False
        
        if target.side == self.side:
            return False  # Don't engage friendly units
        
        distance = self.distance_to(target)
        return any(weapon.can_engage(distance) for weapon in self.weapons)
    
    def engage_target(self, target: 'Unit', weapon_index: int = 0) -> Dict[str, Any]:
        """Engage a target with specified weapon."""
        if weapon_index >= len(self.weapons):
            return {"success": False, "message": "Invalid weapon"}
        
        weapon = self.weapons[weapon_index]
        distance = self.distance_to(target)
        
        if not weapon.can_engage(distance):
            return {"success": False, "message": "Target out of range"}
        
        # Calculate hit probability
        target_cover = 0.0
        if target.position:
            target_cover = target.position.get_cover_for_direction(self.facing)
        
        hit_prob = weapon.hit_probability(distance, target_cover)
        
        # For now, return the calculation. In actual simulation, 
        # this would involve random rolls and damage application
        return {
            "success": True,
            "weapon": weapon.name,
            "distance": distance,
            "hit_probability": hit_prob,
            "target_cover": target_cover
        }
    
    def take_damage(self, damage: float):
        """Apply damage to the unit."""
        self.strength = max(0.0, self.strength - damage)
        
        # High damage might affect morale
        if damage > 20.0:
            self.morale = max(0.0, self.morale - damage * 0.5)
        
        # Unit is destroyed if strength reaches zero
        if self.strength <= 0:
            self.is_active = False
    
    def restore_movement(self):
        """Restore movement points at start of turn."""
        self.movement_points = self.max_movement_points
        
        # Reduce suppression over time
        self.suppression_level = max(0.0, self.suppression_level - 10.0)
    
    def add_waypoint(self, q: int, r: int):
        """Add a waypoint to the unit's movement queue."""
        self.waypoints.append((q, r))
    
    def clear_waypoints(self):
        """Clear all waypoints."""
        self.waypoints.clear()
    
    def get_next_waypoint(self) -> Optional[Tuple[int, int]]:
        """Get the next waypoint in the queue."""
        if self.waypoints:
            return self.waypoints[0]
        return None
    
    def complete_waypoint(self):
        """Mark current waypoint as completed."""
        if self.waypoints:
            self.waypoints.pop(0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert unit to dictionary for serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'unit_type': self.unit_type.value,
            'side': self.side.value,
            'position': self.current_hex_coords,
            'facing': self.facing,
            'movement_type': self.movement_type.value,
            'movement_points': self.movement_points,
            'max_movement_points': self.max_movement_points,
            'strength': self.strength,
            'max_strength': self.max_strength,
            'morale': self.morale,
            'experience': self.experience,
            'sensor_range': self.sensor_range,
            'is_active': self.is_active,
            'is_hidden': self.is_hidden,
            'suppression_level': self.suppression_level,
            'waypoints': self.waypoints
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Unit':
        """Create unit from dictionary."""
        unit = cls(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', 'Unknown Unit'),
            unit_type=UnitType(data.get('unit_type', 'infantry_squad')),
            side=UnitSide(data.get('side', 'blue')),
            facing=data.get('facing', 0.0),
            movement_type=MovementType(data.get('movement_type', 'foot')),
            movement_points=data.get('movement_points', 10.0),
            max_movement_points=data.get('max_movement_points', 10.0),
            strength=data.get('strength', 100.0),
            max_strength=data.get('max_strength', 100.0),
            morale=data.get('morale', 100.0),
            experience=data.get('experience', 50.0),
            sensor_range=data.get('sensor_range', 500.0),
            is_active=data.get('is_active', True),
            is_hidden=data.get('is_hidden', False),
            suppression_level=data.get('suppression_level', 0.0),
            waypoints=data.get('waypoints', [])
        )
        return unit
    
    def _update_hex_control(self, hex_cell: 'HexCell'):
        """Update hex control based on nearby friendly units."""
        # For now, simply set to neutral when unit leaves
        # In future, could check for adjacent friendly units
        hex_cell.controlled_by = None
    
    def __str__(self) -> str:
        """String representation of the unit."""
        pos = f"({self.position.q}, {self.position.r})" if self.position else "(unpositioned)"
        return f"{self.name} ({self.unit_type.value}) - {self.side.value} at {pos}"
    
    def __repr__(self) -> str:
        """Detailed string representation."""
        return (f"Unit(id='{self.id}', name='{self.name}', type={self.unit_type.value}, "
                f"side={self.side.value}, strength={self.strength:.1f})")