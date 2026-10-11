"""
Map view component for displaying hexagonal grid, terrain, and units.
"""
import math
import geopandas as gpd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Set, Tuple, List
from enum import Enum
import warnings
import logging
import os

from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPolygonItem,
    QGraphicsEllipseItem, QGraphicsPixmapItem, QGraphicsTextItem, QMenu, QMessageBox,
    QGraphicsLineItem
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QPolygonF, QPen, QBrush, QColor, QPainter, QFont, 
    QLinearGradient, QRadialGradient, QWheelEvent, QMouseEvent,
    QKeyEvent, QPainterPath, QPixmap, QIcon
)
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

from models.hexcell import HexCell
from models.unit import Unit
from core.hexgrid import HexGrid
from utils.icons import get_unit_icon, get_icon_manager

from core.hexgrid import HexGrid
from models.hexcell import HexCell
from models.unit import Unit, UnitSide


class DisplayMode(Enum):
    """Display modes for the map."""
    ELEVATION = "elevation"
    TERRAIN = "terrain"
    MOVEMENT_COST = "movement_cost"
    COVER = "cover"
    LOS_BLOCKING = "los_blocking"
    CONTROL = "control"


from utils.config import get_config

class RoadItem(QGraphicsLineItem):
    """
    Graphics item representing a road as a line feature.
    """
    
    def __init__(self, road_geometry, road_data: dict):
        super().__init__()
        
        # Store all road metadata
        # GIS attribute tables represent missing text values as NaN (a float).
        # Qt's setToolTip() accepts only strings, so normalize the road name once
        # when the item is created.
        road_name = road_data.get('name')
        self.road_name = road_name.strip() if isinstance(road_name, str) and road_name.strip() else 'Unnamed Road'
        self.road_type = road_data.get('type', 'unknown')
        self.road_ref = road_data.get('ref', '')
        self.road_oneway = road_data.get('oneway', False)
        self.road_maxspeed = road_data.get('maxspeed', 0)
        self.road_bridge = road_data.get('bridge', False)
        self.road_tunnel = road_data.get('tunnel', False)
        self.road_layer = road_data.get('layer', 0)
        self.road_osm_id = road_data.get('osm_id', '')
        self.road_geometry = road_geometry
        self.start_hex = road_data.get('start_hex', (0, 0))
        self.end_hex = road_data.get('end_hex', (0, 0))
        
        # Road selection state
        self.is_highlighted = False
        self.original_pen = None
        
        # Create line from road geometry
        self._create_road_line()
        
        # Set visual properties based on road type
        self._set_road_style()
        
        # Set Z-value to appear above hexes but below units
        self.setZValue(2)
        
        # Enable hover and click events
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    
    def _create_road_line(self):
        """Create the road line from geometry coordinates."""
        if hasattr(self.road_geometry, 'coords'):
            coords = list(self.road_geometry.coords)
            if len(coords) >= 2:
                # For now, create a simple line from start to end
                # TODO: Could be enhanced to draw all segments
                start_x, start_y = coords[0]
                end_x, end_y = coords[-1]
                self.setLine(start_x, start_y, end_x, end_y)
    
    def _set_road_style(self):
        """Set visual style - uniform color for all roads."""
        # Uniform road styling - same color for all road types
        pen = QPen(QColor(100, 100, 100), 50)  # Dark gray, consistent width
        
        # Special styling for bridges and tunnels
        if self.road_bridge:
            pen.setStyle(Qt.PenStyle.DashLine)  # Dashed for bridges
        elif self.road_tunnel:
            pen.setStyle(Qt.PenStyle.DotLine)  # Dotted for tunnels
        
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
    
    def hoverEnterEvent(self, event):
        """Handle hover enter - highlight road."""
        current_pen = self.pen()
        highlighted_pen = QPen(current_pen.color().lighter(150), current_pen.width() + 30)
        highlighted_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        highlighted_pen.setStyle(current_pen.style())  # Preserve dash/dot style
        self.setPen(highlighted_pen)
        
        # Simple tooltip with only road name
        if self.road_name and self.road_name != 'Unnamed Road':
            self.setToolTip(self.road_name)
        else:
            self.setToolTip("Unnamed Road")
        
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        """Handle hover leave - restore normal appearance."""
        if not self.is_highlighted:
            self._set_road_style()
        super().hoverLeaveEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse click on road segment."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Get the parent map view and trigger road selection
            view = self.scene().views()[0] if self.scene() and self.scene().views() else None
            if hasattr(view, 'select_road'):
                view.select_road(self)
        super().mousePressEvent(event)
    
    def get_road_identifier(self):
        """Get unique identifier for this road (name + ref combination)."""
        if self.road_name and self.road_name != 'Unnamed Road':
            if self.road_ref:
                return f"{self.road_name} ({self.road_ref})"
            else:
                return self.road_name
        elif self.road_ref:
            return self.road_ref
        else:
            return f"{self.road_type}_{self.road_osm_id}"
    
    def highlight_road(self, highlight: bool = True):
        """Highlight or unhighlight this road segment."""
        try:
            self.is_highlighted = highlight
            if highlight:
                if not self.original_pen:
                    self.original_pen = self.pen()
                # Create highlight pen (brighter and thicker)
                highlight_pen = QPen(self.original_pen.color().lighter(200), 
                                   self.original_pen.width() + 40)
                highlight_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                highlight_pen.setStyle(self.original_pen.style())
                self.setPen(highlight_pen)
                self.setZValue(5)  # Bring to front
            else:
                if self.original_pen:
                    self.setPen(self.original_pen)
                self.setZValue(2)  # Reset to normal layer
        except RuntimeError:
            # Object has been deleted, ignore
            pass
    
    def get_metadata_dict(self):
        """Get all road metadata as a dictionary."""
        return {
            'name': self.road_name,
            'type': self.road_type,
            'ref': self.road_ref,
            'oneway': self.road_oneway,
            'maxspeed': self.road_maxspeed,
            'bridge': self.road_bridge,
            'tunnel': self.road_tunnel,
            'layer': self.road_layer,
            'osm_id': self.road_osm_id,
            'start_hex': self.start_hex,
            'end_hex': self.end_hex
        }


class WaterWayItem(QGraphicsLineItem):
    """
    Graphics item representing a waterway (river, stream, etc.).
    """
    
    def __init__(self, water_geometry, water_name: str, water_type: str):
        super().__init__()
        
        self.water_name = water_name
        self.water_type = water_type
        self.water_geometry = water_geometry
        
        # Create line from water geometry
        self._create_water_line()
        
        # Set visual properties
        self._set_water_style()
        
        # Set Z-value to appear above hexes but below roads
        self.setZValue(1)
        
        # Enable interaction
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
    
    def _create_water_line(self):
        """Create the water line from geometry coordinates."""
        if hasattr(self.water_geometry, 'coords'):
            coords = list(self.water_geometry.coords)
            if len(coords) >= 2:
                if len(coords) == 2:
                    start_x, start_y = coords[0]
                    end_x, end_y = coords[1]
                    self.setLine(start_x, start_y, end_x, end_y)
                else:
                    start_x, start_y = coords[0]
                    end_x, end_y = coords[-1]
                    self.setLine(start_x, start_y, end_x, end_y)
    
    def _set_water_style(self):
        """Set visual style for waterways."""
        # Water styling - blue colors
        if self.water_type in ['river', 'stream']:
            pen = QPen(QColor(0, 150, 255), 50)  # Blue, medium width
        else:
            pen = QPen(QColor(0, 100, 200), 40)  # Darker blue
        
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
    
    def hoverEnterEvent(self, event):
        """Handle hover enter - highlight waterway."""
        current_pen = self.pen()
        highlighted_pen = QPen(current_pen.color().lighter(130), current_pen.width() + 30)
        highlighted_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(highlighted_pen)
        
        self.setToolTip(f"{self.water_name} ({self.water_type})")
        super().hoverEnterEvent(event)
    
    def highlight_waterway(self):
        """Highlight this waterway segment."""
        try:
            current_pen = self.pen()
            highlighted_pen = QPen(QColor(255, 255, 0), current_pen.width() + 3)  # Yellow highlight
            highlighted_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self.setPen(highlighted_pen)
            self.setZValue(10)  # Bring to front
        except (RuntimeError, AttributeError):
            # Object has been deleted, ignore
            pass
    
    def restore_normal_style(self):
        """Restore normal waterway appearance."""
        try:
            self._set_water_style()
            self.setZValue(1)  # Return to normal layer
        except (RuntimeError, AttributeError):
            # Object has been deleted, ignore
            pass
    
    def mousePressEvent(self, event):
        """Handle mouse click on waterway segment."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Get the parent map view and trigger waterway selection
            view = self.scene().views()[0] if self.scene() and self.scene().views() else None
            if hasattr(view, 'select_waterway'):
                view.select_waterway(self)
        super().mousePressEvent(event)
    
    def hoverLeaveEvent(self, event):
        """Handle hover leave - restore normal appearance."""
        self._set_water_style()
        super().hoverLeaveEvent(event)


class EdgeWaterWayItem(QGraphicsLineItem):
    """
    Graphics item representing a waterway along hex cell edges.
    This renders waterways as edge-aligned segments for tactical authenticity.
    """
    
    def __init__(self, edge_segment: Dict, hex_grid: HexGrid):
        super().__init__()
        
        self.edge_segment = edge_segment
        self.hex_grid = hex_grid
        self.water_name = edge_segment.get('name', 'Unnamed Waterway')
        self.water_type = edge_segment.get('waterway_type', 'unknown')
        self.water_width = edge_segment.get('width', 0.0)
        
        # Create line along hex edge
        self._create_edge_line()
        
        # Set visual properties
        self._set_water_style()
        
        # Set Z-value to appear above hexes but below roads
        self.setZValue(1)
        
        # Enable interaction
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
    
    def _create_edge_line(self):
        """Create the waterway line along the hex edge using specific start/end points."""
        # Use the exact start and end points from the connectivity algorithm
        start_point = self.edge_segment.get('start_point')
        end_point = self.edge_segment.get('end_point')
        
        if start_point and end_point:
            start_x, start_y = start_point
            end_x, end_y = end_point
            self.setLine(start_x, start_y, end_x, end_y)
        else:
            # Fallback to full edge if specific points not available
            hex_q = self.edge_segment['hex_q']
            hex_r = self.edge_segment['hex_r']
            edge_index = self.edge_segment['edge_index']
            
            # Get the hex cell
            hex_cell = self.hex_grid.get_cell(hex_q, hex_r)
            if hex_cell:
                edge_coords = hex_cell.get_edge_coordinates(edge_index)
                if edge_coords and len(edge_coords) >= 2:
                    start_x, start_y = edge_coords[0]
                    end_x, end_y = edge_coords[1]
                    self.setLine(start_x, start_y, end_x, end_y)
    
    def _set_water_style(self):
        """Set visual style for edge-aligned waterways."""
        # Determine pen width based on waterway type and width
        base_width = 30
        if self.water_type in ['river']:
            base_width = 60
        elif self.water_type in ['stream', 'creek']:
            base_width = 30
        elif self.water_type in ['canal']:
            base_width = 50
        
        # Apply width from data if available
        if self.water_width > 0:
            base_width = max(2, min(int(self.water_width / 2), 8))
        
        # Water styling - blue colors with edge alignment
        if self.water_type in ['river']:
            pen = QPen(QColor(0, 120, 255), base_width)  # Bright blue for rivers
        elif self.water_type in ['stream', 'creek']:
            pen = QPen(QColor(70, 140, 255), base_width)  # Lighter blue for streams
        elif self.water_type in ['canal']:
            pen = QPen(QColor(0, 100, 200), base_width)  # Darker blue for canals
        else:
            pen = QPen(QColor(0, 130, 220), base_width)  # Default blue
        
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
    
    def hoverEnterEvent(self, event):
        """Handle hover enter - highlight waterway edge."""
        current_pen = self.pen()
        highlighted_pen = QPen(current_pen.color().lighter(140), current_pen.width() + 2)
        highlighted_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(highlighted_pen)
        
        # Create informative tooltip
        tooltip = f"{self.water_name} ({self.water_type})"
        if self.water_width > 0:
            tooltip += f"\nWidth: {self.water_width:.1f}m"
        hex_info = f"Hex: ({self.edge_segment['hex_q']}, {self.edge_segment['hex_r']}) Edge: {self.edge_segment['edge_index']}"
        tooltip += f"\n{hex_info}"
        
        self.setToolTip(tooltip)
        super().hoverEnterEvent(event)
    
    def highlight_waterway(self):
        """Highlight this waterway segment."""
        try:
            current_pen = self.pen()
            highlighted_pen = QPen(QColor(255, 255, 0), current_pen.width() + 3)  # Yellow highlight
            highlighted_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self.setPen(highlighted_pen)
            self.setZValue(10)  # Bring to front
        except (RuntimeError, AttributeError):
            # Object has been deleted, ignore
            pass
    
    def restore_normal_style(self):
        """Restore normal waterway appearance."""
        try:
            self._set_water_style()
            self.setZValue(1)  # Return to normal layer
        except (RuntimeError, AttributeError):
            # Object has been deleted, ignore
            pass
    
    def mousePressEvent(self, event):
        """Handle mouse click on waterway segment."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Get the parent map view and trigger waterway selection
            view = self.scene().views()[0] if self.scene() and self.scene().views() else None
            if hasattr(view, 'select_waterway'):
                view.select_waterway(self)
        super().mousePressEvent(event)
    
    def hoverLeaveEvent(self, event):
        """Handle hover leave - restore normal appearance."""
        self._set_water_style()
        super().hoverLeaveEvent(event)


class HexItem(QGraphicsPolygonItem):
    """
    Graphics item representing a hexagonal cell.
    """
    
    def __init__(self, hex_cell: HexCell, display_mode: DisplayMode = DisplayMode.TERRAIN):
        super().__init__()
        
        self.hex_cell = hex_cell
        self.display_mode = display_mode
        
        # Visual state (must be set before _update_appearance)
        self.is_highlighted = False
        self.is_selected = False
        self.is_valid_move = False  # New state for movement highlighting
        
        # Create hex polygon
        self._create_polygon()
        
        # Set visual properties
        self._update_appearance()
        
        # Enable interaction
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
    
    def _create_polygon(self):
        """Create the hexagonal polygon shape."""
        if not self.hex_cell.polygon:
            return
        
        # Get polygon coordinates
        coords = list(self.hex_cell.polygon.exterior.coords)
        
        # Convert to QPolygonF
        polygon = QPolygonF()
        for x, y in coords[:-1]:  # Skip last point (same as first)
            polygon.append(QPointF(x, y))
        
        self.setPolygon(polygon)
    
    def _update_appearance(self):
        """Update visual appearance based on display mode."""
        color = self._get_color_for_mode()
        
        # Set fill brush
        brush = QBrush(color)
        self.setBrush(brush)
        
        # Set border pen with enhanced highlighting for movement
        pen_color = QColor(100, 100, 100, 100)
        pen_width = 30
        
        if self.is_valid_move:
            # Bright thick border for valid movement hexes
            pen_color = QColor(0, 255, 0, 255)  # Bright green
            pen_width = 50  # Thicker border
        elif self.is_highlighted:
            pen_color = QColor(255, 255, 0, 200)  # Yellow highlight
            pen_width = 80
        elif self.is_selected:
            pen_color = QColor(255, 0, 0, 200)  # Red selection
            pen_width = 80

        pen = QPen(pen_color, pen_width)
        self.setPen(pen)
        
        # Set Z-value for layering
        self.setZValue(0)
    
    def _get_color_for_mode(self) -> QColor:
        """Get color based on display mode and hex properties."""
        if self.display_mode == DisplayMode.ELEVATION:
            return self._get_elevation_color()
        elif self.display_mode == DisplayMode.TERRAIN:
            return self._get_terrain_color()
        elif self.display_mode == DisplayMode.MOVEMENT_COST:
            return self._get_movement_cost_color()
        elif self.display_mode == DisplayMode.COVER:
            return self._get_cover_color()
        elif self.display_mode == DisplayMode.LOS_BLOCKING:
            return self._get_los_blocking_color()
        elif self.display_mode == DisplayMode.CONTROL:
            return self._get_control_color()
        else:
            return QColor(200, 200, 200, 100)  # Default gray
    
    def _get_elevation_color(self) -> QColor:
        """Get color based on elevation."""
        elevation = self.hex_cell.elevation_mean

        # Normalize elevation to 0-1 range (assuming 0-1500m range)
        normalized = max(0, min(1, elevation / 1500.0))
        
        # Use terrain colormap
        cmap = plt.cm.terrain
        rgba = cmap(normalized)
        
        return QColor(int(rgba[0] * 255), int(rgba[1] * 255), 
                     int(rgba[2] * 255), 150)
    
    def _get_terrain_color(self) -> QColor:
        """Get color based on advanced terrain classification."""
        # Enhanced terrain color palette with realistic colors
        terrain_colors = {
            # WATER BODIES
            'sea': QColor(0, 100, 255, 180),              # Bright blue sea
            'shore': QColor(0, 100, 250, 150),            # Sandy beach
            'lake': QColor(70, 130, 200, 170),            # Lake blue
            'river': QColor(100, 150, 220, 160),          # River blue
            'mountain_lake': QColor(50, 100, 180, 170),   # Mountain lake
            'wetland': QColor(80, 120, 80, 160),          # Marsh green
            
            # INFRASTRUCTURE
            'urban_dense': QColor(140, 140, 140, 180),    # Dense urban gray
            'urban_hills': QColor(120, 120, 120, 170),    # Hilly urban
            'urban_mountain': QColor(100, 100, 100, 160), # Mountain settlements
            'highway': QColor(180, 180, 180, 150),        # Highway gray
            'mountain_road': QColor(160, 140, 120, 150),  # Mountain road
            'trail': QColor(140, 120, 100, 140),          # Trail brown
            
            # FORESTS
            'forest_lowland': QColor(40, 120, 40, 170),   # Lowland forest
            'forest_hills': QColor(30, 100, 30, 170),     # Hill forest
            'forest_mountain': QColor(20, 80, 20, 170),   # Mountain forest
            
            # AGRICULTURE
            'farmland': QColor(180, 200, 120, 150),       # Cultivated land
            'pasture': QColor(120, 160, 80, 150),         # Grassland
            'rough_pasture': QColor(100, 140, 70, 150),   # Rough grazing
            
            # COASTAL
            'coastal_plain': QColor(220, 200, 150, 150),  # Coastal plain
            'coastal_cliff': QColor(180, 160, 140, 160),  # Coastal cliffs
            
            # LOWLANDS
            'plains': QColor(160, 200, 120, 150),         # Open plains
            'rolling_hills': QColor(140, 180, 100, 150),  # Rolling hills
            'hills': QColor(120, 160, 80, 160),           # Hills
            'steep_hills': QColor(100, 140, 70, 160),     # Steep hills
            
            # HIGHLANDS
            'plateau': QColor(150, 130, 100, 160),        # High plateau
            'highlands': QColor(130, 110, 80, 160),       # Highland terrain
            'steep_slopes': QColor(110, 90, 70, 170),     # Steep slopes
            'cliffs': QColor(90, 70, 50, 180),            # Cliff faces
            
            # MOUNTAINS
            'mountain_valley': QColor(120, 140, 100, 150), # Mountain valley
            'mountain_slopes': QColor(100, 100, 80, 170),  # Mountain slopes
            'mountain_steep': QColor(80, 80, 60, 180),     # Steep mountains
            'alpine_meadow': QColor(140, 160, 120, 150),   # Alpine meadows
            'high_mountain': QColor(70, 70, 70, 180),      # High mountains
            'mountain_peak': QColor(50, 50, 50, 190),      # Mountain peaks
            
            # SPECIAL TERRAIN
            'desert': QColor(200, 180, 120, 150),         # Desert sand
            
            # LEGACY SUPPORT
            'water': QColor(100, 150, 255, 150),          # Generic water
            'flat': QColor(144, 238, 144, 150),           # Generic flat
            'urban': QColor(169, 169, 169, 150),          # Generic urban
            'forest': QColor(34, 139, 34, 150),           # Generic forest
            'unknown': QColor(200, 200, 200, 120)         # Unknown terrain
        }
        
        terrain_type = self.hex_cell.terrain_type
        
        # Return color for terrain type, with fallback to unknown
        return terrain_colors.get(terrain_type, terrain_colors['unknown'])
    
    def _get_movement_cost_color(self) -> QColor:
        """Get color based on movement cost for infantry."""
        cost = self.hex_cell.movement_cost.get('infantry', 1.0)
        
        if cost == float('inf'):
            return QColor(255, 0, 0, 150)  # Red for impassable
        
        # Normalize cost (1.0 = easy, 4.0+ = difficult)
        normalized = max(0, min(1, (cost - 1.0) / 3.0))
        
        # Green to red gradient
        if normalized < 0.5:
            # Green to yellow
            red = int(255 * normalized * 2)
            green = 255
        else:
            # Yellow to red
            red = 255
            green = int(255 * (1 - normalized) * 2)
        
        return QColor(red, green, 0, 150)
    
    def _get_cover_color(self) -> QColor:
        """Get color based on cover value."""
        cover = self.hex_cell.cover_value
        
        # More cover = darker color
        gray_value = int(255 * (1 - cover))
        return QColor(gray_value, gray_value, gray_value, 150)
    
    def _get_los_blocking_color(self) -> QColor:
        """Get color based on line-of-sight blocking height."""
        height = self.hex_cell.los_blocking_height - self.hex_cell.elevation_mean
        
        # Normalize to 0-20m range
        normalized = max(0, min(1, height / 20.0))
        
        # Purple gradient
        purple_value = int(128 + 127 * normalized)
        return QColor(purple_value, 0, purple_value, 150)
    
    def _get_control_color(self) -> QColor:
        """Get color based on hex control."""
        if self.hex_cell.controlled_by == 'red':
            return QColor(255, 50, 50, 200)  # Brighter red tint
        elif self.hex_cell.controlled_by == 'blue':
            return QColor(50, 50, 255, 200)  # Brighter blue tint
        else:
            return QColor(200, 200, 200, 80)  # Lighter neutral gray
    
    def set_display_mode(self, mode: DisplayMode):
        """Set display mode and update appearance."""
        self.display_mode = mode
        self._update_appearance()
    
    def set_highlighted(self, highlighted: bool):
        """Set highlight state."""
        self.is_highlighted = highlighted
        self._update_appearance()
    
    def set_selected(self, selected: bool):
        """Set selection state."""
        self.is_selected = selected
        self._update_appearance()
    
    def set_valid_move(self, valid: bool):
        """Set valid movement state."""
        self.is_valid_move = valid
        self._update_appearance()
    
    def hoverEnterEvent(self, event):
        """Handle mouse hover enter."""
        self.set_highlighted(True)
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        """Handle mouse hover leave."""
        self.set_highlighted(False)
        super().hoverLeaveEvent(event)


class UnitItem(QGraphicsPixmapItem):
    """
    Graphics item representing a military unit with proper military icons.
    """
    
    def __init__(self, unit: Unit, hex_size: Optional[float] = None):
        super().__init__()
        
        # Use config for hex_size if not provided
        if hex_size is None:
            config = get_config()
            hex_size = config.simulation.hex_size
        
        self.unit = unit
        self.hex_size = hex_size
        
        # Visual state (must be set before _create_unit_graphics)
        self.is_highlighted = False
        self.is_selected = False
        
        # Store original pixmap for restoring after effects
        self.original_pixmap = None
        
        # Create unit representation with icon
        self._create_unit_graphics()
        
        # Enable interaction
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setAcceptHoverEvents(True)
        
        # Update position
        self._update_position()
    
    def _create_unit_graphics(self):
        """Create unit visual representation using military icons."""
        # Get icon based on unit type and side
        side_name = self.unit.side.value.lower()  # red, blue, etc.
        unit_type_name = self.unit.unit_type.value.lower()  # infantry, armor, etc.
        
        # Get the icon
        icon = get_unit_icon(unit_type_name, side_name)
        
        # Calculate unit size relative to hex size
        # Base size as percentage of hex diameter (2 * hex_size)
        hex_diameter = 2 * self.hex_size
        
        # Unit size based on type - all relative to hex size
        if unit_type_name in ['tank', 'armor', 'artillery']:
            size_ratio = 0.8  # Heavy units, 80% of hex diameter
        elif unit_type_name == 'command':
            size_ratio = 0.9  # Command units, largest at 90%
        elif unit_type_name in ['recon', 'support']:
            size_ratio = 0.65  # Support units, smaller at 65%
        else:  # infantry and others
            size_ratio = 0.7  # Standard infantry units, 70%
        
        # Calculate final size
        unit_size = int(hex_diameter * size_ratio)
        
        # Create pixmap from icon
        if not icon.isNull():
            pixmap = icon.pixmap(unit_size, unit_size)
            self.setPixmap(pixmap)
        else:
            # Fallback to colored rectangle if icon not found
            pixmap = QPixmap(unit_size, unit_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Color based on side
            if side_name == 'red':
                color = QColor(220, 20, 20, 200)
            elif side_name == 'blue':
                color = QColor(20, 20, 220, 200)
            else:
                color = QColor(100, 100, 100, 200)
            
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor(0, 0, 0), 2))
            painter.drawEllipse(2, 2, unit_size-4, unit_size-4)
            painter.end()
            
            self.setPixmap(pixmap)
        
        # Store the original pixmap for hover effects
        self.original_pixmap = self.pixmap().copy()
        
        # Center the pixmap
        rect = self.pixmap().rect()
        self.setOffset(-rect.width()/2, -rect.height()/2)
        
        # Update appearance (highlight effects)
        self._update_appearance()
        
        # Set Z-value for layering
        self.setZValue(10)
    
    def update_hex_size(self, new_hex_size: float):
        """Update unit size when hex size changes."""
        self.hex_size = new_hex_size
        self._create_unit_graphics()
        self._update_position()
    
    def _update_appearance(self):
        """Update visual appearance for highlighting."""
        try:
            if self.original_pixmap and not self.original_pixmap.isNull():
                # Always start from the original pixmap
                if self.is_highlighted or self.is_selected:
                    # Create effect overlay
                    effect_pixmap = QPixmap(self.original_pixmap.size())
                    effect_pixmap.fill(Qt.GlobalColor.transparent)
                    
                    painter = QPainter(effect_pixmap)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    
                    # Draw original pixmap
                    painter.drawPixmap(0, 0, self.original_pixmap)
                    
                    # Add highlight effect
                    if self.is_highlighted:
                        # Yellow glow effect
                        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
                        painter.fillRect(effect_pixmap.rect(), QColor(255, 255, 0, 60))
                    
                    if self.is_selected:
                        # White border effect
                        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                        painter.setPen(QPen(QColor(255, 255, 255), 3))
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawRect(effect_pixmap.rect().adjusted(1, 1, -2, -2))
                    
                    painter.end()
                    self.setPixmap(effect_pixmap)
                else:
                    # No effects - restore original pixmap
                    self.setPixmap(self.original_pixmap)
            
            # Opacity based on unit status
            if not self.unit.is_alive:
                self.setOpacity(0.3)
            else:
                self.setOpacity(1.0)
        except (RuntimeError, AttributeError):
            # Object has been deleted, ignore
            pass
        
        # Set Z-value for layering
        self.setZValue(10)
    
    def _update_position(self):
        """Update position based on unit's hex position."""
        if self.unit.position:
            x, y = self.unit.position.centroid
            self.setPos(x, y)
    
    def set_highlighted(self, highlighted: bool):
        """Set highlight state."""
        self.is_highlighted = highlighted
        self._update_appearance()
    
    def set_selected(self, selected: bool):
        """Set selection state."""
        self.is_selected = selected
        self._update_appearance()
    
    def update_from_unit(self):
        """Update graphics from unit state."""
        self._update_position()
        self._update_appearance()
    
    def hoverEnterEvent(self, event):
        """Handle mouse hover enter."""
        self.set_highlighted(True)
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event):
        """Handle mouse hover leave."""
        self.set_highlighted(False)
        super().hoverLeaveEvent(event)


class MovementArrow(QGraphicsLineItem):
    """
    Graphics item representing a movement order arrow from start to destination.
    """
    
    def __init__(self, start_pos: Tuple[float, float], end_pos: Tuple[float, float], unit_color: QColor):
        super().__init__()
        
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.unit_color = unit_color
        
        # Create the arrow line
        self.setLine(start_pos[0], start_pos[1], end_pos[0], end_pos[1])
        
        # Set pen style - thick arrow with unit color
        pen = QPen(unit_color, 80)  # Thick and visible but not overwhelming
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        
        # Set Z-value to appear above hexes but below units
        self.setZValue(5)
        
        # Create arrowhead
        self._create_arrowhead()
    
    def _create_arrowhead(self):
        """Create arrowhead at the destination."""
        # Calculate arrow direction
        dx = self.end_pos[0] - self.start_pos[0]
        dy = self.end_pos[1] - self.start_pos[1]
        length = math.sqrt(dx*dx + dy*dy)
        
        if length == 0:
            return
        
        # Normalize direction
        dx /= length
        dy /= length
        
        # Arrowhead size - proportional to 15px line thickness
        head_length = 1000.0  # Prominent arrowhead for good visibility  
        head_width = 800.0   # Wide enough to be clearly visible
        
        # Calculate arrowhead points
        # Back from tip along line direction
        back_x = self.end_pos[0] - dx * head_length
        back_y = self.end_pos[1] - dy * head_length
        
        # Perpendicular direction for width
        perp_x = -dy
        perp_y = dx
        
        # Arrowhead triangle points
        tip_x, tip_y = self.end_pos
        left_x = back_x + perp_x * head_width
        left_y = back_y + perp_y * head_width
        right_x = back_x - perp_x * head_width
        right_y = back_y - perp_y * head_width
        
        # Create arrowhead polygon
        arrowhead = QPolygonF([
            QPointF(tip_x, tip_y),
            QPointF(left_x, left_y),
            QPointF(right_x, right_y)
        ])
        
        # Create arrowhead item
        self.arrowhead_item = QGraphicsPolygonItem(arrowhead, self)
        self.arrowhead_item.setBrush(QBrush(self.unit_color))
        self.arrowhead_item.setPen(QPen(self.unit_color, 80))  # Thick arrowhead border matching 80px line
        self.arrowhead_item.setZValue(1)  # Ensure arrowhead appears above the line


class MapView(QGraphicsView):
    """
    Main map view widget for displaying the hexagonal grid and units.
    """
    
    # Signals
    hex_clicked = pyqtSignal(int, int)  # q, r coordinates
    unit_clicked = pyqtSignal(str)  # unit_id
    unit_move_requested = pyqtSignal(str, int, int)  # unit_id, target_q, target_r
    road_selected = pyqtSignal(dict)  # road_metadata
    waterway_selected = pyqtSignal(dict, list)  # waterway_metadata, segments
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Create scene
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        
        # Core data
        self.hex_grid: Optional[HexGrid] = None
        self.simulation = None  # Will be set by main window
        
        # Map state - start with map flipped by default
        self.is_flipped = True
        
        # Apply initial flip transformation
        transform = self.transform()
        transform.scale(1, -1)  # Flip Y-axis
        self.setTransform(transform)
        
        # Graphics items
        self.hex_items: Dict[Tuple[int, int], HexItem] = {}
        self.unit_items: Dict[str, UnitItem] = {}
        self.movement_arrows: Dict[str, MovementArrow] = {}  # Track movement arrows by unit_id
        
        # Vector feature items
        self.road_items: List[RoadItem] = []
        self.water_items: List[WaterWayItem] = []
        self.edge_water_items: List[EdgeWaterWayItem] = []  # Edge-aligned waterways
        self.show_roads = True  # Toggle for road visibility
        self.show_waterways = True  # Toggle for waterway visibility
        
        # Road selection state
        self.selected_road_segments: List[RoadItem] = []
        self.road_groups: Dict[str, List[RoadItem]] = {}  # Group roads by identifier
        
        # Edge scrolling configuration
        self.edge_scroll_enabled = True
        self.edge_scroll_margin = 20  # Pixel margin from edge to trigger scrolling
        self.edge_scroll_speed = 5.0  # Scrolling speed
        self.edge_scroll_timer = QTimer()
        self.edge_scroll_timer.timeout.connect(self._perform_edge_scroll)
        self.edge_scroll_direction = QPointF(0, 0)  # Current scroll direction
        
        # Zoom limits configuration
        self.min_zoom_factor = 1/200  # Minimum zoom (10% - can see entire map)
        self.max_zoom_factor = 1  # Maximum zoom (5000% - detailed view but not just one cell)
        self.current_zoom_factor = 1 # Current zoom level (100% - default)
        
        # Enable mouse tracking for edge scrolling
        self.setMouseTracking(True)
        
        # Display settings
        self.display_mode = DisplayMode.TERRAIN
        self.show_grid = True
        self.show_coordinates = False
        
        # Interaction state
        self.selected_hex: Optional[Tuple[int, int]] = None
        self.selected_unit: Optional[str] = None
        self.movement_mode = False
        self.selected_unit_for_movement: Optional[str] = None
        
        # View settings
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        # Animation timer
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._update_animations)
        self.animation_timer.start(50)  # 20 FPS
    
    def set_hex_grid(self, hex_grid: HexGrid):
        """Set the hexagonal grid to display."""
        self.hex_grid = hex_grid
        self._create_hex_items()
        self._fit_scene_to_content()
        
        # Update all existing units to use the new hex size
        self._update_all_unit_sizes()
    
    def _update_all_unit_sizes(self):
        """Update all unit sizes to match current hex size."""
        if not self.hex_grid:
            return
            
        hex_size = self.hex_grid.hex_size
        for unit_item in self.unit_items.values():
            unit_item.update_hex_size(hex_size)
    
    def set_simulation(self, simulation):
        """Set the simulation reference for movement validation."""
        self.simulation = simulation
    
    def _cleanup_deleted_items(self):
        """Clean up references to deleted Qt objects."""
        # Clean up unit items
        deleted_units = []
        for unit_id, unit_item in self.unit_items.items():
            try:
                # Try to access a property to check if the object is still valid
                _ = unit_item.pos()
            except (RuntimeError, AttributeError):
                deleted_units.append(unit_id)
        
        for unit_id in deleted_units:
            del self.unit_items[unit_id]
        
        # Clean up selected road segments
        if hasattr(self, 'selected_road_segments'):
            valid_segments = []
            for segment in self.selected_road_segments:
                try:
                    _ = segment.pos()
                    valid_segments.append(segment)
                except (RuntimeError, AttributeError):
                    pass
            self.selected_road_segments = valid_segments
    
    def _create_hex_items(self):
        """Create graphics items for all hex cells and load vector features."""
        if not self.hex_grid:
            return
        
        # Clear existing items
        self.scene.clear()
        self.hex_items.clear()
        self.road_items.clear()
        self.water_items.clear()
        self.edge_water_items.clear()
        
        # Create hex items
        for hex_cell in self.hex_grid:
            hex_item = HexItem(hex_cell, self.display_mode)
            self.scene.addItem(hex_item)
            self.hex_items[(hex_cell.q, hex_cell.r)] = hex_item
        
        # Load and create vector feature items
        self._load_vector_features()
    
    def _load_vector_features(self):
        """Load and create graphics items for vector features (roads, waterways)."""
        
        # Suppress GDAL errors and warnings using environment variables
        os.environ['CPL_LOG'] = '/dev/null'  # Redirect GDAL logs to null
        os.environ['GDAL_DISABLE_READDIR_ON_OPEN'] = 'EMPTY_DIR'
        
        # Suppress warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            warnings.simplefilter("ignore", category=FutureWarning)
            warnings.simplefilter("ignore", category=RuntimeWarning)
            
            try:
                print("Loading vector features...")
                
                # Try to load roads with enhanced processing
                roads_path = Path("data/Vector/roads.shp")
                if roads_path.exists():
                    print("Loading roads data with enhanced processing...")
                    roads_gdf = gpd.read_file(roads_path)
                    
                    # Enhanced road processing
                    try:
                        from utils.gpu_vector_processing import process_roads_with_gpu
                        print("Starting enhanced road processing...")
                        gpu_road_results = process_roads_with_gpu(roads_gdf, self.hex_grid)
                        print(f"Enhanced processing completed for {gpu_road_results.get('processed_roads', 0)} roads")
                        print(f"Generated {gpu_road_results.get('total_coordinates', 0)} processed coordinates")
                    except Exception as e:
                        print(f"Enhanced road processing failed: {e}")
                        print("Falling back to standard road processing...")
                    
                    # Filter roads intelligently
                    filtered_roads = self._filter_roads(roads_gdf)
                    
                    for road_data in filtered_roads:
                        road_item = RoadItem(
                            road_data['geometry'], 
                            road_data  # Pass the entire road data dictionary
                        )
                        if self.show_roads:
                            self.scene.addItem(road_item)
                        self.road_items.append(road_item)
                        
                        # Group roads by identifier for selection
                        road_id = road_item.get_road_identifier()
                        if road_id not in self.road_groups:
                            self.road_groups[road_id] = []
                        self.road_groups[road_id].append(road_item)
                    
                    print(f"Successfully loaded {len(filtered_roads)} roads for display (filtered from {len(roads_gdf)} total)")
                    print(f"   Grouped into {len(self.road_groups)} distinct roads")
                else:
                    print("Roads shapefile not found")
                
                # Try to load waterways with enhanced processing
                waterways_path = Path("data/Vector/water_ways.shp")
                if waterways_path.exists():
                    print("Loading waterways data for enhanced edge alignment...")
                    waterways_gdf = gpd.read_file(waterways_path)
                    
                    # Enhanced waterway processing
                    try:
                        from utils.gpu_vector_processing import process_waterways_with_gpu
                        print("Starting enhanced waterway processing...")
                        gpu_results = process_waterways_with_gpu(waterways_gdf, self.hex_grid)
                        print(f"Enhanced processing completed for {gpu_results.get('processed_waterways', 0)} waterways")
                        print(f"Generated {gpu_results.get('total_segments', 0)} processed segments")
                        
                        # Validate waterway rules implementation
                        from utils.waterway_validator import WaterwayValidator
                        validator = WaterwayValidator(self.hex_grid)
                        print("Starting waterway rules validation...")
                        
                        # Convert GeoDataFrame to expected format
                        waterway_segments = []
                        for idx, row in waterways_gdf.iterrows():
                            segment = {
                                'geometry': row.geometry,
                                'waterway_id': row.get('name', f'waterway_{idx}'),
                                'segment_id': idx,
                                'properties': dict(row)
                            }
                            waterway_segments.append(segment)
                        
                        validation_result = validator.validate_all_waterways(waterway_segments)
                        
                        if validation_result.get('total_errors', 0) > 0:
                            print(f"WARNING: Waterway validation found {validation_result['total_errors']} rule violations")
                            for error in validation_result.get('errors', [])[:5]:  # Show first 5
                                print(f"  - {error}")
                            if validation_result['total_errors'] > 5:
                                print(f"  ... and {validation_result['total_errors'] - 5} more violations")
                        else:
                            print("Waterway validation passed - all rules correctly implemented")
                        
                        # Use enhanced results if available
                        if 'edge_aligned_segments' in gpu_results:
                            self._load_gpu_waterway_results(gpu_results['edge_aligned_segments'])
                    except Exception as e:
                        print(f"Enhanced waterway processing failed: {e}")
                        print("Falling back to standard waterway processing...")
                    
                    # Load traditional waterways for compatibility
                    for _, waterway in waterways_gdf.iterrows():
                        water_item = WaterWayItem(
                            waterway.geometry,
                            waterway.get('name', 'Unnamed Waterway'), 
                            waterway.get('type', 'unknown')
                        )
                        self.water_items.append(water_item)
                    
                    # Process waterways for edge alignment if hex grid exists (CPU fallback)
                    if self.hex_grid and len(self.edge_water_items) == 0:
                        print("Creating edge-aligned waterways (CPU method)...")
                        self._load_edge_aligned_waterways(waterways_gdf)
                    
                    print(f"Successfully loaded {len(waterways_gdf)} waterways for display")
                    print(f"   Created {len(self.edge_water_items)} edge-aligned waterway segments")
                else:
                    print("Waterways shapefile not found")
                    
            except Exception as e:
                print(f"❌ Error loading vector features: {e}")
                print("   Continuing without vector features...")
            
            finally:
                # Clean up environment variables
                if 'CPL_LOG' in os.environ:
                    del os.environ['CPL_LOG']
                if 'GDAL_DISABLE_READDIR_ON_OPEN' in os.environ:
                    del os.environ['GDAL_DISABLE_READDIR_ON_OPEN']

    def _load_gpu_waterway_results(self, gpu_segments):
        """Load GPU-processed waterway segments into the map view."""
        from ui.waterway_items import consolidate_waterway_segments, ConsolidatedWaterwayItem
        
        print(f"Loading {len(gpu_segments)} processed waterway segments...")
        
        # Convert GPU results to the format expected by consolidation
        edge_segments = []
        for gpu_seg in gpu_segments:
            edge_segment = {
                'start_point': gpu_seg['start_point'],
                'end_point': gpu_seg['end_point'],
                'name': gpu_seg['name'],
                'waterway_type': gpu_seg['waterway_type'],
                'gpu_processed': True
            }
            edge_segments.append(edge_segment)
        
        # Consolidate GPU segments by waterway name
        waterway_groups = consolidate_waterway_segments(edge_segments)
        
        print(f"Consolidated {len(edge_segments)} processed segments into {len(waterway_groups)} waterways")
        
        # Create consolidated waterway items from GPU results
        for group_key, waterway_data in waterway_groups.items():
            consolidated_item = ConsolidatedWaterwayItem(
                waterway_data['name'],
                waterway_data['type'], 
                waterway_data['segments']
            )
            self.scene.addItem(consolidated_item)
            self.edge_water_items.append(consolidated_item)
        
        print(f"Enhanced waterway loading complete - {len(waterway_groups)} consolidated items created")

    def _load_edge_aligned_waterways(self, waterways_gdf):
        """Load waterways and convert them to edge-aligned segments."""
        from core.terrain import TerrainAnalyzer
        
        if not self.hex_grid:
            print("No hex grid available for edge alignment")
            return
        
        # Convert GeoDataFrame to list format expected by terrain analyzer
        waterways_data = []
        for _, waterway in waterways_gdf.iterrows():
            waterway_dict = {
                'geometry': waterway.geometry,
                'properties': {
                    'name': waterway.get('name', 'Unnamed Waterway'),
                    'fclass': waterway.get('fclass', waterway.get('type', 'unknown')),
                    'type': waterway.get('type', 'unknown'),
                    'width': waterway.get('width', 0.0)
                }
            }
            waterways_data.append(waterway_dict)
        
        # Use terrain analyzer to process edge-aligned waterways
        terrain_analyzer = TerrainAnalyzer("data")  # Provide data directory
        edge_segments = terrain_analyzer.process_edge_aligned_waterways(
            self.hex_grid, waterways_data
        )
        
        # Import the consolidated waterway system
        from .waterway_items import ConsolidatedWaterwayItem, consolidate_waterway_segments
        
        print(f"Creating consolidated waterways from {len(edge_segments)} segments...")
        
        # Group segments by waterway name
        waterway_groups = consolidate_waterway_segments(edge_segments)
        
        print(f"Consolidated {len(edge_segments)} segments into {len(waterway_groups)} waterways")
        
        # Create ConsolidatedWaterwayItem objects for each waterway
        for waterway_key, waterway_data in waterway_groups.items():
            consolidated_item = ConsolidatedWaterwayItem(
                waterway_data['name'],
                waterway_data['type'],
                waterway_data['segments']
            )
            if self.show_waterways:
                self.scene.addItem(consolidated_item)
            self.edge_water_items.append(consolidated_item)
        
        print(f"   Created {len(self.edge_water_items)} consolidated waterway items (reduced from {len(edge_segments)} segments)")
    
    def _filter_roads(self, roads_gdf):
        """Filter roads and create connections between ALL hex cells that roads pass through."""
        if not self.hex_grid:
            # If no hex grid, return all roads
            return [{'geometry': row.geometry, 'name': row.get('name', 'Unnamed Road'), 'type': row.get('type', 'unknown')} 
                    for _, row in roads_gdf.iterrows()]
        
        filtered_roads = []
        connected_pairs = set()  # Track connected cell pairs
        excluded_count = 0
        
        for _, road in roads_gdf.iterrows():
            try:
                # Get road coordinates
                if hasattr(road.geometry, 'coords'):
                    coords = list(road.geometry.coords)
                    if len(coords) < 2:
                        excluded_count += 1
                        continue  # Skip invalid roads
                    
                    # Process the entire road path, not just start/end points
                    road_hex_cells = []
                    
                    # Sample points along the road geometry to capture all cells it passes through
                    for i in range(len(coords) - 1):
                        start_x, start_y = coords[i]
                        end_x, end_y = coords[i + 1]
                        
                        # Convert segment endpoints to hex coordinates
                        start_hex = self._world_to_hex(start_x, start_y)
                        end_hex = self._world_to_hex(end_x, end_y)
                        
                        # Get line of hexes between segment endpoints
                        hex_line = self.hex_grid.get_line_of_hexes(
                            start_hex[0], start_hex[1], end_hex[0], end_hex[1]
                        )
                        
                        # Add all hexes in this segment to the road path
                        for hex_coord in hex_line:
                            if hex_coord not in road_hex_cells:
                                road_hex_cells.append(hex_coord)
                    
                    # Create connections between adjacent hexes in the road path
                    for i in range(len(road_hex_cells) - 1):
                        current_hex = road_hex_cells[i]
                        next_hex = road_hex_cells[i + 1]
                        
                        # Create normalized pair (smaller first to avoid duplicates)
                        cell_pair = tuple(sorted([current_hex, next_hex]))
                        
                        # Skip if this connection already exists
                        if cell_pair in connected_pairs:
                            continue
                        
                        # Get hex cell centers
                        start_center = self._hex_to_world_center(current_hex[0], current_hex[1])
                        end_center = self._hex_to_world_center(next_hex[0], next_hex[1])
                        
                        if start_center and end_center:
                            # Create a line geometry connecting the hex centers
                            from shapely.geometry import LineString
                            line_geometry = LineString([start_center, end_center])
                            
                            # Add this road segment with comprehensive metadata
                            connected_pairs.add(cell_pair)
                            filtered_roads.append({
                                'geometry': line_geometry,
                                'name': road.get('name', 'Unnamed Road'),
                                'type': road.get('fclass', 'unknown'),  # Functional class (motorway, primary, etc.)
                                'ref': road.get('ref', ''),  # Road reference number
                                'oneway': road.get('oneway', 'F') == 'T',  # Convert to boolean
                                'maxspeed': road.get('maxspeed', 0),  # Speed limit
                                'bridge': road.get('bridge', 'F') == 'T',  # Is bridge
                                'tunnel': road.get('tunnel', 'F') == 'T',  # Is tunnel
                                'layer': road.get('layer', 0),  # Road layer (for overpasses)
                                'osm_id': road.get('osm_id', ''),  # OpenStreetMap ID
                                'start_hex': current_hex,
                                'end_hex': next_hex
                            })
                    
                    # If no valid hex path was found, count as excluded
                    if len(road_hex_cells) < 2:
                        excluded_count += 1
                    
            except Exception as e:
                logging.warning(f"Error processing road '{road.get('name', 'Unnamed')}': {e}")
                excluded_count += 1
                continue
        
        if excluded_count > 0:
            print(f"   Excluded {excluded_count} roads (short/duplicate/invalid)")
        
        return filtered_roads
    
    def _world_to_hex(self, x, y):
        """Convert world coordinates to hex cell coordinates (q, r)."""
        if not self.hex_grid:
            return (0, 0)
        
        try:
            # Get hex size and center offset from hex grid
            hex_size = self.hex_grid.hex_size
            center_offset = self.hex_grid.center_offset
            
            # Adjust coordinates by center offset
            adjusted_x = x - center_offset[0]
            adjusted_y = y - center_offset[1]
            
            # Convert to axial coordinates (q, r)
            # This is the standard pointy-top hex conversion
            q = (2.0/3.0 * adjusted_x) / hex_size
            r = (-1.0/3.0 * adjusted_x + 1.0/3.0 * np.sqrt(3) * adjusted_y) / hex_size
            
            # Round to nearest hex
            return self._hex_round(q, r)
            
        except Exception as e:
            print(f"Error converting coordinates ({x}, {y}) to hex: {e}")
            return (0, 0)
    
    def _hex_round(self, q, r):
        """Round fractional hex coordinates to nearest hex center."""
        # Convert to cube coordinates
        s = -q - r
        
        # Round all coordinates
        rq = round(q)
        rr = round(r)
        rs = round(s)
        
        # Find which coordinate changed the most
        q_diff = abs(rq - q)
        r_diff = abs(rr - r)
        s_diff = abs(rs - s)
        
        if q_diff > r_diff and q_diff > s_diff:
            rq = -rr - rs
        elif r_diff > s_diff:
            rr = -rq - rs
        else:
            rs = -rq - rr
        
        return (int(rq), int(rr))
    
    def _hex_to_world_center(self, q, r):
        """Convert hex axial coordinates to world coordinates (hex center)."""
        if not self.hex_grid:
            return None
        
        try:
            # Get hex size and center offset from hex grid
            hex_size = self.hex_grid.hex_size
            center_offset = self.hex_grid.center_offset
            
            # Convert axial to world coordinates
            x = hex_size * (3.0/2.0 * q) + center_offset[0]
            y = hex_size * (np.sqrt(3)/2.0 * q + np.sqrt(3) * r) + center_offset[1]
            
            return (x, y)
            
        except Exception as e:
            print(f"Error converting hex ({q}, {r}) to world coordinates: {e}")
            return None
    
    def _fit_scene_to_content(self):
        """Fit scene rectangle to content."""
        if self.hex_items:
            self.scene.setSceneRect(self.scene.itemsBoundingRect())
    
    def set_display_mode(self, mode: DisplayMode):
        """Set display mode for hex cells."""
        self.display_mode = mode
        
        # Update all hex items
        for hex_item in self.hex_items.values():
            hex_item.set_display_mode(mode)
    
    def add_unit(self, unit: Unit):
        """Add a unit to the map view."""
        if unit.id in self.unit_items:
            return  # Unit already exists
        
        # Get hex size for proper unit scaling
        config = get_config()
        hex_size = self.hex_grid.hex_size if self.hex_grid else config.simulation.hex_size
        unit_item = UnitItem(unit, hex_size)
        self.scene.addItem(unit_item)
        self.unit_items[unit.id] = unit_item
        
        # Update hex display when unit is added
        if unit.position:
            hex_key = (unit.position.q, unit.position.r)
            if hex_key in self.hex_items:
                # Force update the hex appearance
                self.hex_items[hex_key]._update_appearance()
        
        # Center the view on the new unit to ensure it's visible
        if unit.position:
            self.centerOn(unit_item.pos())
    
    def remove_unit(self, unit_id: str):
        """Remove a unit from the map view."""
        if unit_id in self.unit_items:
            unit_item = self.unit_items[unit_id]
            unit = unit_item.unit
            
            # Update hex display if in control mode
            if self.display_mode == DisplayMode.CONTROL and unit.position:
                hex_key = (unit.position.q, unit.position.r)
                if hex_key in self.hex_items:
                    self.hex_items[hex_key]._update_appearance()
            
            self.scene.removeItem(unit_item)
            del self.unit_items[unit_id]
    
    def update_unit_position(self, unit_id: str, position: Tuple[int, int]):
        """Update unit position on the map."""
        if unit_id in self.unit_items:
            unit_item = self.unit_items[unit_id]
            
            # Update hex display for old and new positions if in control mode
            if self.display_mode == DisplayMode.CONTROL:
                # Update old position
                old_unit = unit_item.unit
                if old_unit.position:
                    old_hex_key = (old_unit.position.q, old_unit.position.r)
                    if old_hex_key in self.hex_items:
                        self.hex_items[old_hex_key]._update_appearance()
                
                # Update new position
                new_hex_key = position
                if new_hex_key in self.hex_items:
                    self.hex_items[new_hex_key]._update_appearance()
            
            unit_item.update_from_unit()
    
    def clear_units(self):
        """Clear all units from the map view."""
        for unit_item in self.unit_items.values():
            self.scene.removeItem(unit_item)
        self.unit_items.clear()
        
        # Also clear movement arrows
        for arrow in self.movement_arrows.values():
            self.scene.removeItem(arrow)
        self.movement_arrows.clear()
    
    def update_display(self):
        """Update the entire display."""
        # Update all unit items
        for unit_item in self.unit_items.values():
            unit_item.update_from_unit()
        
        # Update movement arrows
        self._update_movement_arrows()
        
        # Update scene
        self.scene.update()
    
    def _update_movement_arrows(self):
        """Update movement arrows based on current movement orders."""
        if not self.simulation or not self.hex_grid:
            return
            
        # Get current movement orders from simulation (it's a list of MovementOrder objects)
        movement_orders = getattr(self.simulation, 'movement_orders', [])
        
        # Create a set of unit IDs that currently have movement orders
        units_with_orders = set()
        for order in movement_orders:
            units_with_orders.add(order.unit_id)
        
        # Remove arrows for units that no longer have movement orders
        units_to_remove = []
        for unit_id in self.movement_arrows:
            if unit_id not in units_with_orders:
                units_to_remove.append(unit_id)
        
        for unit_id in units_to_remove:
            arrow = self.movement_arrows[unit_id]
            self.scene.removeItem(arrow)
            del self.movement_arrows[unit_id]
        
        # Add or update arrows for units with movement orders
        for order in movement_orders:
            unit_id = order.unit_id
            path = order.path
            
            # Get unit for color and position
            unit = self.simulation.units.get(unit_id)
            if not unit:
                continue
                
            # Handle case where path is not calculated yet (immediate arrow display)
            if not path:
                # Create simple arrow from current position to target
                if unit.position:
                    start_hex = (unit.position.q, unit.position.r)
                else:
                    continue
                end_hex = (order.target_q, order.target_r)
            elif len(path) < 2:
                continue
            else:
                # Use calculated path
                if unit.position:
                    start_hex = (unit.position.q, unit.position.r)  # Unit's current position
                else:
                    # Fallback to path start if unit.position is None
                    start_hex = path[0]
                end_hex = path[-1]   # Final destination
            
            start_screen = self._hex_to_screen(start_hex[0], start_hex[1])
            end_screen = self._hex_to_screen(end_hex[0], end_hex[1])
            
            # Get unit color based on side
            unit_color = QColor(0, 0, 255) if unit.side == UnitSide.BLUE else QColor(255, 0, 0)
            
            # Remove existing arrow if present
            if unit_id in self.movement_arrows:
                self.scene.removeItem(self.movement_arrows[unit_id])
            
            # Create new arrow
            arrow = MovementArrow(start_screen, end_screen, unit_color)
            self.movement_arrows[unit_id] = arrow
            self.scene.addItem(arrow)
    
    def _hex_to_screen(self, q: int, r: int) -> Tuple[float, float]:
        """Convert hex coordinates to screen coordinates."""
        if (q, r) in self.hex_items:
            hex_item = self.hex_items[(q, r)]
            center = hex_item.boundingRect().center()
            return (hex_item.x() + center.x(), hex_item.y() + center.y())
        else:
            # Fallback calculation if hex item not found
            config = get_config()
            hex_size = self.hex_grid.hex_size if self.hex_grid else config.simulation.hex_size
            x = hex_size * (3/2 * q)
            y = hex_size * (math.sqrt(3)/2 * (q + 2*r))
            return (x, y)
    
    def zoom_in(self):
        """Zoom in the view with limits."""
        zoom_step = 1.2
        proposed_zoom = self.current_zoom_factor * zoom_step
        
        if proposed_zoom <= self.max_zoom_factor:
            self.scale(zoom_step, zoom_step)
            self.current_zoom_factor = proposed_zoom
    
    def zoom_out(self):
        """Zoom out the view with limits."""
        zoom_step = 0.8
        proposed_zoom = self.current_zoom_factor * zoom_step
        
        if proposed_zoom >= self.min_zoom_factor:
            self.scale(zoom_step, zoom_step)
            self.current_zoom_factor = proposed_zoom
    
    def fit_in_view(self):
        """Fit the entire scene in view."""
        if self.hex_items:
            # Store current transform
            old_transform = self.transform()
            
            # Fit to view
            self.fitInView(self.scene.itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)
            
            # Calculate what zoom factor this results in
            new_transform = self.transform()
            scale_factor = new_transform.m11()  # Get horizontal scale factor
            
            # Check if the new scale is within limits
            if scale_factor < self.min_zoom_factor:
                # If too zoomed out, set to minimum zoom
                self.setTransform(old_transform)
                self.resetTransform()
                # Apply initial flip transformation
                transform = self.transform()
                transform.scale(1, -1)  # Flip Y-axis
                transform.scale(self.min_zoom_factor, self.min_zoom_factor)
                self.setTransform(transform)
                self.current_zoom_factor = self.min_zoom_factor
            elif scale_factor > self.max_zoom_factor:
                # If too zoomed in, set to maximum zoom
                self.setTransform(old_transform)
                self.resetTransform()
                # Apply initial flip transformation
                transform = self.transform()
                transform.scale(1, -1)  # Flip Y-axis
                transform.scale(self.max_zoom_factor, self.max_zoom_factor)
                self.setTransform(transform)
                self.current_zoom_factor = self.max_zoom_factor
            else:
                # Within limits, update current zoom factor
                self.current_zoom_factor = scale_factor
    
    def reset_zoom(self):
        """Reset zoom to 1.0 (100%)."""
        # Calculate scale factor needed to get to 1.0
        target_zoom = 1.0
        if target_zoom < self.min_zoom_factor:
            target_zoom = self.min_zoom_factor
        elif target_zoom > self.max_zoom_factor:
            target_zoom = self.max_zoom_factor
            
        scale_factor = target_zoom / self.current_zoom_factor
        self.scale(scale_factor, scale_factor)
        self.current_zoom_factor = target_zoom
    
    def set_zoom_limits(self, min_zoom: float, max_zoom: float):
        """Set minimum and maximum zoom factors."""
        if min_zoom > 0 and max_zoom > min_zoom:
            self.min_zoom_factor = min_zoom
            self.max_zoom_factor = max_zoom
            
            # Ensure current zoom is within new limits
            if self.current_zoom_factor < min_zoom:
                scale_factor = min_zoom / self.current_zoom_factor
                self.scale(scale_factor, scale_factor)
                self.current_zoom_factor = min_zoom
            elif self.current_zoom_factor > max_zoom:
                scale_factor = max_zoom / self.current_zoom_factor
                self.scale(scale_factor, scale_factor)
                self.current_zoom_factor = max_zoom
    
    def get_current_zoom(self) -> float:
        """Get current zoom factor."""
        return self.current_zoom_factor
    
    def get_zoom_limits(self) -> Tuple[float, float]:
        """Get current zoom limits as (min_zoom, max_zoom)."""
        return (self.min_zoom_factor, self.max_zoom_factor)
    
    def reset_view(self):
        """Reset view transformation to default (flipped) state."""
        self.resetTransform()
        # Apply default flip transformation
        self.is_flipped = True
        transform = self.transform()
        transform.scale(1, -1)  # Flip Y-axis
        self.setTransform(transform)
        self.fit_in_view()
    
    def _get_hex_at_position(self, pos: QPointF) -> Optional[Tuple[int, int]]:
        """Get hex coordinates at scene position."""
        if not self.hex_grid:
            return None
        
        # Find hex cell at position
        hex_cell = self.hex_grid.get_cell_at_position(pos.x(), pos.y())
        if hex_cell:
            return (hex_cell.q, hex_cell.r)
        
        return None
    
    def _get_unit_at_position(self, pos: QPointF) -> Optional[str]:
        """Get unit ID at scene position."""
        items = self.scene.items(pos)
        
        for item in items:
            if isinstance(item, UnitItem):
                return item.unit.id
        
        return None
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Convert to scene coordinates
            scene_pos = self.mapToScene(event.pos())
            
            # Check for unit click first
            unit_id = self._get_unit_at_position(scene_pos)
            if unit_id:
                self._handle_unit_click(unit_id)
                return
            
            # Check for hex click
            hex_coords = self._get_hex_at_position(scene_pos)
            if hex_coords:
                self._handle_hex_click(hex_coords)
        
        super().mousePressEvent(event)
    
    def _handle_hex_click(self, coords: Tuple[int, int]):
        """Handle hex cell click."""
        q, r = coords
        
        # If in movement mode, try to move selected unit
        if self.movement_mode and self.selected_unit_for_movement:
            self.unit_move_requested.emit(self.selected_unit_for_movement, q, r)
            self._exit_movement_mode()
            return
        
        # Update selection
        self._update_hex_selection(coords)
        
        # Emit signal
        self.hex_clicked.emit(q, r)
    
    def _handle_unit_click(self, unit_id: str):
        """Handle unit click."""
        # Update selection
        self._update_unit_selection(unit_id)
        
        # Emit signal
        self.unit_clicked.emit(unit_id)
    
    def _update_hex_selection(self, coords: Optional[Tuple[int, int]]):
        """Update hex selection visual state."""
        # Clear previous selection
        if self.selected_hex and self.selected_hex in self.hex_items:
            self.hex_items[self.selected_hex].set_selected(False)
        
        # Set new selection
        self.selected_hex = coords
        if coords and coords in self.hex_items:
            self.hex_items[coords].set_selected(True)
    
    def _update_unit_selection(self, unit_id: Optional[str]):
        """Update unit selection visual state."""
        # Clear previous selection
        if self.selected_unit and self.selected_unit in self.unit_items:
            try:
                self.unit_items[self.selected_unit].set_selected(False)
            except (RuntimeError, AttributeError):
                # Unit item has been deleted, remove from dict
                if self.selected_unit in self.unit_items:
                    del self.unit_items[self.selected_unit]
        
        # Set new selection
        self.selected_unit = unit_id
        if unit_id and unit_id in self.unit_items:
            try:
                self.unit_items[unit_id].set_selected(True)
            except (RuntimeError, AttributeError):
                # Unit item has been deleted, remove from dict
                if unit_id in self.unit_items:
                    del self.unit_items[unit_id]
    
    def enter_movement_mode(self, unit_id: str):
        """Enter movement mode for a unit."""
        if unit_id not in self.unit_items:
            return
        
        self.movement_mode = True
        self.selected_unit_for_movement = unit_id
        
        # Highlight valid movement hexes
        self._highlight_valid_movement_hexes(unit_id)
    
    def _exit_movement_mode(self):
        """Exit movement mode."""
        self.movement_mode = False
        self.selected_unit_for_movement = None
        
        # Clear movement highlighting
        self._clear_movement_highlighting()
    
    def _highlight_valid_movement_hexes(self, unit_id: str):
        """Highlight hexes where the unit can move."""
        if not self.simulation or unit_id not in self.simulation.units:
            return
        
        unit = self.simulation.units[unit_id]
        if not unit.position:
            return
        
        # Check all hexes for movement validity
        for coords, hex_item in self.hex_items.items():
            q, r = coords
            target_cell = self.hex_grid.get_cell(q, r)
            
            if target_cell and unit.can_move_to(target_cell):
                # Check if unit has enough movement points
                movement_cost = unit.movement_cost_to(target_cell)
                if movement_cost <= unit.movement_points:
                    hex_item.set_valid_move(True)
    
    def _clear_movement_highlighting(self):
        """Clear all movement highlighting."""
        for hex_item in self.hex_items.values():
            hex_item.set_valid_move(False)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move events for edge scrolling."""
        if not self.edge_scroll_enabled:
            super().mouseMoveEvent(event)
            return
            
        # Get mouse position relative to widget
        mouse_pos = event.pos()
        widget_rect = self.rect()
        
        # Calculate edge scroll direction
        scroll_x = 0.0
        scroll_y = 0.0
        
        # Check horizontal edges
        if mouse_pos.x() <= self.edge_scroll_margin:
            # Left edge - scroll left
            scroll_x = -self.edge_scroll_speed
        elif mouse_pos.x() >= widget_rect.width() - self.edge_scroll_margin:
            # Right edge - scroll right
            scroll_x = self.edge_scroll_speed
            
        # Check vertical edges
        if mouse_pos.y() <= self.edge_scroll_margin:
            # Top edge - scroll up
            scroll_y = -self.edge_scroll_speed
        elif mouse_pos.y() >= widget_rect.height() - self.edge_scroll_margin:
            # Bottom edge - scroll down
            scroll_y = self.edge_scroll_speed
        
        # Update scroll direction
        self.edge_scroll_direction = QPointF(scroll_x, scroll_y)
        
        # Start or stop timer based on whether we're scrolling
        if scroll_x != 0 or scroll_y != 0:
            if not self.edge_scroll_timer.isActive():
                self.edge_scroll_timer.start(16)  # ~60 FPS for smooth scrolling
        else:
            self.edge_scroll_timer.stop()
        
        # Continue with normal mouse move handling
        super().mouseMoveEvent(event)
    
    def _perform_edge_scroll(self):
        """Perform the actual edge scrolling."""
        if self.edge_scroll_direction.x() == 0 and self.edge_scroll_direction.y() == 0:
            return
            
        # Get current scroll bar values
        h_scroll = self.horizontalScrollBar()
        v_scroll = self.verticalScrollBar()
        
        # Check if scroll bars exist
        if not h_scroll or not v_scroll:
            return
        
        # Apply scrolling
        new_h_value = h_scroll.value() + int(self.edge_scroll_direction.x())
        new_v_value = v_scroll.value() + int(self.edge_scroll_direction.y())
        
        # Clamp to valid ranges
        new_h_value = max(h_scroll.minimum(), min(h_scroll.maximum(), new_h_value))
        new_v_value = max(v_scroll.minimum(), min(v_scroll.maximum(), new_v_value))
        
        # Set new scroll positions
        h_scroll.setValue(new_h_value)
        v_scroll.setValue(new_v_value)
    
    def leaveEvent(self, event):
        """Handle mouse leave events to stop edge scrolling."""
        self.edge_scroll_timer.stop()
        self.edge_scroll_direction = QPointF(0, 0)
        super().leaveEvent(event)
    
    def set_edge_scroll_enabled(self, enabled: bool):
        """Enable or disable edge scrolling."""
        self.edge_scroll_enabled = enabled
        if not enabled:
            self.edge_scroll_timer.stop()
            self.edge_scroll_direction = QPointF(0, 0)
    
    def set_edge_scroll_speed(self, speed: float):
        """Set edge scrolling speed."""
        self.edge_scroll_speed = speed
    
    def set_edge_scroll_margin(self, margin: int):
        """Set edge scrolling margin in pixels."""
        self.edge_scroll_margin = margin
    
    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel events for zooming with limits."""
        # Zoom factor per scroll step
        zoom_step = 1.15
        
        # Calculate proposed zoom factor
        if event.angleDelta().y() > 0:
            # Zoom in
            proposed_zoom = self.current_zoom_factor * zoom_step
        else:
            # Zoom out
            proposed_zoom = self.current_zoom_factor / zoom_step
        
        # Apply zoom limits
        if proposed_zoom < self.min_zoom_factor:
            proposed_zoom = self.min_zoom_factor
        elif proposed_zoom > self.max_zoom_factor:
            proposed_zoom = self.max_zoom_factor
        
        # Calculate actual scale factor to apply
        if proposed_zoom == self.current_zoom_factor:
            # Already at limit, don't zoom
            return
            
        actual_scale_factor = proposed_zoom / self.current_zoom_factor
        
        # Apply the zoom
        self.scale(actual_scale_factor, actual_scale_factor)
        
        # Update current zoom factor
        self.current_zoom_factor = proposed_zoom
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            # Clear selections and exit modes
            self._update_hex_selection(None)
            self._update_unit_selection(None)
            self._exit_movement_mode()
        
        elif event.key() == Qt.Key.Key_M and self.selected_unit:
            # Enter movement mode for selected unit
            self.enter_movement_mode(self.selected_unit)
        
        super().keyPressEvent(event)
    
    def _show_context_menu(self, position):
        """Show context menu."""
        # Convert to scene coordinates
        scene_pos = self.mapToScene(position)
        
        # Check what's under the cursor
        unit_id = self._get_unit_at_position(scene_pos)
        hex_coords = self._get_hex_at_position(scene_pos)
        
        # Create context menu
        menu = QMenu(self)
        
        if unit_id:
            # Unit context menu
            menu.addAction(f"Select Unit {unit_id}")
            menu.addAction("Move Unit").triggered.connect(
                lambda: self.enter_movement_mode(unit_id)
            )
            menu.addAction("Unit Info")
        
        elif hex_coords:
            # Hex context menu
            q, r = hex_coords
            menu.addAction(f"Hex ({q}, {r})")
            menu.addAction("Hex Info")
            
            if self.selected_unit:
                menu.addAction("Move Selected Unit Here").triggered.connect(
                    lambda: self.unit_move_requested.emit(self.selected_unit, q, r)
                )
        
        # Show menu if it has actions
        if menu.actions():
            menu.exec(self.mapToGlobal(position))
    
    def _update_animations(self):
        """Update any animations."""
        # This could be used for unit movement animations,
        # blinking selections, etc.
        pass
    
    def set_show_grid(self, show: bool):
        """Set whether to show grid lines."""
        self.show_grid = show
        # Update visual appearance
        
    def set_show_coordinates(self, show: bool):
        """Set whether to show hex coordinates."""
        self.show_coordinates = show
        # Update visual appearance
    
    def set_show_roads(self, show: bool):
        """Toggle visibility of roads."""
        print(f"Setting road visibility to: {show}")
        self.show_roads = show
        road_count = 0
        for road_item in self.road_items:
            road_item.setVisible(show)
            road_count += 1
        print(f"Updated visibility for {road_count} road items")
    
    def set_show_waterways(self, show: bool):
        """Toggle visibility of waterways."""
        print(f"Setting waterway visibility to: {show}")
        self.show_waterways = show
        water_count = 0
        # Toggle traditional waterways
        for water_item in self.water_items:
            water_item.setVisible(show)
            water_count += 1
        # Toggle edge-aligned waterways  
        for edge_water_item in self.edge_water_items:
            edge_water_item.setVisible(show)
            water_count += 1
        print(f"Updated visibility for {water_count} waterway items")
    
    def center_on_roads(self):
        """Center the view on the road network."""
        if self.road_items:
            # Calculate bounding box of all roads
            all_lines = []
            for road_item in self.road_items:
                line = road_item.line()
                all_lines.extend([line.p1(), line.p2()])
            
            if all_lines:
                min_x = min(p.x() for p in all_lines)
                max_x = max(p.x() for p in all_lines)
                min_y = min(p.y() for p in all_lines)
                max_y = max(p.y() for p in all_lines)
                
                # Create bounding rectangle with some margin
                margin = 500  # 500m margin
                road_rect = QRectF(min_x - margin, min_y - margin, 
                                 max_x - min_x + 2*margin, max_y - min_y + 2*margin)
                
                # Fit view to road area
                self.fitInView(road_rect, Qt.AspectRatioMode.KeepAspectRatio)
                
                print(f"Centered view on {len(self.road_items)} roads")
    
    def select_road(self, road_item: RoadItem):
        """Select a road and highlight all its segments."""
        # Clear previous selection
        self.clear_road_selection()
        
        # Get the road identifier
        road_id = road_item.get_road_identifier()
        
        # Find all segments of this road and highlight them
        if road_id in self.road_groups:
            self.selected_road_segments = self.road_groups[road_id]
            for segment in self.selected_road_segments:
                segment.highlight_road(True)
        
        # Get road metadata and send to sidebar
        if self.selected_road_segments:
            # Aggregate metadata from all segments
            road_metadata = self._aggregate_road_metadata(self.selected_road_segments)
            self._display_road_metadata(road_metadata)
            # Emit signal for the main window to handle
            self.road_selected.emit(road_metadata)
        
        print(f"Selected road: {road_id} ({len(self.selected_road_segments)} segments)")
    
    def clear_road_selection(self):
        """Clear the current road selection."""
        # Clean up any deleted objects first
        self._cleanup_deleted_items()
        
        # Use list() to create a copy since we'll be modifying during iteration
        segments_to_clear = list(self.selected_road_segments)
        for segment in segments_to_clear:
            try:
                segment.highlight_road(False)
            except (RuntimeError, AttributeError):
                # Object has been deleted or is invalid, remove from selection
                if segment in self.selected_road_segments:
                    self.selected_road_segments.remove(segment)
        self.selected_road_segments.clear()
    
    def _aggregate_road_metadata(self, segments: List[RoadItem]) -> dict:
        """Aggregate metadata from multiple road segments."""
        if not segments:
            return {}
        
        # Use first segment as base
        first_segment = segments[0]
        metadata = {
            'name': first_segment.road_name,
            'type': first_segment.road_type,
            'ref': first_segment.road_ref,
            'oneway': first_segment.road_oneway,
            'maxspeed': first_segment.road_maxspeed,
            'segment_count': len(segments),
            'total_length': 0.0,  # Could calculate if needed
            'special_features': set()
        }
        
        # Aggregate special features from all segments
        for segment in segments:
            if segment.road_bridge:
                metadata['special_features'].add('bridge')
            if segment.road_tunnel:
                metadata['special_features'].add('tunnel')
            if segment.road_layer != 0:
                metadata['special_features'].add(f'layer_{segment.road_layer}')
        
        # Convert set to list for easier handling
        metadata['special_features'] = list(metadata['special_features'])
        
        return metadata
    
    def _display_road_metadata(self, metadata: dict):
        """Display road metadata in the sidebar."""
        # Get the main window to access the sidebar
        main_window = self.window()
        if hasattr(main_window, 'side_panel'):
            main_window.side_panel.display_road_info(metadata)
        
        # Also print to console for debugging
        print("Road Metadata:")
        print(f"  Name: {metadata.get('name', 'Unnamed')}")
        print(f"  Reference: {metadata.get('ref', 'None')}")
        print(f"  Type: {metadata.get('type', 'unknown')}")
        print(f"  Segments: {metadata.get('segment_count', 0)}")
        if metadata.get('maxspeed', 0) > 0:
            print(f"  Speed Limit: {metadata['maxspeed']} km/h")
        if metadata.get('oneway'):
            print("  One-way road")
        if metadata.get('special_features'):
            print(f"  Features: {', '.join(metadata['special_features'])}")
    
    def highlight_waterway(self, waterway_name: str, highlight_on: bool):
        """Highlight all segments of a specific waterway."""
        highlighted_count = 0
        
        # Highlight consolidated waterway items 
        for consolidated_item in self.edge_water_items:
            # Check if this is a ConsolidatedWaterwayItem
            if hasattr(consolidated_item, 'waterway_name'):
                item_name = consolidated_item.waterway_name
            else:
                # Fallback for legacy EdgeWaterWayItem
                item_name = getattr(consolidated_item, 'water_name', '')
            
            if item_name == waterway_name:
                try:
                    if highlight_on:
                        consolidated_item.highlight_waterway()
                    else:
                        consolidated_item.restore_normal_style()
                    highlighted_count += 1
                except (RuntimeError, AttributeError):
                    # Object has been deleted, ignore
                    pass
        
        # Also highlight traditional waterway items if they exist
        for water_item in self.water_items:
            if water_item.water_name == waterway_name:
                try:
                    if highlight_on:
                        water_item.highlight_waterway()
                    else:
                        water_item.restore_normal_style()
                    highlighted_count += 1
                except (RuntimeError, AttributeError):
                    # Object has been deleted, ignore
                    pass
        
        if highlight_on:
            print(f"Highlighted {highlighted_count} waterway(s) named '{waterway_name}'")
        else:
            print(f"Removed highlight from {highlighted_count} waterway(s) named '{waterway_name}'")
    
    def select_waterway(self, waterway_item):
        """Select a waterway and emit selection signal."""
        # Handle both consolidated and legacy waterway items
        if hasattr(waterway_item, 'waterway_name'):
            waterway_name = waterway_item.waterway_name
            waterway_type = waterway_item.waterway_type
            segment_count = getattr(waterway_item, 'segment_count', 0)
        else:
            # Legacy EdgeWaterWayItem
            waterway_name = waterway_item.water_name
            waterway_type = waterway_item.water_type
            segment_count = 1
        
        # Create waterway metadata
        waterway_metadata = {
            'name': waterway_name,
            'waterway_type': waterway_type,
            'width': getattr(waterway_item, 'water_width', 0.0),
            'segments_count': segment_count,
            'total_length': 0.0  # Could be calculated if needed
        }
        
        # Find all segments of this waterway
        waterway_segments = []
        
        # Collect segments from consolidated or traditional items
        for edge_water_item in self.edge_water_items:
            # Handle consolidated waterway items
            if hasattr(edge_water_item, 'waterway_name'):
                if edge_water_item.waterway_name == waterway_name:
                    # This is a consolidated item, get segments from it
                    segments = getattr(edge_water_item, 'segments', [])
                    waterway_segments.extend(segments)
                    
                    # Calculate total length from all segments
                    for segment in segments:
                        geom = segment.get('geometry')
                        if geom and hasattr(geom, 'length'):
                            waterway_metadata['total_length'] += geom.length
            else:
                # Handle legacy EdgeWaterWayItem
                if edge_water_item.water_name == waterway_name:
                    segment_data = edge_water_item.edge_segment
                    waterway_segments.append(segment_data)
                    
                    # Add to total length
                    geom = segment_data.get('geometry')
                    if geom and hasattr(geom, 'length'):
                        waterway_metadata['total_length'] += geom.length
        
        # Collect traditional waterway segments
        for water_item in self.water_items:
            if water_item.water_name == waterway_name:
                segment_data = {
                    'name': water_item.water_name,
                    'waterway_type': water_item.water_type,
                    'geometry': water_item.water_geometry,
                    'traditional_segment': True
                }
                waterway_segments.append(segment_data)
                
                # Add to total length
                if hasattr(water_item.water_geometry, 'length'):
                    waterway_metadata['total_length'] += water_item.water_geometry.length
        
        waterway_metadata['segments_count'] = len(waterway_segments)
        
        # Emit signal for main window to handle
        self.waterway_selected.emit(waterway_metadata, waterway_segments)
        
        print(f"Selected waterway: {waterway_name} ({len(waterway_segments)} segments, {waterway_metadata['total_length']:.1f}m total length)")
