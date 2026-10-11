"""
HexCell model for representing hexagonal grid cells with terrain and game attributes.
"""
from typing import Optional, Dict, Tuple, Any, List
from dataclasses import dataclass, field
import numpy as np
from utils.config import get_config
from models.unit import Unit



@dataclass
class HexCell:
    """
    Represents a single hexagonal cell in the game grid.
    
    Uses axial coordinates (q, r) for hexagonal grid math.
    Contains terrain attributes, movement costs, and gameplay state.
    """
    
    # Grid coordinates
    q: int  # Axial coordinate q
    r: int  # Axial coordinate r
    
    # Geographic properties
    centroid: Tuple[float, float]  # (x, y) in map coordinates
    polygon: Optional[Any] = None  # Shapely polygon geometry
    
    # Terrain attributes
    elevation_mean: float = 0.0
    elevation_min: float = 0.0
    elevation_max: float = 0.0
    slope: float = 0.0  # Average slope in degrees
    
    # Land cover and terrain
    terrain_type: str = "unknown"  # primary terrain type
    has_roads: bool = False
    has_buildings: bool = False
    has_water: bool = False
    land_use: str = "unknown"
    
    # Gameplay attributes
    movement_cost: Dict[str, float] = field(default_factory=lambda: {
        "infantry": 1.0,
        "vehicle": 1.0,
        "aircraft": 1.0
    })
    cover_value: float = 0.0  # 0.0 = no cover, 1.0 = full cover
    concealment: float = 0.0  # 0.0 = no concealment, 1.0 = full concealment
    los_blocking_height: float = 0.0  # Height that blocks line of sight
    
    # Game state
    occupied_by: Optional['Unit'] = None  # Reference to unit in this hex
    controlled_by: Optional[str] = None  # Which side controls this hex
    visibility: Dict[str, float] = field(default_factory=dict)  # Visibility by side
    
    # Edge-based features (for roads, waterways, borders)
    # Each hex has 6 edges numbered 0-5 clockwise from top
    # Edge 0: top, Edge 1: top-right, Edge 2: bottom-right, Edge 3: bottom, Edge 4: bottom-left, Edge 5: top-left
    edge_waterways: Dict[int, List[Dict[str, Any]]] = field(default_factory=dict)  # Waterways on each edge
    edge_roads: Dict[int, List[Dict[str, Any]]] = field(default_factory=dict)  # Roads on each edge
    
    def __post_init__(self):
        """Initialize computed properties after dataclass creation."""
        if not self.polygon:
            from utils.geo_utils import hex_to_polygon
            # Use config for hex_size
            config = get_config()
            self.polygon = hex_to_polygon(self.q, self.r, size=config.simulation.hex_size, center=self.centroid)
    
    @property
    def id(self) -> str:
        """Unique identifier for this hex cell."""
        return f"hex_{self.q}_{self.r}"
    
    @property
    def cube_coordinates(self) -> Tuple[int, int, int]:
        """Convert axial coordinates to cube coordinates (x, y, z)."""
        x = self.q
        z = self.r
        y = -x - z
        return (x, y, z)
    
    @property
    def neighbors(self) -> list[Tuple[int, int]]:
        """Get the six neighboring hex coordinates in axial system."""
        directions = [
            (1, 0), (1, -1), (0, -1),
            (-1, 0), (-1, 1), (0, 1)
        ]
        return [(self.q + dq, self.r + dr) for dq, dr in directions]
    
    def distance_to(self, other: 'HexCell') -> int:
        """Calculate hex distance to another cell using cube coordinates."""
        x1, y1, z1 = self.cube_coordinates
        x2, y2, z2 = other.cube_coordinates
        return max(abs(x1 - x2), abs(y1 - y2), abs(z1 - z2))
    
    def is_passable(self, movement_type: str = "infantry") -> bool:
        """Check if this hex is passable for a given movement type."""
        if self.occupied_by is not None:
            return False
        
        # Water is generally impassable for ground units
        if self.has_water and movement_type in ["infantry", "vehicle"]:
            return False
        
        # Very steep terrain might be impassable for vehicles
        if movement_type == "vehicle" and self.slope > 45.0:
            return False
        
        return True
    
    def get_movement_cost(self, movement_type: str = "infantry") -> float:
        """Get movement cost for a specific movement type."""
        if not self.is_passable(movement_type):
            return float('inf')
        
        base_cost = self.movement_cost.get(movement_type, 1.0)
        
        # Modify cost based on terrain features
        if self.has_roads and movement_type == "vehicle":
            base_cost *= 0.5  # Roads make vehicle movement easier
        
        if self.terrain_type == "forest":
            if movement_type == "infantry":
                base_cost *= 1.5
            elif movement_type == "vehicle":
                base_cost *= 2.0
        
        # Slope affects movement cost
        if self.slope > 0:
            slope_multiplier = 1.0 + (self.slope / 45.0)  # Max 2x cost at 45 degrees
            base_cost *= slope_multiplier
        
        return base_cost
    
    def update_visibility(self, side: str, visibility: float):
        """Update visibility of this hex for a specific side."""
        self.visibility[side] = max(0.0, min(1.0, visibility))
    
    def is_visible_to(self, side: str) -> bool:
        """Check if this hex is visible to a specific side."""
        return self.visibility.get(side, 0.0) > 0.0
    
    def get_cover_for_direction(self, from_direction: float) -> float:
        """Get cover value for attacks from a specific direction."""
        # This could be enhanced to consider directional cover
        # For now, return base cover value
        cover = self.cover_value
        
        # Buildings provide additional cover
        if self.has_buildings:
            cover = max(cover, 0.7)
        
        # Forests provide moderate cover
        if self.terrain_type == "forest":
            cover = max(cover, 0.4)
        
        return min(1.0, cover)
    
    def get_edge_coordinates(self, edge_index: int) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """Get world coordinates of a hex edge.
        
        Args:
            edge_index: Edge number (0-5, clockwise from top)
            
        Returns:
            Tuple of (start_point, end_point) coordinates
        """
        if not self.polygon:
            return ((0, 0), (0, 0))
        
        coords = list(self.polygon.exterior.coords)
        if len(coords) < 7:  # Should have 7 coordinates (6 vertices + closing)
            return ((0, 0), (0, 0))
        
        # Get the edge vertices
        start_point = coords[edge_index]
        end_point = coords[(edge_index + 1) % 6]
        
        return (start_point, end_point)
    
    def add_edge_waterway(self, edge_index: int, waterway_data: Dict[str, Any]):
        """Add a waterway to a specific edge.
        
        Args:
            edge_index: Edge number (0-5)
            waterway_data: Waterway information
        """
        if edge_index not in self.edge_waterways:
            self.edge_waterways[edge_index] = []
        self.edge_waterways[edge_index].append(waterway_data)
        self.has_water = True
    
    def add_edge_road(self, edge_index: int, road_data: Dict[str, Any]):
        """Add a road to a specific edge.
        
        Args:
            edge_index: Edge number (0-5)
            road_data: Road information
        """
        if edge_index not in self.edge_roads:
            self.edge_roads[edge_index] = []
        self.edge_roads[edge_index].append(road_data)
        self.has_roads = True
    
    def get_waterway_edges(self) -> List[int]:
        """Get list of edges that have waterways.
        
        Returns:
            List of edge indices with waterways
        """
        return list(self.edge_waterways.keys())
    
    def get_road_edges(self) -> List[int]:
        """Get list of edges that have roads.
        
        Returns:
            List of edge indices with roads
        """
        return list(self.edge_roads.keys())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert hex cell to dictionary for serialization."""
        return {
            'q': self.q,
            'r': self.r,
            'centroid': self.centroid,
            'elevation_mean': self.elevation_mean,
            'elevation_min': self.elevation_min,
            'elevation_max': self.elevation_max,
            'slope': self.slope,
            'terrain_type': self.terrain_type,
            'has_roads': self.has_roads,
            'has_buildings': self.has_buildings,
            'has_water': self.has_water,
            'land_use': self.land_use,
            'movement_cost': self.movement_cost,
            'cover_value': self.cover_value,
            'concealment': self.concealment,
            'los_blocking_height': self.los_blocking_height,
            'controlled_by': self.controlled_by,
            'visibility': self.visibility
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HexCell':
        """Create hex cell from dictionary."""
        return cls(
            q=data['q'],
            r=data['r'],
            centroid=tuple(data['centroid']),
            elevation_mean=data.get('elevation_mean', 0.0),
            elevation_min=data.get('elevation_min', 0.0),
            elevation_max=data.get('elevation_max', 0.0),
            slope=data.get('slope', 0.0),
            terrain_type=data.get('terrain_type', 'unknown'),
            has_roads=data.get('has_roads', False),
            has_buildings=data.get('has_buildings', False),
            has_water=data.get('has_water', False),
            land_use=data.get('land_use', 'unknown'),
            movement_cost=data.get('movement_cost', {}),
            cover_value=data.get('cover_value', 0.0),
            concealment=data.get('concealment', 0.0),
            los_blocking_height=data.get('los_blocking_height', 0.0),
            controlled_by=data.get('controlled_by'),
            visibility=data.get('visibility', {})
        )
    
    def __str__(self) -> str:
        """String representation of the hex cell."""
        return f"HexCell({self.q}, {self.r}) - {self.terrain_type} @ {self.elevation_mean:.1f}m"
    
    def __repr__(self) -> str:
        """Detailed string representation."""
        return (f"HexCell(q={self.q}, r={self.r}, terrain='{self.terrain_type}', "
                f"elevation={self.elevation_mean:.1f}, slope={self.slope:.1f})")