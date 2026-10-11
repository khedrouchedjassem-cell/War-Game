"""
Terrain analysis system for processing DEM and vector data to assign hex cell attributes.
"""
import numpy as np
import geopandas as gpd
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path
import math

# Use gpu_utils for robust GPU detection and xp selection
from utils.gpu_utils import detect_gpu, get_xp

# Detect GPU at import time
_gpu_available, _gpu_provider = detect_gpu()
GPU_AVAILABLE = _gpu_available
if GPU_AVAILABLE:
    print(f"GPU acceleration available via {_gpu_provider}")
else:
    print("GPU acceleration not available - falling back to CPU")

from core.hexgrid import HexGrid
from models.hexcell import HexCell
from utils.geo_utils import (
    load_dem, load_vector_layers, project_to_crs, get_common_crs,
    calculate_hex_statistics, intersect_hex_with_vectors, calculate_slope
)


class TerrainAnalyzer:
    """
    Analyzes terrain data (DEM + vector layers) and assigns attributes to hex cells.
    
    Handles data loading, projection, and statistical analysis for the wargame simulation.
    """
    
    def __init__(self, data_dir: str):
        """
        Initialize terrain analyzer.
        
        Args:
            data_dir: Directory containing DEM and Vector subdirectories
        """
        self.data_dir = Path(data_dir)
        self.dem_dir = self.data_dir / "DEM"
        self.vector_dir = self.data_dir / "Vector"
        
        # Loaded data
        self.elevation_data = None
        self.elevation_transform = None
        self.slope_data = None
        self.vector_layers = {}
        self.common_crs = None
        
        # Processing parameters
        self.terrain_classification = {
            'water': {'elevation_max': 0, 'slope_max': 5},
            'flat': {'elevation_max': float('inf'), 'slope_max': 5},
            'hills': {'elevation_max': float('inf'), 'slope_max': 15},
            'steep': {'elevation_max': float('inf'), 'slope_max': 30},
            'mountain': {'elevation_max': float('inf'), 'slope_max': float('inf')}
        }
        
        self.movement_costs = {
            # WATER BODIES
            'sea': {'infantry': float('inf'), 'vehicle': float('inf'), 'aircraft': 1.0},
            'shore': {'infantry': 1.2, 'vehicle': 1.5, 'aircraft': 1.0},
            'lake': {'infantry': float('inf'), 'vehicle': float('inf'), 'aircraft': 1.0},
            'river': {'infantry': 3.0, 'vehicle': float('inf'), 'aircraft': 1.0},
            'mountain_lake': {'infantry': float('inf'), 'vehicle': float('inf'), 'aircraft': 1.0},
            'wetland': {'infantry': 2.5, 'vehicle': float('inf'), 'aircraft': 1.0},
            
            # INFRASTRUCTURE
            'urban_dense': {'infantry': 1.3, 'vehicle': 1.8, 'aircraft': 1.0},
            'urban_hills': {'infantry': 1.5, 'vehicle': 2.2, 'aircraft': 1.0},
            'urban_mountain': {'infantry': 2.0, 'vehicle': 3.5, 'aircraft': 1.0},
            
            # FORESTS
            'forest_lowland': {'infantry': 1.8, 'vehicle': 3.5, 'aircraft': 1.0},
            'forest_hills': {'infantry': 2.2, 'vehicle': 4.0, 'aircraft': 1.0},
            'forest_mountain': {'infantry': 2.8, 'vehicle': float('inf'), 'aircraft': 1.0},
            
            # AGRICULTURE
            'farmland': {'infantry': 1.0, 'vehicle': 1.2, 'aircraft': 1.0},
            'pasture': {'infantry': 1.1, 'vehicle': 1.3, 'aircraft': 1.0},
            'rough_pasture': {'infantry': 1.4, 'vehicle': 2.0, 'aircraft': 1.0},
            
            # COASTAL
            'coastal_plain': {'infantry': 1.0, 'vehicle': 1.1, 'aircraft': 1.0},
            'coastal_cliff': {'infantry': 2.0, 'vehicle': float('inf'), 'aircraft': 1.0},
            
            # LOWLANDS
            'plains': {'infantry': 0.9, 'vehicle': 0.8, 'aircraft': 1.0},
            'rolling_hills': {'infantry': 1.2, 'vehicle': 1.4, 'aircraft': 1.0},
            'hills': {'infantry': 1.5, 'vehicle': 2.0, 'aircraft': 1.0},
            'steep_hills': {'infantry': 2.0, 'vehicle': 3.5, 'aircraft': 1.0},
            
            # HIGHLANDS
            'plateau': {'infantry': 1.3, 'vehicle': 1.6, 'aircraft': 1.0},
            'highlands': {'infantry': 1.8, 'vehicle': 2.5, 'aircraft': 1.0},
            'steep_slopes': {'infantry': 2.5, 'vehicle': 4.5, 'aircraft': 1.0},
            'cliffs': {'infantry': 4.0, 'vehicle': float('inf'), 'aircraft': 1.0},
            
            # MOUNTAINS
            'mountain_valley': {'infantry': 1.4, 'vehicle': 1.8, 'aircraft': 1.0},
            'mountain_slopes': {'infantry': 2.2, 'vehicle': 4.0, 'aircraft': 1.0},
            'mountain_steep': {'infantry': 3.5, 'vehicle': float('inf'), 'aircraft': 1.0},
            'alpine_meadow': {'infantry': 1.6, 'vehicle': 2.2, 'aircraft': 1.0},
            'high_mountain': {'infantry': 3.0, 'vehicle': float('inf'), 'aircraft': 1.2},
            'mountain_peak': {'infantry': 4.5, 'vehicle': float('inf'), 'aircraft': 1.5},
            
            # SPECIAL TERRAIN
            'desert': {'infantry': 1.3, 'vehicle': 1.1, 'aircraft': 1.0},
            
            # LEGACY SUPPORT
            'water': {'infantry': float('inf'), 'vehicle': float('inf'), 'aircraft': 1.0},
            'flat': {'infantry': 1.0, 'vehicle': 1.0, 'aircraft': 1.0},
            'hills': {'infantry': 1.5, 'vehicle': 2.0, 'aircraft': 1.0},
            'steep': {'infantry': 2.5, 'vehicle': 4.0, 'aircraft': 1.0},
            'mountain': {'infantry': 4.0, 'vehicle': float('inf'), 'aircraft': 1.0},
            'forest': {'infantry': 1.8, 'vehicle': 3.0, 'aircraft': 1.0},
            'urban': {'infantry': 1.2, 'vehicle': 1.5, 'aircraft': 1.0},
            'road': {'infantry': 0.8, 'vehicle': 0.5, 'aircraft': 1.0}
        }
        
        self.cover_values = {
            # WATER BODIES
            'sea': 0.0,  # No cover on open water
            'shore': 0.1,  # Minimal cover from beach structures
            'lake': 0.0,  # No cover on open water
            'river': 0.1,  # Minimal cover from riverbanks
            'mountain_lake': 0.0,  # No cover on water
            'wetland': 0.3,  # Some cover from reeds and vegetation
            
            # INFRASTRUCTURE
            'urban_dense': 0.8,  # High cover from buildings
            'urban_hills': 0.7,  # Good cover from elevated buildings
            'urban_mountain': 0.6,  # Some cover despite terrain challenges
            
            # FORESTS
            'forest_lowland': 0.9,  # Excellent cover from trees
            'forest_hills': 0.9,  # Excellent cover from trees
            'forest_mountain': 0.8,  # Good cover despite terrain
            
            # AGRICULTURE
            'farmland': 0.2,  # Minimal cover from crops
            'pasture': 0.1,  # Very little cover
            'rough_pasture': 0.3,  # Some cover from scrubland
            
            # COASTAL
            'coastal_plain': 0.1,  # Very little cover
            'coastal_cliff': 0.4,  # Some cover from cliff formations
            
            # LOWLANDS
            'plains': 0.0,  # No cover in open plains
            'rolling_hills': 0.2,  # Some cover from terrain undulation
            'hills': 0.4,  # Moderate cover from elevation changes
            'steep_hills': 0.6,  # Good cover from steep terrain
            
            # HIGHLANDS
            'plateau': 0.3,  # Some cover from elevated position
            'highlands': 0.5,  # Moderate cover from rough terrain
            'steep_slopes': 0.7,  # Good cover from steep terrain
            'cliffs': 0.9,  # Excellent cover from cliff faces
            
            # MOUNTAINS
            'mountain_valley': 0.4,  # Moderate cover from valley walls
            'mountain_slopes': 0.6,  # Good cover from terrain
            'mountain_steep': 0.8,  # Excellent cover from steep terrain
            'alpine_meadow': 0.3,  # Some cover from elevation
            'high_mountain': 0.7,  # Good cover from rocky terrain
            'mountain_peak': 0.5,  # Some cover despite exposure
            
            # SPECIAL TERRAIN
            'desert': 0.1,  # Very little cover
            
            # LEGACY SUPPORT
            'water': 0.0,
            'flat': 0.0,
            'hills': 0.4,
            'steep': 0.7,
            'mountain': 0.8,
            'forest': 0.9,
            'urban': 0.7,
            'road': 0.0
        }
        
        self.los_blocking = {
            # WATER BODIES
            'sea': 0.0,  # Clear line of sight over water
            'shore': 0.0,  # Generally clear
            'lake': 0.0,  # Clear line of sight over water
            'river': 0.0,  # Rivers don't block LOS
            'mountain_lake': 0.0,  # Clear over water
            'wetland': 0.2,  # Some vegetation obstruction
            
            # INFRASTRUCTURE
            'urban_dense': 0.9,  # Buildings heavily block LOS
            'urban_hills': 0.8,  # Buildings on hills block well
            'urban_mountain': 0.7,  # Mountain terrain reduces building density
            
            # FORESTS
            'forest_lowland': 0.8,  # Trees heavily block LOS
            'forest_hills': 0.8,  # Trees heavily block LOS
            'forest_mountain': 0.7,  # Some visibility through mountain forest
            
            # AGRICULTURE
            'farmland': 0.2,  # Crops provide some obstruction
            'pasture': 0.0,  # Clear fields
            'rough_pasture': 0.3,  # Scrubland provides some obstruction
            
            # COASTAL
            'coastal_plain': 0.0,  # Clear coastal areas
            'coastal_cliff': 0.0,  # Elevation change doesn't block horizontal LOS
            
            # LOWLANDS
            'plains': 0.0,  # Clear open terrain
            'rolling_hills': 0.1,  # Minimal obstruction from terrain undulation
            'hills': 0.2,  # Some obstruction from terrain features
            'steep_hills': 0.3,  # More obstruction from steep terrain
            
            # HIGHLANDS
            'plateau': 0.1,  # Minimal obstruction on flat elevated terrain
            'highlands': 0.2,  # Some obstruction from rough terrain
            'steep_slopes': 0.4,  # Terrain features block some sight lines
            'cliffs': 0.5,  # Cliff faces can block sight lines
            
            # MOUNTAINS
            'mountain_valley': 0.3,  # Valley walls provide some obstruction
            'mountain_slopes': 0.4,  # Sloped terrain blocks some sight lines
            'mountain_steep': 0.6,  # Steep terrain heavily obstructs
            'alpine_meadow': 0.1,  # Generally clear at high elevation
            'high_mountain': 0.5,  # Rocky terrain provides obstruction
            'mountain_peak': 0.2,  # Elevated position provides good visibility
            
            # SPECIAL TERRAIN
            'desert': 0.0,  # Clear desert terrain
            
            # LEGACY SUPPORT
            'water': 0.0,
            'flat': 0.0,
            'hills': 0.2,
            'steep': 0.4,
            'mountain': 0.6,
            'forest': 0.8,
            'urban': 0.8,
            'road': 0.0
        }
    
    def load_data(self) -> bool:
        """
        Load DEM and vector data from the data directory.
        
        Returns:
            True if data loaded successfully, False otherwise
        """
        try:
            # Load DEM
            dem_files = list(self.dem_dir.glob('*.tif'))
            if not dem_files:
                print(f"Warning: No DEM files found in {self.dem_dir}")
                return False
            
            dem_file = dem_files[0]  # Use first DEM file found
            print(f"Loading DEM from {dem_file}")
            self.elevation_data, self.elevation_transform, dem_crs = load_dem(str(dem_file))
            
            # Calculate slope
            self.slope_data = calculate_slope(self.elevation_data, self.elevation_transform)
            
            # Load vector layers
            print(f"Loading vector layers from {self.vector_dir}")
            self.vector_layers = load_vector_layers(str(self.vector_dir))
            
            # Determine common CRS
            self.common_crs = get_common_crs(dem_crs, self.vector_layers)
            print(f"Using common CRS: {self.common_crs}")
            
            # Project vector layers to common CRS
            for name, gdf in self.vector_layers.items():
                if gdf.crs is not None:
                    self.vector_layers[name] = project_to_crs(gdf, self.common_crs)
                    print(f"Projected {name} layer: {len(gdf)} features")
            
            return True
            
        except Exception as e:
            print(f"Error loading data: {str(e)}")
            return False
    
    def analyze_grid(self, hex_grid: HexGrid) -> None:
        """
        Analyze terrain for all cells in the hex grid with optional GPU acceleration.
        
        Args:
            hex_grid: HexGrid instance to analyze
        """
        if self.elevation_data is None:
            print("Warning: No elevation data loaded")
            return
        
        total_cells = len(hex_grid)
        print(f"Analyzing terrain for {total_cells} hex cells...")
        
        # Intelligent GPU usage with configuration override
        from utils.gpu_config import should_use_gpu, get_gpu_config
        
        gpu_config = get_gpu_config()
        use_gpu = should_use_gpu(total_cells)
        
        if use_gpu:
            try:
                print("ATTEMPTING GPU-ACCELERATED TERRAIN ANALYSIS...")
                print(f"GPU Device: {_gpu_provider}")
                print(f"Dataset: {total_cells} cells | Config: {gpu_config}")
                
                # Run GPU stress test if configured
                if gpu_config.get('gpu_stress_test', False):
                    from utils.gpu_config import run_gpu_stress_test
                    run_gpu_stress_test()
                
                self._analyze_grid_gpu(hex_grid)
                print("GPU TERRAIN ANALYSIS COMPLETED SUCCESSFULLY")
                return
            except Exception as e:
                print(f"GPU analysis failed: {e}")
                print("Falling back to CPU analysis...")
        else:
            print(f"Using CPU analysis - {gpu_config}")
        
        # CPU analysis
        self._analyze_grid_cpu(hex_grid)
    
    def _analyze_grid_gpu(self, hex_grid: HexGrid) -> None:
        """
        GPU-accelerated terrain analysis using CuPy with massive parallel processing.
        
        Args:
            hex_grid: HexGrid instance to analyze
        """
        # Use gpu_utils to obtain an array module (cupy if available)
        from utils.gpu_utils import get_xp, to_cpu
        import cupy as cp
        
        xp = get_xp(prefer_gpu=True)
        if not hasattr(xp, '__name__') or xp.__name__ != 'cupy':
            print("CuPy not available, falling back to CPU")
            return self._analyze_grid_cpu(hex_grid)

        total_cells = len(hex_grid)
        print(f"USING CUPY GPU ACCELERATION for {total_cells} cells")
        
        # Get GPU memory info safely
        try:
            device = cp.cuda.Device()
            mem_info = device.mem_info
            print(f"GPU Memory: {mem_info[1] - mem_info[0]} bytes free of {mem_info[1]} total")
        except Exception as e:
            print(f"GPU Memory info unavailable: {e}")
        
        # Convert hex_grid to list for indexing
        cells_list = list(hex_grid)
        
        # ==== MASSIVE GPU BATCH PROCESSING ====
        print("Preparing massive GPU batch processing...")
        
        # Prepare all hex bounds at once
        all_bounds = []
        all_polygons = []
        for cell in cells_list:
            bounds = self._polygon_to_pixel_bounds(cell.polygon)
            all_bounds.append(bounds)
            all_polygons.append(cell.polygon)
        
        # Transfer ALL data to GPU memory at once for maximum utilization
        print("TRANSFERRING MASSIVE DATA TO GPU...")
        try:
            elevation_gpu = cp.asarray(self.elevation_data)
            slope_gpu = cp.asarray(self.slope_data) if self.slope_data is not None else None
            
            print(f"GPU Elevation Array: {elevation_gpu.shape}, {elevation_gpu.dtype}")
            print(f"Successfully transferred elevation data to GPU")
            
            # ==== MEGA-BATCH GPU STATISTICS PROCESSING ====
            print("PROCESSING ELEVATION STATISTICS ON GPU...")
            elevation_results = self._gpu_mega_batch_statistics(all_bounds, elevation_gpu)
            
            slope_results = []
            if slope_gpu is not None:
                print("PROCESSING SLOPE STATISTICS ON GPU...")
                slope_results = self._gpu_mega_batch_statistics(all_bounds, slope_gpu)
            
            # ==== GPU VECTOR PROCESSING ====
            print("PROCESSING VECTOR INTERSECTIONS WITH GPU OPTIMIZATION...")
            vector_results = self._gpu_vector_batch_processing(all_polygons)
            
            # Apply all results
            print("APPLYING GPU RESULTS...")
            for i, cell in enumerate(cells_list):
                # Apply elevation statistics
                if i < len(elevation_results):
                    elev_stats = elevation_results[i]
                    cell.elevation_mean = elev_stats['mean']
                    cell.elevation_min = elev_stats['min']
                    cell.elevation_max = elev_stats['max']
                
                # Apply slope statistics
                if slope_results and i < len(slope_results):
                    cell.slope = slope_results[i]['mean']
                else:
                    cell.slope = 0.0
                
                # Apply vector results
                if i < len(vector_results):
                    cell.has_roads = vector_results[i]['has_roads']
                    cell.has_buildings = vector_results[i]['has_buildings']
                    cell.has_water = vector_results[i]['has_water']
                    cell.land_use = vector_results[i]['land_use']
                
                # Terrain classification and other calculations
                cell.terrain_type = self._classify_terrain(cell)
                cell.movement_cost = self._calculate_movement_cost(cell)
                cell.cover_value = self._calculate_cover(cell)
                cell.concealment = self._calculate_concealment(cell)
                cell.los_blocking_height = self._calculate_los_blocking_height(cell)
                
                # Progress reporting
                if (i + 1) % 50 == 0 or (i + 1) == total_cells:
                    print(f"GPU Processed {i + 1}/{total_cells} cells...")
            
            # Clear GPU memory
            del elevation_gpu
            if slope_gpu is not None:
                del slope_gpu
            cp.cuda.Stream.null.synchronize()
            
            print(f"GPU TERRAIN ANALYSIS COMPLETE for {total_cells} cells")
            print(f"GPU processing successful!")
            
        except Exception as gpu_error:
            print(f"GPU processing error: {gpu_error}")
            print("Falling back to CPU analysis...")
            return self._analyze_grid_cpu(hex_grid)
        
    def _gpu_mega_batch_statistics(self, all_bounds: List[Tuple[int, int, int, int]], 
                                 data_gpu) -> List[Dict[str, float]]:
        """
        Mega-batch GPU statistics processing for maximum GPU utilization.
        
        Args:
            all_bounds: List of all pixel bounds for hexes
            data_gpu: CuPy array containing raster data
            
        Returns:
            List of statistics dictionaries
        """
        import cupy as cp
        
        print(f"Processing {len(all_bounds)} hex statistics on GPU...")
        
        # Process in large batches to maximize GPU usage
        batch_size = min(100, len(all_bounds))  # Large batches for GPU efficiency
        all_results = []
        
        for batch_start in range(0, len(all_bounds), batch_size):
            batch_end = min(batch_start + batch_size, len(all_bounds))
            batch_bounds = all_bounds[batch_start:batch_end]
            
            # Prepare batch arrays on GPU
            batch_means = []
            batch_mins = []
            batch_maxs = []
            batch_stds = []
            
            for bounds in batch_bounds:
                min_row, max_row, min_col, max_col = bounds
                
                if min_col >= max_col or min_row >= max_row:
                    batch_means.append(0.0)
                    batch_mins.append(0.0)
                    batch_maxs.append(0.0)
                    batch_stds.append(0.0)
                    continue
                
                # Extract subset on GPU (this is where the real GPU work happens)
                subset = data_gpu[min_row:max_row, min_col:max_col]
                
                # GPU operations - remove NaN values
                valid_mask = ~cp.isnan(subset)
                valid_data = subset[valid_mask]
                
                if valid_data.size == 0:
                    batch_means.append(0.0)
                    batch_mins.append(0.0)
                    batch_maxs.append(0.0)
                    batch_stds.append(0.0)
                    continue
                
                # All statistics computed on GPU
                mean_val = float(cp.mean(valid_data))
                min_val = float(cp.min(valid_data))
                max_val = float(cp.max(valid_data))
                std_val = float(cp.std(valid_data))
                
                batch_means.append(mean_val)
                batch_mins.append(min_val)
                batch_maxs.append(max_val)
                batch_stds.append(std_val)
            
            # Convert batch results
            for i in range(len(batch_bounds)):
                result = {
                    'mean': batch_means[i],
                    'min': batch_mins[i], 
                    'max': batch_maxs[i],
                    'std': batch_stds[i]
                }
                all_results.append(result)
        
        return all_results
    
    def _gpu_vector_batch_processing(self, all_polygons) -> List[Dict[str, Any]]:
        """
        GPU-accelerated vector intersection processing.
        
        Args:
            all_polygons: List of all hex polygons
            
        Returns:
            List of vector intersection results
        """
        import cupy as cp
        from shapely.geometry import Polygon
        
        print(f"GPU Vector processing for {len(all_polygons)} polygons...")
        
        results = []
        
        # Process in large batches for GPU efficiency
        batch_size = 50
        for batch_start in range(0, len(all_polygons), batch_size):
            batch_end = min(batch_start + batch_size, len(all_polygons))
            batch_polygons = all_polygons[batch_start:batch_end]
            
            batch_results = []
            
            # Use GPU-accelerated spatial operations where possible
            for polygon in batch_polygons:
                # For now, use CPU vector operations but in optimized batches
                # In future, could use GPU spatial libraries like cuSpatial
                if self.vector_layers:
                    from utils.geo_utils import intersect_hex_with_vectors
                    vector_result = intersect_hex_with_vectors(polygon, self.vector_layers)
                else:
                    vector_result = {
                        'has_roads': False,
                        'has_buildings': False,
                        'has_water': False,
                        'land_use': ''
                    }
                batch_results.append(vector_result)
            
            results.extend(batch_results)
        
        return results
    
    def _analyze_grid_cpu(self, hex_grid: HexGrid) -> None:
        """
        CPU-based terrain analysis (original implementation).
        
        Args:
            hex_grid: HexGrid instance to analyze
        """
        # Convert to list for faster iteration
        cells_list = list(hex_grid)
        total_cells = len(cells_list)
        
        # Process in batches for better memory management and progress reporting
        batch_size = 500
        processed = 0
        
        for i in range(0, total_cells, batch_size):
            batch = cells_list[i:i + batch_size]
            
            # Process batch
            for cell in batch:
                self._analyze_cell(cell)
                processed += 1
            
            # Report progress
            print(f"Processed {processed}/{total_cells} cells...")
        
        print(f"CPU terrain analysis complete for {processed} cells")
    
    def _polygon_to_pixel_bounds(self, polygon) -> Tuple[int, int, int, int]:
        """
        Convert polygon to pixel bounds in the elevation raster.
        
        Args:
            polygon: Shapely polygon
            
        Returns:
            Tuple of (min_row, max_row, min_col, max_col)
        """
        minx, miny, maxx, maxy = polygon.bounds
        
        # Convert to pixel coordinates
        min_col, max_row = ~self.elevation_transform * (minx, miny)
        max_col, min_row = ~self.elevation_transform * (maxx, maxy)
        
        # Ensure integer indices and valid bounds
        min_col = max(0, int(min_col))
        max_col = min(self.elevation_data.shape[1], int(max_col) + 1)
        min_row = max(0, int(min_row))
        max_row = min(self.elevation_data.shape[0], int(max_row) + 1)
        
        return (min_row, max_row, min_col, max_col)
    
    def _gpu_batch_statistics(self, hex_bounds: List[Tuple[int, int, int, int]], 
                             data_gpu) -> List[Dict[str, float]]:
        """
        Calculate statistics for multiple hex cells on GPU.
        
        Args:
            hex_bounds: List of pixel bounds for each hex
            data_gpu: CuPy array containing raster data
            
        Returns:
            List of statistics dictionaries
        """
        # Use xp = cupy or numpy depending on availability
        from utils.gpu_utils import get_xp
        xp = get_xp(prefer_gpu=True)

        results = []

        for bounds in hex_bounds:
            min_row, max_row, min_col, max_col = bounds

            if min_col >= max_col or min_row >= max_row:
                results.append({'mean': 0.0, 'min': 0.0, 'max': 0.0, 'std': 0.0})
                continue

            # Extract subset on device
            subset = data_gpu[min_row:max_row, min_col:max_col]

            # Remove NaN values
            valid_mask = ~xp.isnan(subset)
            # Flatten selection
            valid_data = subset[valid_mask]

            # If xp is cupy, transfer small arrays to host for python-side length checks
            try:
                valid_len = int(valid_data.size)
            except Exception:
                # As a fallback, move to CPU
                valid_host = xp.asnumpy(valid_data) if hasattr(xp, 'asnumpy') else valid_data
                valid_len = valid_host.size

            if valid_len == 0:
                results.append({'mean': 0.0, 'min': 0.0, 'max': 0.0, 'std': 0.0})
                continue

            # Calculate statistics (use xp functions; convert to float)
            mean_v = float(xp.mean(valid_data))
            min_v = float(xp.min(valid_data))
            max_v = float(xp.max(valid_data))
            std_v = float(xp.std(valid_data))

            stats = {'mean': mean_v, 'min': min_v, 'max': max_v, 'std': std_v}
            results.append(stats)

        return results
    
    def _analyze_vector_intersections(self, cell) -> Dict[str, Any]:
        """
        Analyze vector intersections for a single cell (CPU-based).
        
        Args:
            cell: HexCell to analyze
            
        Returns:
            Dictionary with intersection results
        """
        from utils.geo_utils import intersect_hex_with_vectors
        
        if self.vector_layers:
            return intersect_hex_with_vectors(cell.polygon, self.vector_layers)
        else:
            return {
                'has_roads': False,
                'has_buildings': False,
                'has_water': False,
                'land_use': ''
            }
    
    def _analyze_cell(self, cell: HexCell) -> None:
        """
        Analyze terrain for a single hex cell.
        
        Args:
            cell: HexCell to analyze
        """
        # Get elevation statistics
        if self.elevation_data is not None:
            elev_stats = calculate_hex_statistics(
                cell.polygon, self.elevation_data, self.elevation_transform
            )
            cell.elevation_mean = elev_stats['mean']
            cell.elevation_min = elev_stats['min']
            cell.elevation_max = elev_stats['max']
            
            # Get slope statistics
            if self.slope_data is not None:
                slope_stats = calculate_hex_statistics(
                    cell.polygon, self.slope_data, self.elevation_transform
                )
                cell.slope = slope_stats['mean']
        
        # Analyze vector intersections
        if self.vector_layers:
            vector_results = intersect_hex_with_vectors(cell.polygon, self.vector_layers)
            
            cell.has_roads = vector_results['has_roads']
            cell.has_buildings = vector_results['has_buildings']
            cell.has_water = vector_results['has_water']
            cell.land_use = vector_results['land_use']
        
        # Classify terrain type
        cell.terrain_type = self._classify_terrain(cell)
        
        # Calculate movement costs
        cell.movement_cost = self._calculate_movement_cost(cell)
        
        # Calculate cover and concealment
        cell.cover_value = self._calculate_cover(cell)
        cell.concealment = self._calculate_concealment(cell)
        
        # Calculate LOS blocking height
        cell.los_blocking_height = self._calculate_los_blocking_height(cell)
    
    def _classify_terrain(self, cell: HexCell) -> str:
        """
        Terrain classification system based ONLY on elevation and slope.
        Ignores water bodies, buildings, roads, land use, and other features.
        
        Args:
            cell: HexCell to classify
            
        Returns:
            Terrain type string based purely on topography
        """
        elevation = cell.elevation_mean
        slope = cell.slope
        
        if elevation <= 0:
            return "sea"  # Below sea level is considered sea
        
        # PURE ELEVATION AND SLOPE BASED CLASSIFICATION
        # Coastal areas (near sea level)
        if elevation <= 5:
            if slope <= 2:
                return "coastal_plain"  # Flat coastal areas
            else:
                return "coastal_cliff"  # Steep coastal areas
        
        # Lowland areas
        elif elevation <= 100:
            if slope <= 3:
                return "plains"  # Flat plains
            elif slope <= 8:
                return "rolling_hills"  # Gentle hills
            elif slope <= 20:
                return "hills"  # Moderate hills
            else:
                return "steep_hills"  # Steep hills
        
        # Highland areas
        elif elevation <= 500:
            if slope <= 5:
                return "plateau"  # High plateaus
            elif slope <= 15:
                return "highlands"  # Highland terrain
            elif slope <= 30:
                return "steep_slopes"  # Steep mountain slopes
            else:
                return "cliffs"  # Cliff faces
        
        # Mountain areas
        elif elevation <= 1000:
            if slope <= 10:
                return "mountain_valley"  # Mountain valleys
            elif slope <= 25:
                return "mountain_slopes"  # Mountain slopes
            else:
                return "mountain_steep"  # Steep mountains
        
        # High mountains
        else:
            if slope <= 15:
                return "alpine_meadow"  # High alpine areas
            elif slope <= 35:
                return "high_mountain"  # High mountain terrain
            else:
                return "mountain_peak"  # Mountain peaks and ridges
    
    def _calculate_movement_cost(self, cell: HexCell) -> Dict[str, float]:
        """
        Calculate movement costs for different movement types.
        
        Args:
            cell: HexCell to calculate for
            
        Returns:
            Dictionary of movement costs by type
        """
        base_costs = self.movement_costs.get(cell.terrain_type, 
                                           self.movement_costs['flat']).copy()
        
        # Modify costs based on features
        if cell.has_roads:
            # Roads reduce movement cost
            road_costs = self.movement_costs['road']
            for move_type in base_costs:
                base_costs[move_type] = min(base_costs[move_type], road_costs[move_type])
        
        if cell.has_buildings:
            # Buildings increase movement cost for vehicles
            base_costs['vehicle'] *= 1.5
        
        # Steep slopes affect movement
        if cell.slope > 15:
            slope_multiplier = 1.0 + (cell.slope - 15) / 30  # Up to 2x cost at 45 degrees
            base_costs['infantry'] *= slope_multiplier
            base_costs['vehicle'] *= slope_multiplier * 1.5  # Vehicles more affected
        
        return base_costs
    
    def _calculate_cover(self, cell: HexCell) -> float:
        """
        Calculate cover value based on terrain features.
        
        Args:
            cell: HexCell to calculate for
            
        Returns:
            Cover value (0.0 to 1.0)
        """
        base_cover = self.cover_values.get(cell.terrain_type, 0.1)
        
        # Buildings provide excellent cover (use appropriate urban terrain types)
        if cell.has_buildings:
            if 'urban' in cell.terrain_type:
                # Cover already handled by terrain type
                pass  
            else:
                # Building in non-urban terrain - use highest urban cover
                base_cover = max(base_cover, 0.8)  # High cover from buildings
        
        # Forest provides good cover (use appropriate forest terrain types)
        if cell.land_use.lower() in ['forest', 'woodland', 'trees']:
            if 'forest' in cell.terrain_type:
                # Cover already handled by terrain type
                pass
            else:
                # Forest in non-forest terrain - use forest cover
                base_cover = max(base_cover, 0.9)  # Excellent cover from trees
        
        return min(1.0, base_cover)
    
    def _calculate_concealment(self, cell: HexCell) -> float:
        """
        Calculate concealment value based on terrain features.
        
        Args:
            cell: HexCell to calculate for
            
        Returns:
            Concealment value (0.0 to 1.0)
        """
        concealment = 0.0
        
        # Forest provides good concealment
        if cell.land_use.lower() in ['forest', 'woodland', 'trees']:
            concealment = max(concealment, 0.7)
        
        # Buildings provide moderate concealment
        if cell.has_buildings:
            concealment = max(concealment, 0.5)
        
        # Rough terrain provides some concealment
        if cell.terrain_type in ['hills', 'steep', 'mountain']:
            concealment = max(concealment, 0.3)
        
        return concealment
    
    def _calculate_los_blocking_height(self, cell: HexCell) -> float:
        """
        Calculate the height that blocks line of sight.
        
        Args:
            cell: HexCell to calculate for
            
        Returns:
            LOS blocking height in meters
        """
        base_height = cell.elevation_mean
        
        # Get terrain-specific LOS blocking factor
        terrain_blocking = self.los_blocking.get(cell.terrain_type, 0.0)
        
        # Base terrain blocking height
        blocking_height = terrain_blocking * 15.0  # Scale to realistic height
        
        # Add height for forests (more specific than terrain type)
        if 'forest' in cell.terrain_type:
            blocking_height = max(blocking_height, 15.0)  # Minimum tree height
        
        # Add height for urban areas (more specific than terrain type)
        if 'urban' in cell.terrain_type:
            if 'dense' in cell.terrain_type:
                blocking_height = max(blocking_height, 20.0)  # Tall buildings
            else:
                blocking_height = max(blocking_height, 10.0)  # Average buildings
        
        # Legacy support for old land use classifications
        if cell.land_use.lower() in ['forest', 'woodland', 'trees']:
            blocking_height = max(blocking_height, 15.0)
        
        if cell.has_buildings:
            blocking_height = max(blocking_height, 10.0)
        
        # Steep terrain creates micro-terrain that can block LOS
        if cell.slope > 20:
            blocking_height += cell.slope * 0.1
        
        return base_height + blocking_height
    
    def get_elevation_bounds(self) -> Tuple[float, float]:
        """Get elevation min/max bounds from DEM data."""
        if self.elevation_data is None:
            return 0.0, 0.0
        
        valid_elevations = self.elevation_data[~np.isnan(self.elevation_data)]
        if len(valid_elevations) == 0:
            return 0.0, 0.0
        
        return float(np.min(valid_elevations)), float(np.max(valid_elevations))
    
    def get_data_bounds(self) -> Optional[Tuple[float, float, float, float]]:
        """
        Get bounding box of all loaded data.
        
        Primary strategy: Use DEM bounds as the authoritative extent to ensure
        all hexes have elevation data and avoid "sea" areas.
        
        Returns:
            (minx, miny, maxx, maxy) or None if no data loaded
        """
        # Use DEM bounds as the primary extent to avoid areas without elevation data
        if self.elevation_data is not None and self.elevation_transform is not None:
            height, width = self.elevation_data.shape
            # Get corner coordinates
            corners = [
                (0, 0), (width, 0), (width, height), (0, height)
            ]
            
            x_coords = []
            y_coords = []
            
            for col, row in corners:
                x, y = self.elevation_transform * (col, row)
                x_coords.append(x)
                y_coords.append(y)
            
            dem_bounds = (min(x_coords), min(y_coords), max(x_coords), max(y_coords))
            print(f"DEM bounds: {dem_bounds}")
            
            # Check vector bounds for informational purposes
            vector_bounds_list = []
            for name, gdf in self.vector_layers.items():
                if not gdf.empty:
                    vector_bounds = gdf.total_bounds  # (minx, miny, maxx, maxy)
                    vector_bounds_list.append(vector_bounds)
                    print(f"Vector layer '{name}' bounds: {vector_bounds}")
            
            if vector_bounds_list:
                # Get overall vector bounds
                vector_minx = min(bounds[0] for bounds in vector_bounds_list)
                vector_miny = min(bounds[1] for bounds in vector_bounds_list)
                vector_maxx = max(bounds[2] for bounds in vector_bounds_list)
                vector_maxy = max(bounds[3] for bounds in vector_bounds_list)
                overall_vector_bounds = (vector_minx, vector_miny, vector_maxx, vector_maxy)
                print(f"Overall vector bounds: {overall_vector_bounds}")
                
                # Check if vector extends beyond DEM
                extends_beyond = (
                    vector_minx < dem_bounds[0] or vector_maxx > dem_bounds[2] or
                    vector_miny < dem_bounds[1] or vector_maxy > dem_bounds[3]
                )
                
                if extends_beyond:
                    print("Warning: Vector data extends beyond DEM coverage.")
                    print("Using DEM bounds to ensure all hexes have elevation data.")
                
                # Check if DEM extends beyond vector data
                vector_covers_dem = (
                    vector_minx <= dem_bounds[0] and vector_maxx >= dem_bounds[2] and
                    vector_miny <= dem_bounds[1] and vector_maxy >= dem_bounds[3]
                )
                
                if not vector_covers_dem:
                    print("Note: DEM extends beyond vector data coverage.")
                    print("Some hexes may have limited vector features.")
            
            # Always use DEM bounds as the primary extent to ensure proper alignment
            print(f"Using DEM bounds as grid extent: {dem_bounds}")
            return dem_bounds
        
        return None
    
    def generate_terrain_summary(self, hex_grid: HexGrid) -> Dict[str, Any]:
        """
        Generate a summary of terrain analysis results.
        
        Args:
            hex_grid: Analyzed hex grid
            
        Returns:
            Dictionary with terrain summary statistics
        """
        if not hex_grid.cells:
            return {}
        
        # Collect statistics
        terrain_counts = {}
        elevation_values = []
        slope_values = []
        cover_values = []
        
        feature_counts = {
            'roads': 0,
            'buildings': 0,
            'water': 0
        }
        
        for cell in hex_grid:
            # Terrain types
            terrain = cell.terrain_type
            terrain_counts[terrain] = terrain_counts.get(terrain, 0) + 1
            
            # Elevation and slope
            elevation_values.append(cell.elevation_mean)
            slope_values.append(cell.slope)
            cover_values.append(cell.cover_value)
            
            # Features
            if cell.has_roads:
                feature_counts['roads'] += 1
            if cell.has_buildings:
                feature_counts['buildings'] += 1
            if cell.has_water:
                feature_counts['water'] += 1
        
        # Calculate percentages
        total_cells = len(hex_grid)
        terrain_percentages = {
            terrain: (count / total_cells) * 100 
            for terrain, count in terrain_counts.items()
        }
        
        feature_percentages = {
            feature: (count / total_cells) * 100 
            for feature, count in feature_counts.items()
        }
        
        return {
            'total_cells': total_cells,
            'terrain_distribution': terrain_counts,
            'terrain_percentages': terrain_percentages,
            'feature_counts': feature_counts,
            'feature_percentages': feature_percentages,
            'elevation_stats': {
                'min': min(elevation_values) if elevation_values else 0,
                'max': max(elevation_values) if elevation_values else 0,
                'mean': sum(elevation_values) / len(elevation_values) if elevation_values else 0,
                'std': np.std(elevation_values) if elevation_values else 0
            },
            'slope_stats': {
                'min': min(slope_values) if slope_values else 0,
                'max': max(slope_values) if slope_values else 0,
                'mean': sum(slope_values) / len(slope_values) if slope_values else 0,
                'std': np.std(slope_values) if slope_values else 0
            },
            'cover_stats': {
                'min': min(cover_values) if cover_values else 0,
                'max': max(cover_values) if cover_values else 0,
                'mean': sum(cover_values) / len(cover_values) if cover_values else 0,
                'std': np.std(cover_values) if cover_values else 0
            }
        }
    
    def process_edge_aligned_waterways(self, hex_grid: HexGrid, waterways_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process waterway data to align them with hex cell edges.
        
        Args:
            hex_grid: HexGrid instance with generated cells
            waterways_data: Raw waterway data from vector files
            
        Returns:
            List of edge-aligned waterway segments
        """
        from shapely.geometry import LineString, shape
        from utils.geo_utils import align_waterway_to_hex_edges
        
        print("Processing edge-aligned waterways...")
        
        all_edge_segments = []
        processed_waterways = 0
        
        for waterway in waterways_data:
            try:
                # Extract geometry from waterway data
                geometry = None
                if isinstance(waterway, dict):
                    if 'geometry' in waterway:
                        if hasattr(waterway['geometry'], 'coords'):
                            geometry = waterway['geometry']
                        elif isinstance(waterway['geometry'], dict):
                            geometry = shape(waterway['geometry'])
                        elif hasattr(waterway['geometry'], '__geo_interface__'):
                            geometry = shape(waterway['geometry'].__geo_interface__)
                    elif hasattr(waterway, 'geometry'):
                        geometry = waterway.geometry
                else:
                    geometry = waterway.geometry if hasattr(waterway, 'geometry') else None
                
                if not geometry or not hasattr(geometry, 'coords'):
                    continue
                
                # Get waterway metadata
                waterway_name = "Unknown Waterway"
                waterway_type = "unknown"
                waterway_width = 0.0
                
                if isinstance(waterway, dict):
                    if 'properties' in waterway:
                        props = waterway['properties']
                        waterway_name = props.get('name', props.get('NAME', waterway_name))
                        waterway_type = props.get('fclass', props.get('type', props.get('TYPE', waterway_type)))
                        waterway_width = props.get('width', props.get('WIDTH', waterway_width))
                    else:
                        waterway_name = waterway.get('name', waterway_name)
                        waterway_type = waterway.get('fclass', waterway.get('type', waterway_type))
                        waterway_width = waterway.get('width', waterway_width)
                else:
                    waterway_name = getattr(waterway, 'name', waterway_name)
                    waterway_type = getattr(waterway, 'fclass', getattr(waterway, 'type', waterway_type))
                    waterway_width = getattr(waterway, 'width', waterway_width)
                
                # Convert to edge-aligned segments with connectivity
                edge_segments = align_waterway_to_hex_edges(geometry, hex_grid, hex_grid.hex_size)
                
                # Add metadata to each segment
                for segment in edge_segments:
                    segment.update({
                        'name': waterway_name,
                        'waterway_type': waterway_type,
                        'width': waterway_width,
                        'original_waterway_id': processed_waterways
                    })
                    
                    # Add to the hex cell's edge waterways
                    hex_cell = hex_grid.get_cell(segment['hex_q'], segment['hex_r'])
                    if hex_cell:
                        hex_cell.add_edge_waterway(segment['edge_index'], segment)
                
                all_edge_segments.extend(edge_segments)
                processed_waterways += 1
                
                # Debug connectivity for first few waterways
                if processed_waterways <= 3 and len(edge_segments) > 1:
                    print(f"  🔗 Waterway '{waterway_name}' connectivity check:")
                    print(f"     Generated {len(edge_segments)} connected segments")
                    for j, seg in enumerate(edge_segments[:3]):  # Show first 3 segments
                        print(f"     Segment {j}: Hex({seg['hex_q']},{seg['hex_r']}) Edge-{seg['edge_index']}")
                        print(f"       Start: {seg['start_point']}")
                        print(f"       End: {seg['end_point']}")
                
                if processed_waterways % 100 == 0:
                    print(f"  Processed {processed_waterways} waterways...")
                
            except Exception as e:
                print(f"  Failed to process waterway: {e}")
                continue
        
        print(f"Processed {processed_waterways} waterways into {len(all_edge_segments)} edge segments")
        
        # Validate connectivity
        print("🔗 Validating waterway connectivity...")
        connectivity_issues = 0
        
        # Group segments by waterway ID
        waterway_groups = {}
        for segment in all_edge_segments:
            wid = segment.get('original_waterway_id', 0)
            if wid not in waterway_groups:
                waterway_groups[wid] = []
            waterway_groups[wid].append(segment)
        
        for waterway_id, segments in waterway_groups.items():
            if len(segments) > 1:
                # Check if segments connect properly
                gaps_found = 0
                for i in range(len(segments) - 1):
                    current_end = segments[i]['end_point']
                    next_start = segments[i + 1]['start_point']
                    
                    # Calculate distance between end of current and start of next
                    distance = ((current_end[0] - next_start[0])**2 + (current_end[1] - next_start[1])**2)**0.5
                    
                    # If gap is larger than 1% of hex size, it's a connectivity issue
                    if distance > hex_grid.hex_size * 0.01:
                        gaps_found += 1
                
                if gaps_found > 0:
                    connectivity_issues += 1
                    if connectivity_issues <= 5:  # Only show first 5 issues
                        waterway_name = segments[0].get('name', 'Unknown')
                        print(f"   Waterway '{waterway_name}' has {gaps_found} connectivity gaps")
        
        if connectivity_issues == 0:
            print("   All waterways properly connected!")
        else:
            print(f"   Found connectivity issues in {connectivity_issues} waterways")
        
        # Update hex grid statistics
        waterway_hexes = 0
        for cell in hex_grid:
            if cell.edge_waterways:
                waterway_hexes += 1
        
        print(f"🗺️  Waterways affect {waterway_hexes} hex cells")
        
        return all_edge_segments