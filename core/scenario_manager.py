"""
Comprehensive scenario management system for saving/loading complete game states.
Includes terrain data, hex cells, roads, waterways, and application settings.
"""
import json
import numpy as np
import geopandas as gpd
from typing import Dict, List, Any, Optional
from pathlib import Path
import time
from datetime import datetime

from core.hexgrid import HexGrid
from models.hexcell import HexCell
from core.terrain import TerrainAnalyzer


class ScenarioManager:
    """
    Efficient scenario saving and loading with compression and metadata.
    Handles complete game state including terrain, roads, waterways, and settings.
    """
    
    def __init__(self):
        """Initialize scenario manager."""
        self.scenario_version = "1.0"
        
    def _json_serializer(self, obj):
        """Custom JSON serializer for NumPy and other non-JSON types."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif hasattr(obj, '__geo_interface__'):
            return obj.__geo_interface__
        else:
            return str(obj)
        
    def save_scenario(self, 
                     scenario_path: str,
                     hex_grid: HexGrid,
                     terrain_analyzer: TerrainAnalyzer,
                     roads_data: List[Dict[str, Any]],
                     waterways_data: List[Dict[str, Any]],
                     app_settings: Dict[str, Any],
                     metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Save complete scenario to compressed file.
        
        Args:
            scenario_path: Path to save scenario file
            hex_grid: Complete hex grid with analyzed terrain
            terrain_analyzer: Terrain analyzer instance
            roads_data: Road network information
            waterways_data: Waterway network information
            app_settings: Application configuration settings
            metadata: Optional scenario metadata
            
        Returns:
            True if save successful, False otherwise
        """
        try:
            print(f"Saving scenario to {scenario_path}...")
            start_time = time.time()
            
            # Prepare scenario data structure
            scenario_data = {
                'version': self.scenario_version,
                'timestamp': datetime.now().isoformat(),
                'metadata': metadata or {},
                'hex_grid_info': {
                    'hex_size': hex_grid.hex_size,
                    'bounds': hex_grid.bounds,
                    'center_offset': hex_grid.center_offset
                },
                'terrain_data': self._serialize_terrain_data(terrain_analyzer),
                'hex_cells': self._serialize_hex_cells(hex_grid),
                'roads': self._serialize_roads_data(roads_data),
                'waterways': self._serialize_waterways_data(waterways_data),
                'settings': app_settings,
                'statistics': self._generate_scenario_stats(hex_grid, roads_data, waterways_data)
            }
            
            # Save as JSON
            scenario_path = Path(scenario_path)
            scenario_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Change extension to .json
            json_path = scenario_path.with_suffix('.json')
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(scenario_data, f, indent=2, ensure_ascii=False, default=self._json_serializer)
            
            save_time = time.time() - start_time
            file_size = json_path.stat().st_size / (1024 * 1024)
            
            print(f"Scenario saved successfully!")
            print(f"   File: {json_path}")
            print(f"   Size: {file_size:.2f} MB")
            print(f"   Time: {save_time:.2f} seconds")
            
            return True
            
        except Exception as e:
            print(f"❌ Error saving scenario: {e}")
            return False
    
    def load_scenario(self, scenario_path: str) -> Optional[Dict[str, Any]]:
        """
        Load complete scenario from JSON file.
        
        Args:
            scenario_path: Path to scenario file
            
        Returns:
            Scenario data dictionary or None if failed
        """
        try:
            print(f"Loading scenario from {scenario_path}...")
            start_time = time.time()
            
            scenario_path = Path(scenario_path)
            if not scenario_path.exists():
                # Try with .json extension
                scenario_path = scenario_path.with_suffix('.json')
                if not scenario_path.exists():
                    print(f"❌ Scenario file not found: {scenario_path}")
                    return None
            
            with open(scenario_path, 'r', encoding='utf-8') as f:
                scenario_data = json.load(f)
            
            # Validate scenario version
            if scenario_data.get('version') != self.scenario_version:
                print(f"Warning: Scenario version mismatch. "
                      f"Expected {self.scenario_version}, got {scenario_data.get('version')}")
            
            load_time = time.time() - start_time
            print(f"Scenario loaded successfully in {load_time:.2f} seconds")
            
            return scenario_data
            
        except Exception as e:
            print(f"❌ Error loading scenario: {e}")
            return None
    
    def _serialize_terrain_data(self, terrain_analyzer: TerrainAnalyzer) -> Dict[str, Any]:
        """
        Serialize terrain analyzer data efficiently.
        
        Args:
            terrain_analyzer: TerrainAnalyzer instance
            
        Returns:
            Serialized terrain data
        """
        terrain_data = {
            'data_directory': str(terrain_analyzer.data_dir),
            'common_crs': terrain_analyzer.common_crs,
            'elevation_bounds': terrain_analyzer.get_elevation_bounds(),
            'data_bounds': terrain_analyzer.get_data_bounds(),
            'terrain_config': {
                'terrain_classification': terrain_analyzer.terrain_classification,
                'movement_costs': terrain_analyzer.movement_costs,
                'cover_values': terrain_analyzer.cover_values,
                'los_blocking': terrain_analyzer.los_blocking
            }
        }
        
        # Store elevation data statistics (not full raster for efficiency)
        if terrain_analyzer.elevation_data is not None:
            terrain_data['elevation_stats'] = {
                'shape': terrain_analyzer.elevation_data.shape,
                'dtype': str(terrain_analyzer.elevation_data.dtype),
                'min': float(np.nanmin(terrain_analyzer.elevation_data)),
                'max': float(np.nanmax(terrain_analyzer.elevation_data)),
                'mean': float(np.nanmean(terrain_analyzer.elevation_data))
            }
        
        return terrain_data
    
    def _serialize_hex_cells(self, hex_grid: HexGrid) -> List[Dict[str, Any]]:
        """
        Serialize all hex cells with complete metadata.
        
        Args:
            hex_grid: HexGrid instance
            
        Returns:
            List of serialized hex cell data
        """
        hex_cells_data = []
        
        for cell in hex_grid:
            cell_data = {
                # Coordinates
                'q': cell.q,
                'r': cell.r,
                'center_x': cell.centroid[0],
                'center_y': cell.centroid[1],
                
                # Terrain properties
                'terrain_type': cell.terrain_type,
                'elevation_mean': cell.elevation_mean,
                'elevation_min': getattr(cell, 'elevation_min', 0.0),
                'elevation_max': getattr(cell, 'elevation_max', 0.0),
                'slope': cell.slope,
                
                # Features
                'has_roads': cell.has_roads,
                'has_buildings': cell.has_buildings,
                'has_water': cell.has_water,
                'land_use': cell.land_use,
                
                # Movement and combat
                'movement_cost': cell.movement_cost,
                'cover_value': cell.cover_value,
                'concealment': cell.concealment,
                'los_blocking_height': cell.los_blocking_height,
                
                # Polygon geometry (simplified)
                'polygon_bounds': list(cell.polygon.bounds) if cell.polygon else None
            }
            
            # Add units if present (currently not used in HexCell model)
            # if hasattr(cell, 'units') and cell.units:
            #     cell_data['units'] = [unit.id for unit in cell.units]
            
            hex_cells_data.append(cell_data)
        
        return hex_cells_data
    
    def _serialize_roads_data(self, roads_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Serialize road network data efficiently.
        
        Args:
            roads_data: Road network information
            
        Returns:
            Serialized roads data
        """
        if not roads_data:
            return {'roads': [], 'statistics': {}}
        
        serialized_roads = []
        total_length = 0.0
        road_types = {}
        
        for road in roads_data:
            road_info = {
                'name': road.get('name', 'Unnamed Road'),
                'road_type': road.get('fclass', 'unknown'),
                'reference': road.get('ref', ''),
                'oneway': road.get('oneway', False),
                'maxspeed': road.get('maxspeed', 0),
                'bridge': road.get('bridge', False),
                'tunnel': road.get('tunnel', False),
                'layer': road.get('layer', 0),
                'osm_id': road.get('osm_id', ''),
                'length': road.get('length', 0.0),
                'geometry_type': road.get('geometry_type', 'LineString')
            }
            
            # Geometry as simplified coordinates
            if 'geometry' in road and road['geometry'] is not None:
                if hasattr(road['geometry'], 'coords'):
                    road_info['coordinates'] = list(road['geometry'].coords)
                elif hasattr(road['geometry'], 'bounds'):
                    road_info['bounds'] = list(road['geometry'].bounds)
            
            serialized_roads.append(road_info)
            
            # Statistics
            total_length += road_info['length']
            road_type = road_info['road_type']
            road_types[road_type] = road_types.get(road_type, 0) + 1
        
        return {
            'roads': serialized_roads,
            'statistics': {
                'total_roads': len(serialized_roads),
                'total_length_km': total_length / 1000.0,
                'road_types': road_types
            }
        }
    
    def _serialize_waterways_data(self, waterways_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Serialize waterway network data efficiently.
        
        Args:
            waterways_data: Waterway network information
            
        Returns:
            Serialized waterways data
        """
        if not waterways_data:
            return {'waterways': [], 'statistics': {}}
        
        serialized_waterways = []
        total_length = 0.0
        waterway_types = {}
        
        for waterway in waterways_data:
            waterway_info = {
                'name': waterway.get('name', 'Unnamed Waterway'),
                'waterway_type': waterway.get('fclass', 'unknown'),
                'width': waterway.get('width', 0.0),
                'depth': waterway.get('depth', 0.0),
                'navigable': waterway.get('navigable', False),
                'length': waterway.get('length', 0.0),
                'geometry_type': waterway.get('geometry_type', 'LineString')
            }
            
            # Geometry as simplified coordinates
            if 'geometry' in waterway and waterway['geometry'] is not None:
                if hasattr(waterway['geometry'], 'coords'):
                    waterway_info['coordinates'] = list(waterway['geometry'].coords)
                elif hasattr(waterway['geometry'], 'bounds'):
                    waterway_info['bounds'] = list(waterway['geometry'].bounds)
            
            serialized_waterways.append(waterway_info)
            
            # Statistics
            total_length += waterway_info['length']
            waterway_type = waterway_info['waterway_type']
            waterway_types[waterway_type] = waterway_types.get(waterway_type, 0) + 1
        
        return {
            'waterways': serialized_waterways,
            'statistics': {
                'total_waterways': len(serialized_waterways),
                'total_length_km': total_length / 1000.0,
                'waterway_types': waterway_types
            }
        }
    
    def _generate_scenario_stats(self, 
                                hex_grid: HexGrid,
                                roads_data: List[Dict[str, Any]],
                                waterways_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate comprehensive scenario statistics.
        
        Args:
            hex_grid: HexGrid instance
            roads_data: Road network data
            waterways_data: Waterway network data
            
        Returns:
            Statistics dictionary
        """
        # Terrain statistics
        terrain_types = {}
        total_area = 0.0
        elevation_values = []
        
        for cell in hex_grid:
            terrain_types[cell.terrain_type] = terrain_types.get(cell.terrain_type, 0) + 1
            total_area += cell.area if hasattr(cell, 'area') else 1.0
            if cell.elevation_mean is not None:
                elevation_values.append(cell.elevation_mean)
        
        stats = {
            'terrain': {
                'total_hex_cells': len(hex_grid),
                'total_area_km2': total_area / 1_000_000,  # Convert to km²
                'terrain_distribution': terrain_types,
                'elevation_range': {
                    'min': min(elevation_values) if elevation_values else 0.0,
                    'max': max(elevation_values) if elevation_values else 0.0,
                    'mean': sum(elevation_values) / len(elevation_values) if elevation_values else 0.0
                }
            },
            'infrastructure': {
                'total_roads': len(roads_data),
                'total_waterways': len(waterways_data),
                'road_density_per_km2': len(roads_data) / (total_area / 1_000_000) if total_area > 0 else 0.0,
                'waterway_density_per_km2': len(waterways_data) / (total_area / 1_000_000) if total_area > 0 else 0.0
            }
        }
        
        return stats
    
    def regenerate_terrain_from_scenario(self, scenario_data: Dict[str, Any]) -> Optional[HexGrid]:
        """
        Regenerate hex grid and terrain from saved scenario data.
        
        Args:
            scenario_data: Loaded scenario data
            
        Returns:
            Reconstructed HexGrid or None if failed
        """
        try:
            print("Regenerating terrain from scenario data...")
            
            hex_cells_data = scenario_data.get('hex_cells', [])
            if not hex_cells_data:
                print("❌ No hex cell data found in scenario")
                return None
            
            # Get hex grid information from scenario
            hex_grid_info = scenario_data.get('hex_grid_info', {})
            hex_size = hex_grid_info.get('hex_size', 500)  # Default to 500 if not found
            bounds = hex_grid_info.get('bounds')
            center_offset = hex_grid_info.get('center_offset', (0.0, 0.0))
            
            # Create new hex grid with proper configuration
            hex_grid = HexGrid(hex_size=hex_size, bounds=bounds)
            hex_grid.center_offset = center_offset
            hex_grid.is_generated = True
            hex_grid.cells = {}
            
            # Reconstruct hex cells
            for cell_data in hex_cells_data:
                cell = HexCell(
                    q=cell_data['q'],
                    r=cell_data['r'],
                    centroid=(cell_data['center_x'], cell_data['center_y']),
                )
                
                # Restore terrain properties
                cell.terrain_type = cell_data.get('terrain_type', 'unknown')
                cell.elevation_mean = cell_data.get('elevation_mean', 0.0)
                cell.elevation_min = cell_data.get('elevation_min', 0.0)
                cell.elevation_max = cell_data.get('elevation_max', 0.0)
                cell.slope = cell_data.get('slope', 0.0)
                
                # Restore features
                cell.has_roads = cell_data.get('has_roads', False)
                cell.has_buildings = cell_data.get('has_buildings', False)
                cell.has_water = cell_data.get('has_water', False)
                cell.land_use = cell_data.get('land_use', '')
                
                # Restore movement and combat properties
                cell.movement_cost = cell_data.get('movement_cost', {'infantry': 1.0, 'vehicle': 1.0, 'aircraft': 1.0})
                cell.cover_value = cell_data.get('cover_value', 0.0)
                cell.concealment = cell_data.get('concealment', 0.0)
                cell.los_blocking_height = cell_data.get('los_blocking_height', 0.0)
                
                # Reconstruct proper hexagonal polygon directly at the cell's centroid
                # Create proper hexagonal polygon directly at the centroid
                import math
                from shapely.geometry import Polygon
                
                center_x, center_y = cell_data['center_x'], cell_data['center_y']
                
                # Calculate hex vertices around the centroid
                vertices = []
                for i in range(6):
                    angle = math.pi / 3 * i  # 60 degrees per vertex
                    vertex_x = center_x + hex_size * math.cos(angle)
                    vertex_y = center_y + hex_size * math.sin(angle)
                    vertices.append((vertex_x, vertex_y))
                
                cell.polygon = Polygon(vertices)
                
                hex_grid.cells[(cell.q, cell.r)] = cell
            
            print(f"Regenerated terrain with {len(hex_grid.cells)} hex cells")
            return hex_grid
            
        except Exception as e:
            print(f"❌ Error regenerating terrain: {e}")
            return None
    
    def get_scenario_info(self, scenario_path: str) -> Optional[Dict[str, Any]]:
        """
        Get scenario metadata without loading full scenario.
        
        Args:
            scenario_path: Path to scenario file
            
        Returns:
            Scenario metadata or None if failed
        """
        try:
            scenario_data = self.load_scenario(scenario_path)
            if not scenario_data:
                return None
            
            return {
                'version': scenario_data.get('version'),
                'timestamp': scenario_data.get('timestamp'),
                'metadata': scenario_data.get('metadata', {}),
                'statistics': scenario_data.get('statistics', {}),
                'terrain_summary': {
                    'hex_cells': len(scenario_data.get('hex_cells', [])),
                    'roads': len(scenario_data.get('roads', {}).get('roads', [])),
                    'waterways': len(scenario_data.get('waterways', {}).get('waterways', []))
                }
            }
            
        except Exception as e:
            print(f"❌ Error getting scenario info: {e}")
            return None