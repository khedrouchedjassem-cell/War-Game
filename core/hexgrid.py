"""
Hexagonal grid generation and management system.
"""
import math
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from shapely.geometry import Polygon
import geopandas as gpd

from models.hexcell import HexCell
from utils.geo_utils import (
    axial_to_pixel, pixel_to_axial, hex_to_polygon, 
    create_hex_grid, calculate_distance
)
from utils.config import get_config


class HexGrid:
    """
    Manages a hexagonal grid system for the wargame simulation.
    
    Provides methods for grid generation, coordinate conversion,
    neighbor finding, and spatial queries.
    """
    
    def __init__(self, hex_size: Optional[float] = None, bounds: Optional[Tuple[float, float, float, float]] = None):
        """
        Initialize the hexagonal grid.
        
        Args:
            hex_size: Size of hexagons (distance from center to vertex) in map units. If None, uses config.
            bounds: Optional (minx, miny, maxx, maxy) bounding box
        """
        # Use config for hex_size if not provided
        if hex_size is None:
            config = get_config()
            hex_size = config.simulation.hex_size
        self.hex_size = hex_size
        self.bounds = bounds
        self.cells: Dict[Tuple[int, int], HexCell] = {}
        self._neighbors_cache: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        
        # Grid properties
        self.center_offset = (0.0, 0.0)
        self.is_generated = False
        
    def generate_grid(self, bounds: Tuple[float, float, float, float]) -> None:
        """
        Generate the hexagonal grid covering the specified bounds.
        
        Args:
            bounds: (minx, miny, maxx, maxy) bounding box to cover
        """
        self.bounds = bounds
        minx, miny, maxx, maxy = bounds
        
        # Set center offset to the middle of the bounds
        self.center_offset = (
            minx + (maxx - minx) / 2,
            miny + (maxy - miny) / 2
        )
        
        # Generate hex coordinates and polygons
        hex_data = create_hex_grid(bounds, self.hex_size)
        
        # Create HexCell objects
        self.cells.clear()
        for q, r, centroid, polygon in hex_data:
            hex_cell = HexCell(
                q=q,
                r=r,
                centroid=centroid,
                polygon=polygon
            )
            self.cells[(q, r)] = hex_cell
        
        self.is_generated = True
        print(f"Generated {len(self.cells)} hexagonal cells")
    
    def get_cell(self, q: int, r: int) -> Optional[HexCell]:
        """Get hex cell at axial coordinates (q, r)."""
        return self.cells.get((q, r))
    
    def get_cell_at_position(self, x: float, y: float) -> Optional[HexCell]:
        """Get hex cell at world coordinates (x, y)."""
        q, r = pixel_to_axial(x, y, self.hex_size, self.center_offset)
        return self.get_cell(q, r)
    
    def get_neighbors(self, q: int, r: int) -> List[HexCell]:
        """Get neighboring hex cells."""
        # Check cache first
        if (q, r) in self._neighbors_cache:
            neighbor_coords = self._neighbors_cache[(q, r)]
        else:
            # Calculate neighbor coordinates
            directions = [
                (1, 0), (1, -1), (0, -1),
                (-1, 0), (-1, 1), (0, 1)
            ]
            neighbor_coords = [(q + dq, r + dr) for dq, dr in directions]
            self._neighbors_cache[(q, r)] = neighbor_coords
        
        # Return actual hex cells that exist
        neighbors = []
        for nq, nr in neighbor_coords:
            cell = self.get_cell(nq, nr)
            if cell:
                neighbors.append(cell)
        
        return neighbors
    
    def get_cells_in_radius(self, q: int, r: int, radius: int) -> List[HexCell]:
        """Get all hex cells within a given radius."""
        cells = []
        
        for dq in range(-radius, radius + 1):
            for dr in range(max(-radius, -dq - radius), min(radius, -dq + radius) + 1):
                cell = self.get_cell(q + dq, r + dr)
                if cell:
                    cells.append(cell)
        
        return cells
    
    def get_cells_in_range(self, center_x: float, center_y: float, 
                          max_distance: float) -> List[HexCell]:
        """Get all hex cells within a distance from a world coordinate point."""
        cells = []
        
        for cell in self.cells.values():
            distance = calculate_distance((center_x, center_y), cell.centroid)
            if distance <= max_distance:
                cells.append(cell)
        
        return cells
    
    def hex_distance(self, q1: int, r1: int, q2: int, r2: int) -> int:
        """Calculate distance between two hex cells in hex units."""
        # Convert to cube coordinates
        x1, y1, z1 = q1, -q1 - r1, r1
        x2, y2, z2 = q2, -q2 - r2, r2
        
        return max(abs(x1 - x2), abs(y1 - y2), abs(z1 - z2))
    
    def world_distance(self, q1: int, r1: int, q2: int, r2: int) -> float:
        """Calculate world distance between two hex cells."""
        cell1 = self.get_cell(q1, r1)
        cell2 = self.get_cell(q2, r2)
        
        if not cell1 or not cell2:
            return float('inf')
        
        return calculate_distance(cell1.centroid, cell2.centroid)
    
    def get_line_of_hexes(self, q1: int, r1: int, q2: int, r2: int) -> List[Tuple[int, int]]:
        """
        Get a line of hex coordinates from one hex to another.
        Uses cube coordinate lerp for smooth lines.
        """
        distance = self.hex_distance(q1, r1, q2, r2)
        if distance == 0:
            return [(q1, r1)]
        
        # Convert to cube coordinates
        x1, y1, z1 = q1, -q1 - r1, r1
        x2, y2, z2 = q2, -q2 - r2, r2
        
        results = []
        for i in range(distance + 1):
            t = i / distance
            
            # Linear interpolation in cube space
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            z = z1 + (z2 - z1) * t
            
            # Round to nearest hex
            rx = round(x)
            ry = round(y)
            rz = round(z)
            
            # Correct rounding errors
            x_diff = abs(rx - x)
            y_diff = abs(ry - y)
            z_diff = abs(rz - z)
            
            if x_diff > y_diff and x_diff > z_diff:
                rx = -ry - rz
            elif y_diff > z_diff:
                ry = -rx - rz
            else:
                rz = -rx - ry
            
            # Convert back to axial
            q = rx
            r = rz
            results.append((q, r))
        
        return results
    
    def get_ring(self, q: int, r: int, radius: int) -> List[HexCell]:
        """Get hex cells forming a ring at the specified radius."""
        if radius == 0:
            cell = self.get_cell(q, r)
            return [cell] if cell else []
        
        cells = []
        
        # Start at one corner of the ring
        hex_q = q - radius
        hex_r = r + radius
        
        # The six directions to traverse the ring
        directions = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
        
        for direction in directions:
            dq, dr = direction
            for _ in range(radius):
                cell = self.get_cell(hex_q, hex_r)
                if cell:
                    cells.append(cell)
                hex_q += dq
                hex_r += dr
        
        return cells
    
    def get_field_of_view(self, q: int, r: int, radius: int, 
                         facing: float, fov_angle: float = 60.0) -> List[HexCell]:
        """
        Get hex cells within field of view cone.
        
        Args:
            q, r: Center hex coordinates
            radius: Maximum range
            facing: Direction facing in degrees (0 = North)
            fov_angle: Field of view angle in degrees
        """
        cells = []
        center_cell = self.get_cell(q, r)
        if not center_cell:
            return cells
        
        center_x, center_y = center_cell.centroid
        
        # Convert facing to radians
        facing_rad = math.radians(facing)
        fov_rad = math.radians(fov_angle)
        
        for cell in self.get_cells_in_radius(q, r, radius):
            if cell == center_cell:
                continue
            
            # Calculate angle to this cell
            dx = cell.centroid[0] - center_x
            dy = cell.centroid[1] - center_y
            
            angle_to_cell = math.atan2(dx, dy)  # atan2(x, y) for North = 0
            angle_diff = abs(angle_to_cell - facing_rad)
            
            # Normalize angle difference to [0, π]
            if angle_diff > math.pi:
                angle_diff = 2 * math.pi - angle_diff
            
            # Check if within field of view
            if angle_diff <= fov_rad / 2:
                cells.append(cell)
        
        return cells
    
    def get_cells_by_terrain(self, terrain_type: str) -> List[HexCell]:
        """Get all cells with a specific terrain type."""
        return [cell for cell in self.cells.values() 
                if cell.terrain_type == terrain_type]
    
    def get_passable_neighbors(self, q: int, r: int, movement_type: str = "infantry") -> List[HexCell]:
        """Get neighboring cells that are passable for the given movement type."""
        neighbors = self.get_neighbors(q, r)
        return [cell for cell in neighbors if cell.is_passable(movement_type)]
    
    def to_geodataframe(self) -> gpd.GeoDataFrame:
        """Convert the hex grid to a GeoDataFrame for export/visualization."""
        data = []
        
        for cell in self.cells.values():
            cell_data = cell.to_dict()
            cell_data['geometry'] = cell.polygon
            data.append(cell_data)
        
        return gpd.GeoDataFrame(data)
    
    def save_to_file(self, filename: str, driver: str = "GeoJSON"):
        """Save the hex grid to a file."""
        gdf = self.to_geodataframe()
        gdf.to_file(filename, driver=driver)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the hex grid."""
        if not self.cells:
            return {}
        
        terrain_counts = {}
        elevation_values = []
        slope_values = []
        
        for cell in self.cells.values():
            # Count terrain types
            terrain = cell.terrain_type
            terrain_counts[terrain] = terrain_counts.get(terrain, 0) + 1
            
            # Collect elevation and slope data
            elevation_values.append(cell.elevation_mean)
            slope_values.append(cell.slope)
        
        return {
            'total_cells': len(self.cells),
            'hex_size': self.hex_size,
            'bounds': self.bounds,
            'terrain_distribution': terrain_counts,
            'elevation_stats': {
                'min': min(elevation_values) if elevation_values else 0,
                'max': max(elevation_values) if elevation_values else 0,
                'mean': sum(elevation_values) / len(elevation_values) if elevation_values else 0
            },
            'slope_stats': {
                'min': min(slope_values) if slope_values else 0,
                'max': max(slope_values) if slope_values else 0,
                'mean': sum(slope_values) / len(slope_values) if slope_values else 0
            }
        }
    
    def clear(self):
        """Clear all cells from the grid."""
        self.cells.clear()
        self._neighbors_cache.clear()
        self.is_generated = False
    
    def __len__(self) -> int:
        """Return number of cells in the grid."""
        return len(self.cells)
    
    def __contains__(self, coords: Tuple[int, int]) -> bool:
        """Check if coordinates exist in the grid."""
        return coords in self.cells
    
    def __iter__(self):
        """Iterate over all cells in the grid."""
        return iter(self.cells.values())
    
    def __getitem__(self, coords: Tuple[int, int]) -> Optional[HexCell]:
        """Get cell by coordinates using grid[q, r] syntax."""
        return self.cells.get(coords)