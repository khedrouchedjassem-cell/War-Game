"""
Line-of-sight calculations using terrain elevation and obstacles.
"""
import math
import numpy as np
from typing import List, Tuple, Set, Optional, Dict
from dataclasses import dataclass

from core.hexgrid import HexGrid
from models.hexcell import HexCell
from models.unit import Unit
from utils.geo_utils import calculate_distance


@dataclass
class LOSPoint:
    """
    Represents a point along a line of sight with elevation information.
    """
    x: float
    y: float
    ground_elevation: float
    obstacle_height: float = 0.0
    
    @property
    def total_height(self) -> float:
        """Total height including obstacles."""
        return self.ground_elevation + self.obstacle_height


class LineOfSight:
    """
    Calculates line-of-sight between units using terrain elevation and obstacles.
    
    Uses ray-casting with terrain sampling to determine visibility,
    considering ground elevation, vegetation, buildings, and unit heights.
    """
    
    def __init__(self, hex_grid: HexGrid):
        """
        Initialize line-of-sight calculator.
        
        Args:
            hex_grid: HexGrid instance for terrain data
        """
        self.hex_grid = hex_grid
        self.sampling_interval = 5.0  # Sample every 5 meters
        self.earth_curvature = False  # Enable for very long distances
        self.atmospheric_refraction = 1.0  # Atmospheric refraction factor
        
        # LOS cache for performance
        self._los_cache: Dict[Tuple[Tuple[int, int], Tuple[int, int]], bool] = {}
        self._cache_max_size = 10000
    
    def can_see(self, observer: Unit, target: Unit, 
               consider_stealth: bool = True) -> bool:
        """
        Check if observer unit can see target unit.
        
        Args:
            observer: Observer unit
            target: Target unit
            consider_stealth: Whether to consider target stealth rating
            
        Returns:
            True if observer can see target
        """
        if not observer.position or not target.position:
            return False
        
        # Check basic visibility conditions
        if not observer.is_alive or not target.is_alive:
            return False
        
        # Calculate distance
        distance = observer.distance_to(target)
        
        # Check if within sensor range
        if distance > observer.sensor_range:
            return False
        
        # Check line of sight
        has_los = self.has_line_of_sight(
            observer.position, target.position,
            observer.height, target.height
        )
        
        if not has_los:
            return False
        
        # Apply stealth considerations
        if consider_stealth:
            detection_probability = self._calculate_detection_probability(
                observer, target, distance
            )
            # For deterministic results, use threshold
            return detection_probability > 0.6
        
        return True
    
    def has_line_of_sight(self, from_cell: HexCell, to_cell: HexCell,
                         observer_height: float = 2.0, target_height: float = 2.0) -> bool:
        """
        Check if there's a clear line of sight between two hex cells.
        
        Args:
            from_cell: Observer hex cell
            to_cell: Target hex cell
            observer_height: Height of observer above ground
            target_height: Height of target above ground
            
        Returns:
            True if line of sight exists
        """
        # Check cache first
        cache_key = ((from_cell.q, from_cell.r), (to_cell.q, to_cell.r))
        if cache_key in self._los_cache:
            return self._los_cache[cache_key]
        
        # Calculate LOS
        result = self._calculate_line_of_sight(from_cell, to_cell, observer_height, target_height)
        
        # Cache result
        if len(self._los_cache) >= self._cache_max_size:
            # Remove oldest entries (simple FIFO)
            keys_to_remove = list(self._los_cache.keys())[:1000]
            for key in keys_to_remove:
                del self._los_cache[key]
        
        self._los_cache[cache_key] = result
        return result
    
    def get_visible_hexes(self, observer: Unit, max_range: Optional[float] = None) -> List[HexCell]:
        """
        Get all hex cells visible from observer position.
        
        Args:
            observer: Observer unit
            max_range: Maximum visibility range (uses sensor_range if None)
            
        Returns:
            List of visible hex cells
        """
        if not observer.position:
            return []
        
        if max_range is None:
            max_range = observer.sensor_range
        
        visible_hexes = []
        observer_cell = observer.position
        
        # Get all hexes within range
        nearby_hexes = self.hex_grid.get_cells_in_range(
            observer_cell.centroid[0], observer_cell.centroid[1], max_range
        )
        
        for hex_cell in nearby_hexes:
            if hex_cell == observer_cell:
                continue  # Always can see own position
            
            if self.has_line_of_sight(observer_cell, hex_cell, observer.height):
                visible_hexes.append(hex_cell)
        
        return visible_hexes
    
    def get_field_of_view_hexes(self, observer: Unit, facing: float, 
                              fov_angle: float = 120.0, max_range: Optional[float] = None) -> List[HexCell]:
        """
        Get hex cells within field of view cone.
        
        Args:
            observer: Observer unit
            facing: Direction facing in degrees (0 = North)
            fov_angle: Field of view angle in degrees
            max_range: Maximum visibility range
            
        Returns:
            List of hex cells within FOV
        """
        if not observer.position:
            return []
        
        if max_range is None:
            max_range = observer.sensor_range
        
        # Get hexes in FOV cone
        fov_hexes = self.hex_grid.get_field_of_view(
            observer.position.q, observer.position.r,
            int(max_range / 30),  # Convert to hex radius
            facing, fov_angle
        )
        
        # Filter by line of sight
        visible_hexes = []
        observer_cell = observer.position
        
        for hex_cell in fov_hexes:
            if self.has_line_of_sight(observer_cell, hex_cell, observer.height):
                visible_hexes.append(hex_cell)
        
        return visible_hexes
    
    def calculate_detection_range(self, observer: Unit, target: Unit) -> float:
        """
        Calculate effective detection range considering conditions.
        
        Args:
            observer: Observer unit
            target: Target unit
            
        Returns:
            Effective detection range in meters
        """
        base_range = observer.sensor_range
        
        # Modify based on target stealth
        stealth_factor = 1.0 - target.stealth
        
        # Modify based on target concealment
        if target.position:
            concealment_factor = 1.0 - target.position.concealment
        else:
            concealment_factor = 1.0
        
        # Modify based on observer experience
        experience_factor = 0.5 + (observer.experience / 100.0) * 0.5
        
        return base_range * stealth_factor * concealment_factor * experience_factor
    
    def _calculate_line_of_sight(self, from_cell: HexCell, to_cell: HexCell,
                               observer_height: float, target_height: float) -> bool:
        """
        Calculate line of sight using terrain sampling.
        
        Args:
            from_cell: Observer hex cell
            to_cell: Target hex cell
            observer_height: Height of observer above ground
            target_height: Height of target above ground
            
        Returns:
            True if line of sight exists
        """
        # Get start and end points
        start_x, start_y = from_cell.centroid
        end_x, end_y = to_cell.centroid
        
        # Calculate distance and number of sample points
        distance = calculate_distance((start_x, start_y), (end_x, end_y))
        
        if distance == 0:
            return True  # Same position
        
        num_samples = max(10, int(distance / self.sampling_interval))
        
        # Sample points along the line
        los_points = self._sample_line_of_sight(
            start_x, start_y, end_x, end_y, num_samples
        )
        
        if not los_points:
            return False
        
        # Calculate observer and target eye heights
        observer_eye_height = from_cell.elevation_mean + observer_height
        target_eye_height = to_cell.elevation_mean + target_height
        
        # Check if any point blocks the line of sight
        return self._check_line_clearance(
            los_points, observer_eye_height, target_eye_height
        )
    
    def _sample_line_of_sight(self, start_x: float, start_y: float,
                            end_x: float, end_y: float, num_samples: int) -> List[LOSPoint]:
        """
        Sample elevation and obstacles along line of sight.
        
        Args:
            start_x, start_y: Starting coordinates
            end_x, end_y: Ending coordinates
            num_samples: Number of sample points
            
        Returns:
            List of LOS points with elevation data
        """
        los_points = []
        
        for i in range(num_samples + 1):
            t = i / num_samples
            
            # Interpolate position
            x = start_x + t * (end_x - start_x)
            y = start_y + t * (end_y - start_y)
            
            # Get hex cell at this position
            hex_cell = self.hex_grid.get_cell_at_position(x, y)
            
            if hex_cell:
                # Get ground elevation
                ground_elevation = hex_cell.elevation_mean
                
                # Calculate obstacle height
                obstacle_height = self._get_obstacle_height(hex_cell)
                
                los_points.append(LOSPoint(x, y, ground_elevation, obstacle_height))
            else:
                # Use default values for out-of-bounds areas
                los_points.append(LOSPoint(x, y, 0.0, 0.0))
        
        return los_points
    
    def _get_obstacle_height(self, hex_cell: HexCell) -> float:
        """
        Calculate obstacle height above ground for a hex cell.
        
        Args:
            hex_cell: Hex cell to check
            
        Returns:
            Height of obstacles above ground level
        """
        obstacle_height = 0.0
        
        # Buildings
        if hex_cell.has_buildings:
            obstacle_height = max(obstacle_height, 10.0)  # Average building height
        
        # Vegetation
        if hex_cell.land_use.lower() in ['forest', 'woodland', 'trees']:
            obstacle_height = max(obstacle_height, 15.0)  # Average tree height
        elif hex_cell.terrain_type == 'forest':
            obstacle_height = max(obstacle_height, 12.0)
        
        return obstacle_height
    
    def _check_line_clearance(self, los_points: List[LOSPoint], 
                            observer_height: float, target_height: float) -> bool:
        """
        Check if line of sight is clear of obstacles.
        
        Args:
            los_points: Sample points along line of sight
            observer_height: Observer eye height
            target_height: Target eye height
            
        Returns:
            True if line is clear
        """
        if len(los_points) < 2:
            return True
        
        # Calculate line of sight angles at each point
        for i in range(1, len(los_points) - 1):
            point = los_points[i]
            
            # Calculate distance from observer
            observer_point = los_points[0]
            target_point = los_points[-1]
            
            dist_from_observer = calculate_distance(
                (observer_point.x, observer_point.y),
                (point.x, point.y)
            )
            
            total_distance = calculate_distance(
                (observer_point.x, observer_point.y),
                (target_point.x, target_point.y)
            )
            
            if total_distance == 0:
                continue
            
            # Calculate required height for clear line of sight
            t = dist_from_observer / total_distance
            required_height = observer_height + t * (target_height - observer_height)
            
            # Apply Earth curvature correction (for long distances)
            if self.earth_curvature and total_distance > 1000:
                curvature_drop = self._calculate_earth_curvature(dist_from_observer, total_distance)
                required_height -= curvature_drop
            
            # Check if obstacle blocks line of sight
            if point.total_height > required_height:
                return False
        
        return True
    
    def _calculate_earth_curvature(self, distance: float, total_distance: float) -> float:
        """
        Calculate earth curvature drop for long-distance LOS.
        
        Args:
            distance: Distance from observer to point
            total_distance: Total LOS distance
            
        Returns:
            Height drop due to earth curvature
        """
        earth_radius = 6371000  # Earth radius in meters
        
        # Simplified earth curvature calculation
        curvature_drop = (distance * distance) / (2 * earth_radius)
        return curvature_drop * self.atmospheric_refraction
    
    def _calculate_detection_probability(self, observer: Unit, target: Unit, distance: float) -> float:
        """
        Calculate probability of detection considering various factors.
        
        Args:
            observer: Observer unit
            target: Target unit
            distance: Distance between units
            
        Returns:
            Detection probability (0.0 to 1.0)
        """
        # Base probability starts high and decreases with distance
        base_prob = max(0.1, 1.0 - (distance / observer.sensor_range))
        
        # Observer skill affects detection
        skill_factor = 0.5 + (observer.experience / 100.0) * 0.5
        
        # Target stealth reduces detection
        stealth_factor = 1.0 - target.stealth
        
        # Target concealment reduces detection
        concealment_factor = 1.0
        if target.position:
            concealment_factor = 1.0 - target.position.concealment
        
        # Movement increases detection (moving targets are easier to spot)
        movement_factor = 1.0
        if target.movement_points < target.max_movement_points:
            movement_factor = 1.2  # Recently moved
        
        # Combine all factors
        detection_prob = base_prob * skill_factor * stealth_factor * concealment_factor * movement_factor
        
        return max(0.0, min(1.0, detection_prob))
    
    def get_mutual_visibility(self, units: List[Unit]) -> Dict[Tuple[str, str], bool]:
        """
        Calculate mutual visibility between all pairs of units.
        
        Args:
            units: List of units to check
            
        Returns:
            Dictionary mapping (unit1_id, unit2_id) to visibility
        """
        visibility = {}
        
        for i, unit1 in enumerate(units):
            for j, unit2 in enumerate(units):
                if i != j:
                    can_see = self.can_see(unit1, unit2)
                    visibility[(unit1.id, unit2.id)] = can_see
        
        return visibility
    
    def clear_cache(self):
        """Clear the LOS cache."""
        self._los_cache.clear()
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            'cache_size': len(self._los_cache),
            'cache_max_size': self._cache_max_size
        }