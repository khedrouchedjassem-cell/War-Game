"""
Waterway Rules Validation Module

This module ensures strict enforcement of the waterway rules:
1. All waterway segments must follow hex cell edges only
2. Waterway segments of the same waterway must be connected end-to-end
3. No waterway segment may cut through hex cell interiors

Critical Rules Enforcement:
- RULE 1: Edge Following - Every waterway segment must lie exactly on a hex edge
- RULE 2: Connectivity - Segments within the same waterway must form continuous paths
- RULE 3: No Interior Crossing - Waterways cannot pass through hex cell centers
"""

import logging
from typing import List, Dict, Any, Tuple, Set
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points
import numpy as np

# Configure logging for validation
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WaterwayValidator:
    """Validates waterway segments against strict hex edge following rules."""
    
    def __init__(self, hex_grid, tolerance: float = 1e-6):
        """
        Initialize validator.
        
        Args:
            hex_grid: HexGrid instance for validation
            tolerance: Geometric tolerance for edge validation
        """
        self.hex_grid = hex_grid
        self.tolerance = tolerance
        self.validation_errors = []
    
    def validate_all_waterways(self, waterway_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Comprehensive validation of all waterway segments.
        
        Args:
            waterway_segments: List of waterway segment dictionaries
            
        Returns:
            Validation results with errors and statistics
        """
        logger.info(f"Starting comprehensive validation of {len(waterway_segments)} waterway segments")
        
        # Group segments by waterway name
        waterway_groups = self._group_segments_by_waterway(waterway_segments)
        
        validation_results = {
            'total_segments': len(waterway_segments),
            'total_waterways': len(waterway_groups),
            'edge_following_violations': [],
            'connectivity_violations': [],
            'interior_crossing_violations': [],
            'valid_segments': 0,
            'invalid_segments': 0,
            'validation_passed': True
        }
        
        # RULE 1: Validate edge following for all segments
        logger.info("RULE 1: Validating edge following constraint...")
        edge_violations = self._validate_edge_following(waterway_segments)
        validation_results['edge_following_violations'] = edge_violations
        
        # RULE 2: Validate connectivity within each waterway
        logger.info("RULE 2: Validating waterway connectivity...")
        connectivity_violations = self._validate_waterway_connectivity(waterway_groups)
        validation_results['connectivity_violations'] = connectivity_violations
        
        # RULE 3: Validate no interior crossing
        logger.info("RULE 3: Validating no interior crossing...")
        interior_violations = self._validate_no_interior_crossing(waterway_segments)
        validation_results['interior_crossing_violations'] = interior_violations
        
        # Calculate summary statistics
        total_violations = len(edge_violations) + len(connectivity_violations) + len(interior_violations)
        validation_results['valid_segments'] = len(waterway_segments) - total_violations
        validation_results['invalid_segments'] = total_violations
        validation_results['validation_passed'] = total_violations == 0
        
        # Log results
        if validation_results['validation_passed']:
            logger.info("VALIDATION PASSED: All waterway rules are correctly implemented")
        else:
            logger.error(f"VALIDATION FAILED: {total_violations} rule violations found")
            logger.error(f"  Edge following violations: {len(edge_violations)}")
            logger.error(f"  Connectivity violations: {len(connectivity_violations)}")
            logger.error(f"  Interior crossing violations: {len(interior_violations)}")
        
        return validation_results
    
    def _group_segments_by_waterway(self, segments: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group segments by waterway name."""
        groups = {}
        for segment in segments:
            name = segment.get('name', 'Unnamed')
            if name not in groups:
                groups[name] = []
            groups[name].append(segment)
        return groups
    
    def _validate_edge_following(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        RULE 1: Validate that all segments follow hex edges exactly.
        
        Returns:
            List of violation records
        """
        violations = []
        
        for i, segment in enumerate(segments):
            try:
                # Get hex cell
                hex_q = segment.get('hex_q')
                hex_r = segment.get('hex_r')
                edge_index = segment.get('edge_index')
                
                if hex_q is None or hex_r is None or edge_index is None:
                    violations.append({
                        'segment_index': i,
                        'violation_type': 'missing_hex_coordinates',
                        'description': 'Segment missing hex coordinates or edge index',
                        'segment': segment
                    })
                    continue
                
                hex_cell = self.hex_grid.get_cell(hex_q, hex_r)
                if not hex_cell:
                    violations.append({
                        'segment_index': i,
                        'violation_type': 'invalid_hex_cell',
                        'description': f'Invalid hex cell coordinates: q={hex_q}, r={hex_r}',
                        'segment': segment
                    })
                    continue
                
                # Get expected edge coordinates
                edge_start, edge_end = hex_cell.get_edge_coordinates(edge_index)
                edge_line = LineString([edge_start, edge_end])
                
                # Get segment coordinates
                start_point = segment.get('start_point')
                end_point = segment.get('end_point')
                
                if not start_point or not end_point:
                    violations.append({
                        'segment_index': i,
                        'violation_type': 'missing_coordinates',
                        'description': 'Segment missing start or end coordinates',
                        'segment': segment
                    })
                    continue
                
                # Validate that segment points lie on the hex edge
                start_dist = edge_line.distance(Point(start_point))
                end_dist = edge_line.distance(Point(end_point))
                
                if start_dist > self.tolerance:
                    violations.append({
                        'segment_index': i,
                        'violation_type': 'start_point_off_edge',
                        'description': f'Start point {start_point} is {start_dist:.6f} units from edge {edge_index}',
                        'distance': start_dist,
                        'segment': segment
                    })
                
                if end_dist > self.tolerance:
                    violations.append({
                        'segment_index': i,
                        'violation_type': 'end_point_off_edge',
                        'description': f'End point {end_point} is {end_dist:.6f} units from edge {edge_index}',
                        'distance': end_dist,
                        'segment': segment
                    })
                
            except Exception as e:
                violations.append({
                    'segment_index': i,
                    'violation_type': 'validation_error',
                    'description': f'Error validating segment: {str(e)}',
                    'segment': segment
                })
        
        return violations
    
    def _validate_waterway_connectivity(self, waterway_groups: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        RULE 2: Validate that segments within each waterway are connected.
        
        Returns:
            List of connectivity violation records
        """
        violations = []
        
        for waterway_name, segments in waterway_groups.items():
            if len(segments) <= 1:
                continue  # Single segment or empty - no connectivity to check
            
            # Build endpoint graph
            endpoints = {}  # endpoint -> list of segment indices
            
            for i, segment in enumerate(segments):
                start_point = segment.get('start_point')
                end_point = segment.get('end_point')
                
                if not start_point or not end_point:
                    continue
                
                # Round coordinates for robust matching
                start_key = (round(start_point[0], 6), round(start_point[1], 6))
                end_key = (round(end_point[0], 6), round(end_point[1], 6))
                
                if start_key not in endpoints:
                    endpoints[start_key] = []
                if end_key not in endpoints:
                    endpoints[end_key] = []
                
                endpoints[start_key].append(i)
                endpoints[end_key].append(i)
            
            # Check connectivity using graph traversal
            if len(segments) > 1:
                connected_components = self._find_connected_components(segments, endpoints)
                
                if len(connected_components) > 1:
                    violations.append({
                        'waterway_name': waterway_name,
                        'violation_type': 'disconnected_segments',
                        'description': f'Waterway "{waterway_name}" has {len(connected_components)} disconnected components',
                        'components': connected_components,
                        'segment_count': len(segments)
                    })
        
        return violations
    
    def _validate_no_interior_crossing(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        RULE 3: Validate that no segment crosses through hex cell interior.
        
        Returns:
            List of interior crossing violation records
        """
        violations = []
        
        for i, segment in enumerate(segments):
            try:
                hex_q = segment.get('hex_q')
                hex_r = segment.get('hex_r')
                
                if hex_q is None or hex_r is None:
                    continue
                
                hex_cell = self.hex_grid.get_cell(hex_q, hex_r)
                if not hex_cell:
                    continue
                
                # Get segment geometry
                start_point = segment.get('start_point')
                end_point = segment.get('end_point')
                
                if not start_point or not end_point:
                    continue
                
                segment_line = LineString([start_point, end_point])
                
                # Check if segment passes through hex interior
                hex_center = Point(hex_cell.centroid[0], hex_cell.centroid[1])
                
                # If segment passes close to center, it might be crossing interior
                center_distance = segment_line.distance(hex_center)
                hex_radius = hex_cell.size * 0.5  # Approximate hex radius
                
                # If segment is closer to center than to edges, it's likely crossing interior
                if center_distance < hex_radius * 0.3:  # 30% of radius threshold
                    violations.append({
                        'segment_index': i,
                        'violation_type': 'interior_crossing',
                        'description': f'Segment may cross hex interior (distance to center: {center_distance:.3f})',
                        'center_distance': center_distance,
                        'hex_radius': hex_radius,
                        'segment': segment
                    })
                
            except Exception as e:
                violations.append({
                    'segment_index': i,
                    'violation_type': 'interior_validation_error',
                    'description': f'Error checking interior crossing: {str(e)}',
                    'segment': segment
                })
        
        return violations
    
    def _find_connected_components(self, segments: List[Dict[str, Any]], 
                                 endpoints: Dict[Tuple[float, float], List[int]]) -> List[List[int]]:
        """Find connected components in segment graph."""
        visited = set()
        components = []
        
        def dfs(segment_idx: int, component: List[int]):
            if segment_idx in visited:
                return
            visited.add(segment_idx)
            component.append(segment_idx)
            
            # Find connected segments through shared endpoints
            segment = segments[segment_idx]
            start_point = segment.get('start_point')
            end_point = segment.get('end_point')
            
            if start_point:
                start_key = (round(start_point[0], 6), round(start_point[1], 6))
                for connected_idx in endpoints.get(start_key, []):
                    if connected_idx != segment_idx:
                        dfs(connected_idx, component)
            
            if end_point:
                end_key = (round(end_point[0], 6), round(end_point[1], 6))
                for connected_idx in endpoints.get(end_key, []):
                    if connected_idx != segment_idx:
                        dfs(connected_idx, component)
        
        # Find all connected components
        for i in range(len(segments)):
            if i not in visited:
                component = []
                dfs(i, component)
                if component:
                    components.append(component)
        
        return components
    
    def generate_validation_report(self, validation_results: Dict[str, Any]) -> str:
        """Generate human-readable validation report."""
        report = []
        report.append("=" * 80)
        report.append("WATERWAY RULES VALIDATION REPORT")
        report.append("=" * 80)
        
        # Summary
        report.append(f"Total segments analyzed: {validation_results['total_segments']}")
        report.append(f"Total waterways: {validation_results['total_waterways']}")
        report.append(f"Valid segments: {validation_results['valid_segments']}")
        report.append(f"Invalid segments: {validation_results['invalid_segments']}")
        report.append(f"Overall validation: {'PASSED' if validation_results['validation_passed'] else 'FAILED'}")
        report.append("")
        
        # Detailed violations
        if validation_results['edge_following_violations']:
            report.append("RULE 1 VIOLATIONS: Edge Following")
            report.append("-" * 40)
            for violation in validation_results['edge_following_violations'][:10]:  # Limit to first 10
                report.append(f"  - {violation['description']}")
            if len(validation_results['edge_following_violations']) > 10:
                report.append(f"  ... and {len(validation_results['edge_following_violations']) - 10} more")
            report.append("")
        
        if validation_results['connectivity_violations']:
            report.append("RULE 2 VIOLATIONS: Connectivity")
            report.append("-" * 40)
            for violation in validation_results['connectivity_violations']:
                report.append(f"  - {violation['description']}")
            report.append("")
        
        if validation_results['interior_crossing_violations']:
            report.append("RULE 3 VIOLATIONS: Interior Crossing")
            report.append("-" * 40)
            for violation in validation_results['interior_crossing_violations'][:10]:  # Limit to first 10
                report.append(f"  - {violation['description']}")
            if len(validation_results['interior_crossing_violations']) > 10:
                report.append(f"  ... and {len(validation_results['interior_crossing_violations']) - 10} more")
            report.append("")
        
        report.append("=" * 80)
        return "\n".join(report)


def validate_waterway_implementation(waterway_segments: List[Dict[str, Any]], 
                                   hex_grid) -> Tuple[bool, str]:
    """
    Main validation function for waterway implementation.
    
    Args:
        waterway_segments: List of waterway segments to validate
        hex_grid: HexGrid instance
        
    Returns:
        Tuple of (validation_passed, validation_report)
    """
    validator = WaterwayValidator(hex_grid)
    results = validator.validate_all_waterways(waterway_segments)
    report = validator.generate_validation_report(results)
    
    return results['validation_passed'], report