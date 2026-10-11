"""
Geographic utilities for handling GIS data, coordinate conversions, and spatial operations.
"""
import math
import numpy as np
import geopandas as gpd
import rasterio
from shapely.geometry import Polygon, Point
from shapely.affinity import translate
from typing import Tuple, List, Dict, Optional, Any
import pyproj
from pathlib import Path
from utils.config import get_config


def load_dem(dem_path: str) -> Tuple[np.ndarray, rasterio.transform.Affine, str]:
    """
    Load Digital Elevation Model from raster file.
    
    Args:
        dem_path: Path to DEM raster file
        
    Returns:
        Tuple of (elevation_array, transform, crs)
    """
    try:
        with rasterio.open(dem_path) as src:
            elevation = src.read(1)  # Read first band
            transform = src.transform
            crs = src.crs.to_string() if src.crs else None
            
            # Handle NoData values
            if src.nodata is not None:
                elevation = np.where(elevation == src.nodata, np.nan, elevation)
                
        return elevation, transform, crs
    except Exception as e:
        raise ValueError(f"Failed to load DEM from {dem_path}: {str(e)}")


def load_vector_layers(vector_dir: str) -> Dict[str, gpd.GeoDataFrame]:
    """
    Load all vector layers from a directory.
    
    Args:
        vector_dir: Directory containing shapefiles
        
    Returns:
        Dictionary mapping layer names to GeoDataFrames
    """
    vector_path = Path(vector_dir)
    layers = {}
    
    # Common layer patterns
    layer_patterns = {
        'buildings': ['building*', 'struktur*'],
        'roads': ['road*', 'street*', 'way*'],
        'water_ways': ['waterway*', 'river*', 'stream*'],
        'water_zones': ['water*', 'lake*', 'pond*'],
        'landuse': ['landuse*', 'land_use*', 'cover*']
    }
    
    # Find and load shapefiles
    shapefiles = list(vector_path.glob('*.shp'))
    
    for shapefile in shapefiles:
        layer_name = shapefile.stem.lower()
        
        try:
            gdf = gpd.read_file(shapefile)
            
            # Categorize the layer
            for category, patterns in layer_patterns.items():
                if any(pattern.replace('*', '') in layer_name for pattern in patterns):
                    layers[category] = gdf
                    break
            else:
                # If no pattern matches, use the filename
                layers[layer_name] = gdf
                
        except Exception as e:
            print(f"Warning: Failed to load {shapefile}: {str(e)}")
    
    return layers


def project_to_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    """
    Project GeoDataFrame to target coordinate reference system.
    
    Args:
        gdf: Input GeoDataFrame
        target_crs: Target CRS string
        
    Returns:
        Reprojected GeoDataFrame
    """
    if gdf.crs is None:
        raise ValueError("GeoDataFrame has no CRS defined")
    
    if gdf.crs.to_string() != target_crs:
        return gdf.to_crs(target_crs)
    
    return gdf


def axial_to_pixel(q: int, r: int, size: float, center: Tuple[float, float] = (0, 0)) -> Tuple[float, float]:
    """
    Convert axial hex coordinates to pixel coordinates.
    
    Args:
        q, r: Axial coordinates
        size: Hex size (distance from center to vertex)
        center: Center offset
        
    Returns:
        (x, y) pixel coordinates
    """
    x = size * (3/2 * q) + center[0]
    y = size * (math.sqrt(3)/2 * q + math.sqrt(3) * r) + center[1]
    return x, y


def pixel_to_axial(x: float, y: float, size: float, center: Tuple[float, float] = (0, 0)) -> Tuple[int, int]:
    """
    Convert pixel coordinates to axial hex coordinates.
    
    Args:
        x, y: Pixel coordinates
        size: Hex size (distance from center to vertex)
        center: Center offset
        
    Returns:
        (q, r) axial coordinates
    """
    # Adjust for center offset
    x -= center[0]
    y -= center[1]
    
    # Fix coordinate system orientation - negate Y to match expected hex layout
    y = -y
    
    # Convert to fractional axial coordinates
    q = (2/3 * x) / size
    r = (-1/3 * x + math.sqrt(3)/3 * y) / size
    
    # Round to nearest hex
    return cube_round(q, r, -q-r)


def cube_round(x: float, y: float, z: float) -> Tuple[int, int]:
    """
    Round fractional cube coordinates to nearest hex.
    
    Args:
        x, y, z: Fractional cube coordinates
        
    Returns:
        (q, r) axial coordinates
    """
    rx = round(x)
    ry = round(y)
    rz = round(z)
    
    x_diff = abs(rx - x)
    y_diff = abs(ry - y)
    z_diff = abs(rz - z)
    
    if x_diff > y_diff and x_diff > z_diff:
        rx = -ry - rz
    elif y_diff > z_diff:
        ry = -rx - rz
    else:
        rz = -rx - ry
    
    return rx, rz  # Return as (q, r)


def hex_to_polygon(q: int, r: int, size: float, center: Tuple[float, float] = (0, 0)) -> Polygon:
    """
    Create a hexagonal polygon from axial coordinates.
    
    Args:
        q, r: Axial coordinates
        size: Hex size (distance from center to vertex)
        center: Center offset
        
    Returns:
        Shapely Polygon representing the hex
    """
    # Get center point
    center_x, center_y = axial_to_pixel(q, r, size, center)
    
    # Calculate hex vertices
    vertices = []
    for i in range(6):
        angle = math.pi / 3 * i  # 60 degrees per vertex
        vertex_x = center_x + size * math.cos(angle)
        vertex_y = center_y + size * math.sin(angle)
        vertices.append((vertex_x, vertex_y))
    
    return Polygon(vertices)


def get_hex_edge_intersection(line_geometry, hex_cell, hex_size: float) -> List[int]:
    """
    Determine which edges of a hex cell a line geometry intersects.
    
    Args:
        line_geometry: Shapely LineString or similar geometry
        hex_cell: HexCell object
        hex_size: Size of the hex
        
    Returns:
        List of edge indices (0-5) that the line intersects
    """
    from shapely.geometry import LineString
    
    intersected_edges = []
    
    if not hex_cell.polygon or not hasattr(line_geometry, 'coords'):
        return intersected_edges
    
    # Get hex edge coordinates
    coords = list(hex_cell.polygon.exterior.coords)
    if len(coords) < 7:  # Should have 7 coordinates (6 vertices + closing)
        return intersected_edges
    
    # Check intersection with each edge
    for edge_index in range(6):
        start_point = coords[edge_index]
        end_point = coords[(edge_index + 1) % 6]
        edge_line = LineString([start_point, end_point])
        
        # Check if the line intersects this edge
        if line_geometry.intersects(edge_line):
            intersected_edges.append(edge_index)
    
    return intersected_edges


def align_waterway_to_hex_edges(waterway_geometry, hex_grid, hex_size: float) -> List[Dict[str, Any]]:
    """
    Convert a waterway geometry into edge-aligned segments that STRICTLY follow hex edges.
    
    CRITICAL CONSTRAINT: Rivers must follow hex cell edges - never cut through hex interiors.
    
    Args:
        waterway_geometry: Original waterway geometry
        hex_grid: HexGrid instance
        hex_size: Size of hexagons
        
    Returns:
        List of edge-aligned waterway segments that follow hex edges only
    """
    from shapely.geometry import LineString, Point
    
    edge_segments = []
    
    if not hasattr(waterway_geometry, 'coords'):
        return edge_segments
    
    # Process waterway by finding which hex edges it crosses
    coords = list(waterway_geometry.coords)
    
    for i in range(len(coords) - 1):
        start_point = coords[i]
        end_point = coords[i + 1]
        segment = LineString([start_point, end_point])
        
        # Find all hex cells this segment passes through
        intersected_hexes = _find_intersected_hexes(segment, hex_grid, hex_size)
        
        # For each hex, create edge segments that follow hex edges only
        hex_edge_segments = _create_hex_edge_segments(segment, intersected_hexes, hex_grid, hex_size)
        edge_segments.extend(hex_edge_segments)
    
    # Ensure all segments strictly follow hex edges
    edge_segments = _enforce_edge_following_constraint(edge_segments, hex_grid, hex_size)
    
    # Final connectivity pass to fix any gaps
    edge_segments = _fix_connectivity_gaps(edge_segments, hex_grid, hex_size)
    
    return edge_segments


def _fix_connectivity_gaps(segments: List[Dict[str, Any]], hex_grid, hex_size: float) -> List[Dict[str, Any]]:
    """
    Final pass to ensure perfect connectivity while maintaining edge-following constraint.
    """
    from shapely.geometry import LineString, Point
    
    if len(segments) <= 1:
        return segments
    
    fixed_segments = []
    tolerance = hex_size * 0.01
    
    for i, segment in enumerate(segments):
        current_segment = dict(segment)  # Create a copy
        
        # For segments after the first, adjust start point to connect with previous
        if i > 0 and fixed_segments:
            prev_end = fixed_segments[-1]['end_point']
            current_start = current_segment['start_point']
            
            gap_distance = ((prev_end[0] - current_start[0])**2 + 
                           (prev_end[1] - current_start[1])**2)**0.5
            
            # If there's a gap, adjust the current segment's start point
            if gap_distance > tolerance:
                # Project previous end point onto current segment's edge
                hex_cell = hex_grid.get_cell(current_segment['hex_q'], current_segment['hex_r'])
                if hex_cell:
                    edge_start, edge_end = hex_cell.get_edge_coordinates(current_segment['edge_index'])
                    edge_line = LineString([edge_start, edge_end])
                    
                    projected_point = edge_line.interpolate(edge_line.project(Point(prev_end)))
                    
                    # Update current segment's start point to connect
                    current_segment['start_point'] = (projected_point.x, projected_point.y)
                    current_segment['geometry'] = LineString([
                        current_segment['start_point'], 
                        current_segment['end_point']
                    ])
        
        # For segments before the last, adjust end point to connect with next
        if i < len(segments) - 1:
            next_start = segments[i + 1]['start_point']
            current_end = current_segment['end_point']
            
            gap_distance = ((current_end[0] - next_start[0])**2 + 
                           (current_end[1] - next_start[1])**2)**0.5
            
            # If there's a gap, adjust the current segment's end point
            if gap_distance > tolerance:
                # Project next start point onto current segment's edge
                hex_cell = hex_grid.get_cell(current_segment['hex_q'], current_segment['hex_r'])
                if hex_cell:
                    edge_start, edge_end = hex_cell.get_edge_coordinates(current_segment['edge_index'])
                    edge_line = LineString([edge_start, edge_end])
                    
                    projected_point = edge_line.interpolate(edge_line.project(Point(next_start)))
                    
                    # Update current segment's end point to connect
                    current_segment['end_point'] = (projected_point.x, projected_point.y)
                    current_segment['geometry'] = LineString([
                        current_segment['start_point'], 
                        current_segment['end_point']
                    ])
        
        fixed_segments.append(current_segment)
    
    return fixed_segments


def _find_intersected_hexes(waterway_segment, hex_grid, hex_size: float) -> List:
    """
    Find all hex cells that a waterway segment intersects, in order.
    """
    from shapely.geometry import Point
    
    intersected_hexes = []
    
    # Sample points along the segment to find all intersected hexes
    num_samples = max(20, int(waterway_segment.length / (hex_size * 0.1)))
    
    for i in range(num_samples + 1):
        t = i / num_samples if num_samples > 0 else 0
        sample_point = waterway_segment.interpolate(t, normalized=True)
        hex_cell = hex_grid.get_cell_at_position(sample_point.x, sample_point.y)
        
        if hex_cell and hex_cell not in intersected_hexes:
            intersected_hexes.append(hex_cell)
    
    return intersected_hexes


def _create_hex_edge_segments(waterway_segment, intersected_hexes, hex_grid, hex_size: float) -> List[Dict[str, Any]]:
    """
    Create waterway segments that follow hex edges only - never cut through hex interiors.
    """
    from shapely.geometry import LineString, Point
    
    edge_segments = []
    
    for hex_cell in intersected_hexes:
        # Find which edges of this hex the waterway should use
        hex_edge_segments = _determine_hex_edge_path(waterway_segment, hex_cell, hex_size)
        edge_segments.extend(hex_edge_segments)
    
    return edge_segments


def _determine_hex_edge_path(waterway_segment, hex_cell, hex_size: float) -> List[Dict[str, Any]]:
    """
    Determine which edges of a hex cell the waterway should follow.
    
    CONSTRAINT: Waterway must follow hex edges, never cut through hex interior.
    """
    from shapely.geometry import LineString, Point
    from shapely.ops import nearest_points
    
    edge_segments = []
    
    # Get hex center and all edge coordinates
    hex_center = Point(hex_cell.centroid[0], hex_cell.centroid[1])
    
    # Find entry and exit points on hex edges
    entry_edge_idx, entry_point = None, None
    exit_edge_idx, exit_point = None, None
    
    min_entry_dist = float('inf')
    min_exit_dist = float('inf')
    
    # Check intersection with each hex edge
    for edge_idx in range(6):
        edge_start, edge_end = hex_cell.get_edge_coordinates(edge_idx)
        edge_line = LineString([edge_start, edge_end])
        
        # Find intersection points
        try:
            intersection = waterway_segment.intersection(edge_line)
            if intersection.is_empty:
                continue
                
            if hasattr(intersection, 'coords'):
                # Single point intersection
                int_point = intersection
            elif hasattr(intersection, 'geoms'):
                # Multiple intersections - take first
                int_point = list(intersection.geoms)[0]
            else:
                continue
            
            # Check if this is entry or exit point
            waterway_start = Point(waterway_segment.coords[0])
            waterway_end = Point(waterway_segment.coords[-1])
            
            dist_to_start = waterway_start.distance(int_point)
            dist_to_end = waterway_end.distance(int_point)
            
            # Entry point (closer to waterway start)
            if dist_to_start < min_entry_dist:
                min_entry_dist = dist_to_start
                entry_edge_idx = edge_idx
                entry_point = (int_point.x, int_point.y)
            
            # Exit point (closer to waterway end)  
            if dist_to_end < min_exit_dist:
                min_exit_dist = dist_to_end
                exit_edge_idx = edge_idx
                exit_point = (int_point.x, int_point.y)
                
        except Exception:
            continue
    
    # If no clear entry/exit found, find closest edge points
    if entry_edge_idx is None or exit_edge_idx is None:
        waterway_start = waterway_segment.coords[0]
        waterway_end = waterway_segment.coords[-1]
        
        if entry_edge_idx is None:
            entry_edge_idx, entry_point = _find_closest_edge_point(waterway_start, hex_cell, hex_size)
        if exit_edge_idx is None:
            exit_edge_idx, exit_point = _find_closest_edge_point(waterway_end, hex_cell, hex_size)
    
    # Create segments that follow hex edges
    if entry_edge_idx == exit_edge_idx:
        # Same edge - single segment along the edge
        edge_segments.append({
            'hex_q': hex_cell.q,
            'hex_r': hex_cell.r,
            'edge_index': entry_edge_idx,
            'start_point': entry_point,
            'end_point': exit_point,
            'geometry': LineString([entry_point, exit_point])
        })
    else:
        # Different edges - follow hex perimeter
        perimeter_segments = _create_perimeter_path(hex_cell, entry_edge_idx, entry_point, 
                                                   exit_edge_idx, exit_point)
        edge_segments.extend(perimeter_segments)
    
    return edge_segments


def _create_perimeter_path(hex_cell, start_edge_idx: int, start_point: Tuple[float, float],
                          end_edge_idx: int, end_point: Tuple[float, float]) -> List[Dict[str, Any]]:
    """
    Create a path along hex perimeter from start edge to end edge.
    
    CRITICAL: This ensures waterways follow hex edges, never cut through interior.
    """
    from shapely.geometry import LineString
    
    perimeter_segments = []
    
    # Calculate shortest path around hex perimeter
    # Hex edges are numbered 0-5 clockwise from top
    clockwise_distance = (end_edge_idx - start_edge_idx) % 6
    counter_clockwise_distance = (start_edge_idx - end_edge_idx) % 6
    
    # Choose shorter path
    if clockwise_distance <= counter_clockwise_distance:
        # Go clockwise
        current_edge = start_edge_idx
        current_point = start_point
        
        while current_edge != end_edge_idx:
            next_edge = (current_edge + 1) % 6
            
            # Get edge coordinates
            edge_start, edge_end = hex_cell.get_edge_coordinates(current_edge)
            
            # Segment along current edge
            perimeter_segments.append({
                'hex_q': hex_cell.q,
                'hex_r': hex_cell.r,
                'edge_index': current_edge,
                'start_point': current_point,
                'end_point': edge_end,  # End at edge endpoint
                'geometry': LineString([current_point, edge_end])
            })
            
            current_point = edge_end  # Next segment starts where this ends
            current_edge = next_edge
        
        # Final segment to exit point
        perimeter_segments.append({
            'hex_q': hex_cell.q,
            'hex_r': hex_cell.r,
            'edge_index': end_edge_idx,
            'start_point': current_point,
            'end_point': end_point,
            'geometry': LineString([current_point, end_point])
        })
        
    else:
        # Go counter-clockwise
        current_edge = start_edge_idx
        current_point = start_point
        
        while current_edge != end_edge_idx:
            next_edge = (current_edge - 1) % 6
            
            # Get edge coordinates
            edge_start, edge_end = hex_cell.get_edge_coordinates(current_edge)
            
            # Segment along current edge (reversed direction)
            perimeter_segments.append({
                'hex_q': hex_cell.q,
                'hex_r': hex_cell.r,
                'edge_index': current_edge,
                'start_point': current_point,
                'end_point': edge_start,  # End at edge start point
                'geometry': LineString([current_point, edge_start])
            })
            
            current_point = edge_start
            current_edge = next_edge
        
        # Final segment to exit point
        perimeter_segments.append({
            'hex_q': hex_cell.q,
            'hex_r': hex_cell.r,
            'edge_index': end_edge_idx,
            'start_point': current_point,
            'end_point': end_point,
            'geometry': LineString([current_point, end_point])
        })
    
    return perimeter_segments


def _enforce_edge_following_constraint(segments: List[Dict[str, Any]], hex_grid, hex_size: float) -> List[Dict[str, Any]]:
    """
    Final validation to ensure ALL segments follow hex edges only.
    """
    validated_segments = []
    
    for segment in segments:
        # Validate that segment follows hex edge
        hex_cell = hex_grid.get_cell(segment['hex_q'], segment['hex_r'])
        if not hex_cell:
            continue
        
        edge_idx = segment['edge_index']
        edge_start, edge_end = hex_cell.get_edge_coordinates(edge_idx)
        
        # Ensure segment points lie on the hex edge
        start_point = segment['start_point']
        end_point = segment['end_point']
        
        # Project points onto the hex edge to ensure they're on the edge
        from shapely.geometry import LineString, Point
        edge_line = LineString([edge_start, edge_end])
        
        projected_start = edge_line.interpolate(edge_line.project(Point(start_point)))
        projected_end = edge_line.interpolate(edge_line.project(Point(end_point)))
        
        # Update segment to use projected points (ensuring it's on the edge)
        validated_segment = dict(segment)
        validated_segment['start_point'] = (projected_start.x, projected_start.y)
        validated_segment['end_point'] = (projected_end.x, projected_end.y)
        validated_segment['geometry'] = LineString([validated_segment['start_point'], 
                                                   validated_segment['end_point']])
        
        validated_segments.append(validated_segment)
    
    return validated_segments


def _trace_waterway_path(waterway_segment, hex_grid, hex_size: float) -> List[Dict[str, Any]]:
    """
    Trace a waterway segment through hex edges, ensuring connectivity.
    """
    from shapely.geometry import LineString, Point
    
    path_segments = []
    start_coord = waterway_segment.coords[0]
    end_coord = waterway_segment.coords[-1]
    
    # Find start and end hex cells
    start_hex = hex_grid.get_cell_at_position(start_coord[0], start_coord[1])
    end_hex = hex_grid.get_cell_at_position(end_coord[0], end_coord[1])
    
    if not start_hex or not end_hex:
        return path_segments
    
    # If same hex, create internal segment
    if start_hex == end_hex:
        # Find closest edges to start and end points
        start_edge_idx, start_edge_point = _find_closest_edge_point(start_coord, start_hex, hex_size)
        end_edge_idx, end_edge_point = _find_closest_edge_point(end_coord, end_hex, hex_size)
        
        if start_edge_idx == end_edge_idx:
            # Same edge - create single segment
            path_segments.append({
                'hex_q': start_hex.q,
                'hex_r': start_hex.r,
                'edge_index': start_edge_idx,
                'start_point': start_edge_point,
                'end_point': end_edge_point,
                'geometry': LineString([start_edge_point, end_edge_point])
            })
        else:
            # Different edges - create path through hex center
            center_x, center_y = start_hex.x, start_hex.y
            
            # Segment from start edge to center
            path_segments.append({
                'hex_q': start_hex.q,
                'hex_r': start_hex.r,
                'edge_index': start_edge_idx,
                'start_point': start_edge_point,
                'end_point': (center_x, center_y),
                'geometry': LineString([start_edge_point, (center_x, center_y)])
            })
            
            # Segment from center to end edge
            path_segments.append({
                'hex_q': start_hex.q,
                'hex_r': start_hex.r,
                'edge_index': end_edge_idx,
                'start_point': (center_x, center_y),
                'end_point': end_edge_point,
                'geometry': LineString([(center_x, center_y), end_edge_point])
            })
        
        return path_segments
    
    # Different hexes - sample points along the original waterway line
    # and create connected segments that follow the actual path
    num_samples = max(10, int(waterway_segment.length / (hex_size * 0.2)))
    sample_points = []
    
    for i in range(num_samples + 1):
        t = i / num_samples if num_samples > 0 else 0
        sample_point = waterway_segment.interpolate(t, normalized=True)
        sample_points.append((sample_point.x, sample_point.y))
    
    # Trace through each sample point and create connecting segments
    prev_position = None
    prev_hex = None
    
    for sample_coord in sample_points:
        current_hex = hex_grid.get_cell_at_position(sample_coord[0], sample_coord[1])
        
        if current_hex and prev_position is not None and prev_hex is not None:
            # Create segment from previous position to current sample point
            if prev_hex == current_hex:
                # Same hex - find appropriate edge
                edge_idx, edge_point = _find_closest_edge_point(sample_coord, current_hex, hex_size)
                path_segments.append({
                    'hex_q': current_hex.q,
                    'hex_r': current_hex.r,
                    'edge_index': edge_idx,
                    'start_point': prev_position,
                    'end_point': edge_point,
                    'geometry': LineString([prev_position, edge_point])
                })
                prev_position = edge_point
            else:
                # Different hex - create connecting segment via shared edge
                shared_edge_point = _find_shared_edge_point(prev_hex, current_hex, hex_size)
                
                if shared_edge_point:
                    # Segment to shared edge
                    prev_edge_idx, _ = _find_closest_edge_point(shared_edge_point, prev_hex, hex_size)
                    path_segments.append({
                        'hex_q': prev_hex.q,
                        'hex_r': prev_hex.r,
                        'edge_index': prev_edge_idx,
                        'start_point': prev_position,
                        'end_point': shared_edge_point,
                        'geometry': LineString([prev_position, shared_edge_point])
                    })
                    
                    # Segment from shared edge to current position
                    curr_edge_idx, curr_edge_point = _find_closest_edge_point(sample_coord, current_hex, hex_size)
                    path_segments.append({
                        'hex_q': current_hex.q,
                        'hex_r': current_hex.r,
                        'edge_index': curr_edge_idx,
                        'start_point': shared_edge_point,
                        'end_point': curr_edge_point,
                        'geometry': LineString([shared_edge_point, curr_edge_point])
                    })
                    
                    prev_position = curr_edge_point
                else:
                    # No shared edge - direct connection (for non-adjacent hexes)
                    curr_edge_idx, curr_edge_point = _find_closest_edge_point(sample_coord, current_hex, hex_size)
                    path_segments.append({
                        'hex_q': current_hex.q,
                        'hex_r': current_hex.r,
                        'edge_index': curr_edge_idx,
                        'start_point': prev_position,
                        'end_point': curr_edge_point,
                        'geometry': LineString([prev_position, curr_edge_point])
                    })
                    prev_position = curr_edge_point
        
        elif current_hex:
            # First valid hex
            edge_idx, edge_point = _find_closest_edge_point(sample_coord, current_hex, hex_size)
            prev_position = edge_point
        
        prev_hex = current_hex
    
    return path_segments


def _find_shared_edge_point(hex1, hex2, hex_size: float) -> Optional[Tuple[float, float]]:
    """
    Find a point on the shared edge between two adjacent hex cells.
    
    Returns:
        Coordinates of a point on the shared edge, or None if hexes are not adjacent
    """
    if not hex1 or not hex2:
        return None
    
    # Check if hexes are adjacent by comparing their coordinates
    dq = hex2.q - hex1.q
    dr = hex2.r - hex1.r
    
    # Adjacent hex differences should be one of: (1,0), (1,-1), (0,-1), (-1,0), (-1,1), (0,1)
    adjacent_deltas = [(1,0), (1,-1), (0,-1), (-1,0), (-1,1), (0,1)]
    
    if (dq, dr) not in adjacent_deltas:
        return None  # Not adjacent
    
    # Find the shared edge
    # The shared edge is the one that borders the direction to the adjacent hex
    edge_directions = [
        (0, -1),   # Edge 0: top
        (1, -1),   # Edge 1: top-right  
        (1, 0),    # Edge 2: bottom-right
        (0, 1),    # Edge 3: bottom
        (-1, 1),   # Edge 4: bottom-left
        (-1, 0)    # Edge 5: top-left
    ]
    
    # Find which edge of hex1 points toward hex2
    for edge_idx, (edge_dq, edge_dr) in enumerate(edge_directions):
        if (edge_dq, edge_dr) == (dq, dr):
            # This edge of hex1 is shared with hex2
            edge_start, edge_end = hex1.get_edge_coordinates(edge_idx)
            # Return midpoint of shared edge
            return ((edge_start[0] + edge_end[0]) / 2, (edge_start[1] + edge_end[1]) / 2)
    
    return None


def _find_closest_edge_point(point_coord, hex_cell, hex_size: float) -> Tuple[int, Tuple[float, float]]:
    """
    Find the closest point on hex edges to a given coordinate.
    
    Returns:
        Tuple of (edge_index, closest_point_coordinates)
    """
    from shapely.geometry import Point, LineString
    
    point = Point(point_coord)
    closest_edge_idx = 0
    closest_point = (0.0, 0.0)  # Default fallback
    min_distance = float('inf')
    
    for edge_idx in range(6):
        edge_start, edge_end = hex_cell.get_edge_coordinates(edge_idx)
        edge_line = LineString([edge_start, edge_end])
        
        # Find closest point on this edge
        edge_point = edge_line.interpolate(edge_line.project(point))
        distance = point.distance(edge_point)
        
        if distance < min_distance:
            min_distance = distance
            closest_edge_idx = edge_idx
            closest_point = (edge_point.x, edge_point.y)
    
    return closest_edge_idx, closest_point


def _get_adjacent_hex(hex_cell, edge_index: int, hex_grid):
    """
    Get the hex cell adjacent to the given edge.
    """
    # Hex edge directions (q_offset, r_offset for each edge 0-5)
    edge_directions = [
        (0, -1),   # Edge 0: top
        (1, -1),   # Edge 1: top-right
        (1, 0),    # Edge 2: bottom-right
        (0, 1),    # Edge 3: bottom
        (-1, 1),   # Edge 4: bottom-left
        (-1, 0)    # Edge 5: top-left
    ]
    
    dq, dr = edge_directions[edge_index]
    adjacent_q = hex_cell.q + dq
    adjacent_r = hex_cell.r + dr
    
    return hex_grid.get_cell(adjacent_q, adjacent_r)


def _connect_waterway_segments(segments: List[Dict[str, Any]], hex_grid, hex_size: float, 
                             connection_tolerance: Optional[float] = None) -> List[Dict[str, Any]]:
    """
    Post-process waterway segments to ensure proper connectivity.
    """
    if not segments:
        return segments
    
    if connection_tolerance is None:
        connection_tolerance = hex_size * 0.01  # 1% of hex size
    
    connected_segments = []
    
    # Group segments by waterway ID if available
    segment_groups = {}
    for i, segment in enumerate(segments):
        waterway_id = segment.get('original_waterway_id', 0)
        if waterway_id not in segment_groups:
            segment_groups[waterway_id] = []
        segment_groups[waterway_id].append((i, segment))
    
    # Process each waterway separately
    for waterway_id, group_segments in segment_groups.items():
        if len(group_segments) <= 1:
            connected_segments.extend([seg[1] for seg in group_segments])
            continue
        
        # Sort segments to form a connected path
        sorted_segments = _sort_segments_for_connectivity([seg[1] for seg in group_segments], connection_tolerance)
        connected_segments.extend(sorted_segments)
    
    return connected_segments


def _sort_segments_for_connectivity(segments: List[Dict[str, Any]], tolerance: float) -> List[Dict[str, Any]]:
    """
    Sort segments to form a connected waterway path.
    """
    if len(segments) <= 1:
        return segments
    
    from shapely.geometry import Point
    
    # Start with first segment
    ordered_segments = [segments[0]]
    remaining_segments = segments[1:]
    
    while remaining_segments:
        last_segment = ordered_segments[-1]
        last_end_point = Point(last_segment['end_point'])
        
        # Find the segment that starts closest to where we ended
        best_next_idx = None
        best_distance = float('inf')
        best_reversed = False
        
        for i, segment in enumerate(remaining_segments):
            start_point = Point(segment['start_point'])
            end_point = Point(segment['end_point'])
            
            # Check distance from last end to this start
            dist_normal = last_end_point.distance(start_point)
            # Check distance from last end to this end (reversed)
            dist_reversed = last_end_point.distance(end_point)
            
            if dist_normal < best_distance:
                best_distance = dist_normal
                best_next_idx = i
                best_reversed = False
            
            if dist_reversed < best_distance:
                best_distance = dist_reversed
                best_next_idx = i
                best_reversed = True
        
        if best_next_idx is not None:
            next_segment = remaining_segments.pop(best_next_idx)
            
            # Reverse segment if needed
            if best_reversed:
                next_segment = dict(next_segment)
                next_segment['start_point'], next_segment['end_point'] = \
                    next_segment['end_point'], next_segment['start_point']
                # Update geometry
                from shapely.geometry import LineString
                next_segment['geometry'] = LineString([next_segment['start_point'], next_segment['end_point']])
            
            ordered_segments.append(next_segment)
        else:
            # No connecting segment found, add remaining segments as-is
            ordered_segments.extend(remaining_segments)
            break
    
    return ordered_segments


def calculate_slope(elevation: np.ndarray, transform: rasterio.transform.Affine, 
                   window: Tuple[int, int, int, int] = None) -> np.ndarray:
    """
    Calculate slope from elevation data.
    
    Args:
        elevation: 2D numpy array of elevation values
        transform: Rasterio transform for pixel to coordinate conversion
        window: Optional window (minx, miny, maxx, maxy) to calculate slope for
        
    Returns:
        2D numpy array of slope values in degrees
    """
    if window:
        minx, miny, maxx, maxy = window
        elevation = elevation[miny:maxy, minx:maxx]
    
    # Calculate gradients
    grad_y, grad_x = np.gradient(elevation)
    
    # Convert pixel gradients to real-world units
    pixel_size_x = abs(transform[0])
    pixel_size_y = abs(transform[4])
    
    grad_x = grad_x / pixel_size_x
    grad_y = grad_y / pixel_size_y
    
    # Calculate slope in radians, then convert to degrees
    slope_rad = np.arctan(np.sqrt(grad_x**2 + grad_y**2))
    slope_deg = np.degrees(slope_rad)
    
    return slope_deg


def sample_raster_at_points(raster_array: np.ndarray, 
                           transform: rasterio.transform.Affine,
                           points: List[Tuple[float, float]]) -> List[float]:
    """
    Sample raster values at given point coordinates.
    
    Args:
        raster_array: 2D numpy array of raster data
        transform: Rasterio transform for coordinate conversion
        points: List of (x, y) coordinates to sample
        
    Returns:
        List of sampled values
    """
    values = []
    
    for x, y in points:
        # Convert world coordinates to pixel indices
        col, row = ~transform * (x, y)
        col, row = int(col), int(row)
        
        # Check bounds
        if 0 <= row < raster_array.shape[0] and 0 <= col < raster_array.shape[1]:
            value = raster_array[row, col]
            # Handle NaN values
            if np.isnan(value):
                values.append(0.0)
            else:
                values.append(float(value))
        else:
            values.append(0.0)  # Default value for out-of-bounds
    
    return values


def calculate_hex_statistics(hex_polygon: Polygon, 
                           elevation: np.ndarray,
                           transform: rasterio.transform.Affine) -> Dict[str, float]:
    """
    Calculate elevation statistics for a hexagonal cell.
    
    Args:
        hex_polygon: Shapely polygon representing the hex
        elevation: 2D numpy array of elevation data
        transform: Rasterio transform
        
    Returns:
        Dictionary with elevation statistics
    """
    # Get bounding box of hex
    minx, miny, maxx, maxy = hex_polygon.bounds
    
    # Convert to pixel coordinates
    min_col, max_row = ~transform * (minx, miny)
    max_col, min_row = ~transform * (maxx, maxy)
    
    # Ensure integer indices and valid bounds
    min_col = max(0, int(min_col))
    max_col = min(elevation.shape[1], int(max_col) + 1)
    min_row = max(0, int(min_row))
    max_row = min(elevation.shape[0], int(max_row) + 1)
    
    if min_col >= max_col or min_row >= max_row:
        return {'mean': 0.0, 'min': 0.0, 'max': 0.0, 'std': 0.0}
    
    # Extract elevation values within bounding box
    elevation_subset = elevation[min_row:max_row, min_col:max_col]
    
    # Remove NaN values
    valid_elevations = elevation_subset[~np.isnan(elevation_subset)]
    
    if len(valid_elevations) == 0:
        return {'mean': 0.0, 'min': 0.0, 'max': 0.0, 'std': 0.0}
    
    return {
        'mean': float(np.mean(valid_elevations)),
        'min': float(np.min(valid_elevations)),
        'max': float(np.max(valid_elevations)),
        'std': float(np.std(valid_elevations))
    }


def intersect_hex_with_vectors(hex_polygon: Polygon, 
                              vector_layers: Dict[str, gpd.GeoDataFrame]) -> Dict[str, Any]:
    """
    Check intersection of hex with vector layers and extract attributes.
    
    Args:
        hex_polygon: Shapely polygon representing the hex
        vector_layers: Dictionary of vector layer GeoDataFrames
        
    Returns:
        Dictionary with intersection results
    """
    results = {
        'has_roads': False,
        'has_buildings': False,
        'has_water': False,
        'land_use': 'unknown',
        'terrain_features': []
    }
    
    for layer_name, gdf in vector_layers.items():
        if gdf.empty:
            continue
        
        # Check for intersections
        intersections = gdf[gdf.geometry.intersects(hex_polygon)]
        
        if not intersections.empty:
            if 'road' in layer_name.lower() or 'street' in layer_name.lower():
                results['has_roads'] = True
            elif 'building' in layer_name.lower():
                results['has_buildings'] = True
            elif 'water' in layer_name.lower():
                results['has_water'] = True
            elif 'landuse' in layer_name.lower() or 'land_use' in layer_name.lower():
                # Get most common land use type
                if 'type' in intersections.columns:
                    land_use_types = intersections['type'].value_counts()
                    if not land_use_types.empty:
                        results['land_use'] = str(land_use_types.index[0])
                elif 'landuse' in intersections.columns:
                    land_use_types = intersections['landuse'].value_counts()
                    if not land_use_types.empty:
                        results['land_use'] = str(land_use_types.index[0])
            
            # Store feature information
            for _, feature in intersections.iterrows():
                feature_info = {
                    'layer': layer_name,
                    'geometry_type': str(feature.geometry.geom_type),
                    'attributes': {}
                }
                
                # Extract relevant attributes
                for col in feature.index:
                    if col != 'geometry' and feature[col] is not None:
                        feature_info['attributes'][col] = str(feature[col])
                
                results['terrain_features'].append(feature_info)
    
    return results


def create_hex_grid(bounds: Tuple[float, float, float, float], 
                   hex_size: Optional[float] = None) -> List[Tuple[int, int, Tuple[float, float], Polygon]]:
    """
    Create a hexagonal grid covering the given bounds.
    
    Args:
        bounds: (minx, miny, maxx, maxy) bounding box
        hex_size: Size of hexagons (distance from center to vertex). If None, uses config.
        
    Returns:
        List of (q, r, centroid, polygon) tuples
    """
    # Use config for hex_size if not provided
    if hex_size is None:
        config = get_config()
        hex_size = config.simulation.hex_size
    minx, miny, maxx, maxy = bounds
    
    # Calculate hex spacing
    hex_width = hex_size * 2.0
    hex_height = hex_size * math.sqrt(3)
    
    # Calculate grid dimensions
    cols = int((maxx - minx) / (hex_width * 0.75)) + 2
    rows = int((maxy - miny) / hex_height) + 2
    
    hexes = []
    
    for row in range(-rows//2, rows//2 + 1):
        for col in range(-cols//2, cols//2 + 1):
            # Convert to axial coordinates
            q = col
            r = row - col//2
            
            # Calculate pixel position
            x, y = axial_to_pixel(q, r, hex_size, (minx + (maxx-minx)/2, miny + (maxy-miny)/2))
            
            # Check if hex center is within bounds (with some padding)
            if minx - hex_size <= x <= maxx + hex_size and miny - hex_size <= y <= maxy + hex_size:
                centroid = (x, y)
                polygon = hex_to_polygon(q, r, hex_size, (minx + (maxx-minx)/2, miny + (maxy-miny)/2))
                hexes.append((q, r, centroid, polygon))
    
    return hexes


def get_common_crs(dem_crs: str, vector_layers: Dict[str, gpd.GeoDataFrame]) -> str:
    """
    Determine a common CRS for all data layers.
    
    Args:
        dem_crs: CRS of the DEM
        vector_layers: Dictionary of vector layers
        
    Returns:
        Common CRS string
    """
    # Start with DEM CRS if available
    if dem_crs:
        return dem_crs
    
    # Look for CRS in vector layers
    for name, gdf in vector_layers.items():
        if gdf.crs is not None:
            return gdf.crs.to_string()
    
    # Default to a reasonable UTM zone or web mercator
    return "EPSG:3857"  # Web Mercator


def calculate_distance(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
    """
    Calculate Euclidean distance between two points.
    
    Args:
        point1, point2: (x, y) coordinate tuples
        
    Returns:
        Distance in map units
    """
    return math.sqrt((point2[0] - point1[0])**2 + (point2[1] - point1[1])**2)


def calculate_bearing(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
    """
    Calculate bearing from point1 to point2 in degrees.
    
    Args:
        point1, point2: (x, y) coordinate tuples
        
    Returns:
        Bearing in degrees (0 = North, 90 = East)
    """
    dx = point2[0] - point1[0]
    dy = point2[1] - point1[1]
    
    bearing = math.degrees(math.atan2(dx, dy))
    return (bearing + 360) % 360  # Normalize to 0-360