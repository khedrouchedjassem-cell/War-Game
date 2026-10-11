"""
Optimized waterway graphics items for high-performance rendering.
Solves the segmentation and performance issues by consolidating segments.
"""

from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsItem
from PyQt6.QtGui import QPen, QColor, QPainterPath
from PyQt6.QtCore import Qt
from typing import List, Dict, Any
from shapely.geometry import LineString


class ConsolidatedWaterwayItem(QGraphicsPathItem):
    """
    High-performance waterway item that renders multiple segments as a single path.
    This solves both the performance issue and segmentation problem.
    """
    
    def __init__(self, waterway_name: str, waterway_type: str, segments: List[Dict[str, Any]]):
        super().__init__()
        
        self.waterway_name = waterway_name or "Unnamed Waterway"
        self.waterway_type = waterway_type or "unknown"
        self.segments = segments
        self.segment_count = len(segments)
        
        # Create consolidated path from all segments
        self._create_consolidated_path()
        
        # Set visual properties
        self._set_waterway_style()
        
        # Set Z-value to appear above hexes but below roads
        self.setZValue(1)
        
        # Enable interaction
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
    
    def _create_consolidated_path(self):
        """Create a single QPainterPath from all segments."""
        path = QPainterPath()
        
        if not self.segments:
            return
        
        # Group connected segments into continuous paths
        continuous_paths = self._group_connected_segments()
        
        for segment_group in continuous_paths:
            if not segment_group:
                continue
            
            # Start the path at first segment's start point
            first_segment = segment_group[0]
            start_x, start_y = first_segment.get('start_point', (0, 0))
            path.moveTo(start_x, start_y)
            
            # Add lines for each segment in the group
            for segment in segment_group:
                end_x, end_y = segment.get('end_point', (0, 0))
                path.lineTo(end_x, end_y)
        
        self.setPath(path)
    
    def _group_connected_segments(self) -> List[List[Dict[str, Any]]]:
        """Group segments that are connected end-to-end."""
        if not self.segments:
            return []
        # Build a connectivity graph using rounded endpoint coordinates as keys
        # This will tolerate tiny floating point differences while still
        # preserving topology.
        def key_from_point(pt):
            # pt may be (x,y) or shapely Point-like; round to 6 decimal places
            try:
                x, y = pt
            except Exception:
                return None
            return (round(float(x), 6), round(float(y), 6))

        # Collect endpoints and map them to segment indices
        endpoints = []  # list of (start_key, end_key)
        for seg in self.segments:
            sk = key_from_point(seg.get('start_point', (0.0, 0.0)))
            ek = key_from_point(seg.get('end_point', (0.0, 0.0)))
            endpoints.append((sk, ek))

        # adjacency: point_key -> list of (neighbor_point_key, segment_index)
        adj = {}
        for idx, (sk, ek) in enumerate(endpoints):
            adj.setdefault(sk, []).append((ek, idx))
            adj.setdefault(ek, []).append((sk, idx))

        visited_segments = set()
        groups = []

        # Helper to append segment to chain in correct orientation
        def oriented_segment(seg_idx, from_key):
            seg = dict(self.segments[seg_idx])
            sk, ek = endpoints[seg_idx]
            # If the segment's start matches from_key, orientation is fine
            if sk == from_key:
                return seg
            else:
                # swap orientation so start_point matches from_key
                seg = dict(seg)
                seg_start = seg.get('start_point')
                seg_end = seg.get('end_point')
                seg['start_point'] = seg_end
                seg['end_point'] = seg_start
                # also swap any hex/q,r metadata if present
                if 'hex_q' in seg or 'hex_r' in seg:
                    # best-effort: swap hex info if present
                    seg['hex_q_start'] = seg.get('hex_q')
                    seg['hex_q_end'] = seg.get('hex_q_end', seg.get('hex_q'))
                return seg

        # Find terminal nodes (degree != 2). Prefer degree == 1 as chain starts
        terminal_nodes = [pt for pt, nbrs in adj.items() if len(nbrs) == 1]

        # Traverse from each terminal node to build chains
        for node in terminal_nodes:
            # For each connected segment at this terminal that isn't visited, walk along
            for neighbor, seg_idx in list(adj.get(node, [])):
                if seg_idx in visited_segments:
                    continue
                chain = []
                current_node = node
                while True:
                    # Find next unvisited segment connected to current_node
                    next_seg = None
                    next_neighbor = None
                    for nbr, sidx in adj.get(current_node, []):
                        if sidx in visited_segments:
                            continue
                        next_seg = sidx
                        next_neighbor = nbr
                        break

                    if next_seg is None:
                        break

                    # Append oriented segment
                    chain.append(oriented_segment(next_seg, current_node))
                    visited_segments.add(next_seg)

                    # Move to the other endpoint
                    current_node = next_neighbor

                if chain:
                    groups.append(chain)

        # After terminal-based traversal, there may be cycles (closed rings) or
        # remaining segments connected only by degree==2 nodes. Traverse any
        # remaining unvisited segments to extract those cycles.
        remaining = [i for i in range(len(self.segments)) if i not in visited_segments]
        for start_idx in remaining:
            if start_idx in visited_segments:
                continue
            # start from this segment, pick its start_key
            sk, ek = endpoints[start_idx]
            # Try to start at sk
            chain = []
            current_node = sk
            while True:
                # find an unvisited segment connected to current_node
                next_seg = None
                next_neighbor = None
                for nbr, sidx in adj.get(current_node, []):
                    if sidx in visited_segments:
                        continue
                    next_seg = sidx
                    next_neighbor = nbr
                    break

                if next_seg is None:
                    break

                chain.append(oriented_segment(next_seg, current_node))
                visited_segments.add(next_seg)
                current_node = next_neighbor

                # If we've returned to the start of a cycle, stop
                if current_node == sk:
                    break

            if chain:
                groups.append(chain)

        # Fallback: if nothing produced, return original full list as a single group
        if not groups:
            return [self.segments]

        return groups
    
    def _set_waterway_style(self):
        """Set visual style for consolidated waterways."""
        # Determine pen width based on waterway type
        base_width = 3
        if self.waterway_type in ['river']:
            base_width = 5
        elif self.waterway_type in ['stream', 'creek']:
            base_width = 3
        elif self.waterway_type in ['canal']:
            base_width = 4
        
        # Water styling - blue colors
        if self.waterway_type in ['river']:
            pen = QPen(QColor(0, 120, 255), base_width)  # Bright blue for rivers
        elif self.waterway_type in ['stream', 'creek']:
            pen = QPen(QColor(70, 140, 255), base_width)  # Lighter blue for streams
        elif self.waterway_type in ['canal']:
            pen = QPen(QColor(0, 100, 200), base_width)  # Darker blue for canals
        else:
            pen = QPen(QColor(100, 150, 255), base_width)  # Default blue
        
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)
    
    def highlight_waterway(self):
        """Highlight this consolidated waterway."""
        try:
            current_pen = self.pen()
            highlighted_pen = QPen(QColor(255, 255, 0), current_pen.width() + 2)  # Yellow highlight
            highlighted_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            highlighted_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            self.setPen(highlighted_pen)
            self.setZValue(10)  # Bring to front
        except (RuntimeError, AttributeError):
            # Object has been deleted, ignore
            pass
    
    def restore_normal_style(self):
        """Restore normal waterway appearance."""
        try:
            self._set_waterway_style()
            self.setZValue(1)  # Return to normal layer
        except (RuntimeError, AttributeError):
            # Object has been deleted, ignore
            pass
    
    def mousePressEvent(self, event):
        """Handle mouse click on waterway."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Get the parent map view and trigger waterway selection
            view = self.scene().views()[0] if self.scene() and self.scene().views() else None
            if hasattr(view, 'select_waterway'):
                view.select_waterway(self)
        super().mousePressEvent(event)
    
    def hoverEnterEvent(self, event):
        """Handle hover enter - highlight waterway."""
        current_pen = self.pen()
        highlighted_pen = QPen(current_pen.color().lighter(130), current_pen.width() + 1)
        highlighted_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        highlighted_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(highlighted_pen)
        
        # Create informative tooltip
        tooltip = f"{self.waterway_name} ({self.waterway_type})"
        tooltip += f"\nSegments: {self.segment_count}"
        if self.segments:
            first_segment = self.segments[0]
            hex_info = f"Starts at Hex: ({first_segment.get('hex_q', '?')}, {first_segment.get('hex_r', '?')})"
            tooltip += f"\n{hex_info}"
        
        self.setToolTip(tooltip)
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        """Handle hover leave - restore normal appearance."""
        self._set_waterway_style()
        super().hoverLeaveEvent(event)
    
    def get_waterway_name(self) -> str:
        """Get the waterway name for selection purposes."""
        return self.waterway_name


def consolidate_waterway_segments(edge_segments: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group edge segments by waterway name for consolidation.
    
    Args:
        edge_segments: List of individual edge segments
        
    Returns:
        Dictionary mapping waterway names to their segment lists
    """
    waterway_groups = {}
    
    for segment in edge_segments:
        name = segment.get('name', 'Unnamed Waterway')
        waterway_type = segment.get('waterway_type', 'unknown')
        
        # Create a key that includes both name and type for better grouping
        key = f"{name}_{waterway_type}"
        
        if key not in waterway_groups:
            waterway_groups[key] = {
                'name': name,
                'type': waterway_type,
                'segments': []
            }
        
        waterway_groups[key]['segments'].append(segment)
    
    return waterway_groups