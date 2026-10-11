"""
Side panel widget for displaying terrain and unit information, and simulation controls.
"""
from typing import Optional, Dict, Any
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, 
                            QLabel, QTabWidget, QTreeWidget, QTreeWidgetItem, 
                            QGroupBox, QComboBox, QPushButton, QProgressBar,
                            QSpinBox, QDoubleSpinBox, QCheckBox, QTextEdit,
                            QScrollArea, QFrame, QListWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QPixmap

from core.simulation import Simulation, SimulationState
from models.hexcell import HexCell
from models.unit import Unit, UnitSide, UnitType
from ui.map_view import DisplayMode
from utils.config import get_config


class WaterwayInfoWidget(QWidget):
    """Widget for displaying waterway information and highlighting segments."""
    
    waterway_highlight_requested = pyqtSignal(str, bool)  # waterway_name, highlight_on
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self.current_waterway: Optional[Dict[str, Any]] = None
        self.waterway_segments: Dict[str, list] = {}  # waterway_name -> list of segments
    
    def _setup_ui(self):
        """Setup the waterway info UI."""
        layout = QVBoxLayout(self)
        
        # Waterway name with styling
        self.name_label = QLabel("No waterway selected")
        self.name_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.name_label.setStyleSheet("QLabel { color: #2196F3; padding: 8px; background-color: #E3F2FD; border-radius: 3px; }")
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)
        
        # Highlight button
        self.highlight_btn = QPushButton("Highlight Waterway")
        self.highlight_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        self.highlight_btn.clicked.connect(self._toggle_highlight)
        self.highlight_btn.setEnabled(False)
        layout.addWidget(self.highlight_btn)
        
        # Waterway properties
        waterway_group = QGroupBox("Waterway Properties")
        waterway_layout = QFormLayout(waterway_group)
        
        self.type_label = QLabel("-")
        waterway_layout.addRow("Type:", self.type_label)
        
        self.width_label = QLabel("-")
        waterway_layout.addRow("Width:", self.width_label)
        
        self.segments_label = QLabel("-")
        waterway_layout.addRow("Segments:", self.segments_label)
        
        self.length_label = QLabel("-")
        waterway_layout.addRow("Total Length:", self.length_label)
        
        layout.addWidget(waterway_group)
        
        # Flow characteristics
        flow_group = QGroupBox("Flow Characteristics")
        flow_layout = QVBoxLayout(flow_group)
        
        self.navigable_check = QCheckBox("Navigable")
        self.navigable_check.setEnabled(False)
        flow_layout.addWidget(self.navigable_check)
        
        self.seasonal_check = QCheckBox("Seasonal")
        self.seasonal_check.setEnabled(False)
        flow_layout.addWidget(self.seasonal_check)
        
        self.artificial_check = QCheckBox("Artificial")
        self.artificial_check.setEnabled(False)
        flow_layout.addWidget(self.artificial_check)
        
        layout.addWidget(flow_group)
        
        # Tactical information
        tactical_group = QGroupBox("Tactical Information")
        tactical_layout = QFormLayout(tactical_group)
        
        self.crossing_difficulty_label = QLabel("-")
        tactical_layout.addRow("Crossing Difficulty:", self.crossing_difficulty_label)
        
        self.cover_value_label = QLabel("-")
        tactical_layout.addRow("Cover Value:", self.cover_value_label)
        
        self.movement_penalty_label = QLabel("-")
        tactical_layout.addRow("Movement Penalty:", self.movement_penalty_label)
        
        layout.addWidget(tactical_group)
        
        # Technical info
        tech_group = QGroupBox("Technical Information")
        tech_layout = QFormLayout(tech_group)
        
        self.waterway_id_label = QLabel("-")
        tech_layout.addRow("Waterway ID:", self.waterway_id_label)
        
        self.hex_cells_label = QLabel("-")
        tech_layout.addRow("Hex Cells:", self.hex_cells_label)
        
        layout.addWidget(tech_group)
        
        # Add stretch to push everything to top
        layout.addStretch()
        
        self.is_highlighted = False
    
    def _toggle_highlight(self):
        """Toggle waterway highlighting."""
        if self.current_waterway:
            waterway_name = self.current_waterway.get('name', 'Unknown Waterway')
            self.is_highlighted = not self.is_highlighted
            
            self.waterway_highlight_requested.emit(waterway_name, self.is_highlighted)
            
            if self.is_highlighted:
                self.highlight_btn.setText("Remove Highlight")
                self.highlight_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #FF5722;
                        color: white;
                        border: none;
                        padding: 8px;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #E64A19;
                    }
                """)
            else:
                self.highlight_btn.setText("Highlight Waterway")
                self.highlight_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2196F3;
                        color: white;
                        border: none;
                        padding: 8px;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #1976D2;
                    }
                """)
    
    def display_waterway_info(self, waterway_metadata: Dict[str, Any], segments: Optional[list] = None):
        """Display waterway information."""
        self.current_waterway = waterway_metadata
        
        # Update waterway name
        name = waterway_metadata.get('name', 'Unnamed Waterway')
        waterway_type = waterway_metadata.get('waterway_type', 'unknown')
        
        if name != 'Unnamed Waterway':
            display_name = f"{name}"
        else:
            display_name = f"Unnamed {waterway_type.title()}"
        
        self.name_label.setText(display_name)
        
        # Update properties
        self.type_label.setText(waterway_type.title())
        
        width = waterway_metadata.get('width', 0.0)
        if width > 0:
            self.width_label.setText(f"{width:.1f}m")
        else:
            self.width_label.setText("Unknown")
        
        # Segment information
        if segments:
            self.waterway_segments[name] = segments
            self.segments_label.setText(str(len(segments)))
            
            # Calculate total length
            total_length = 0.0
            hex_cells = set()
            for segment in segments:
                geom = segment.get('geometry')
                if geom:
                    total_length += geom.length
                hex_cells.add((segment.get('hex_q', 0), segment.get('hex_r', 0)))
            
            self.length_label.setText(f"{total_length:.1f}m")
            self.hex_cells_label.setText(str(len(hex_cells)))
        else:
            self.segments_label.setText("-")
            self.length_label.setText("-")
            self.hex_cells_label.setText("-")
        
        # Flow characteristics (based on waterway type)
        if waterway_type in ['river', 'canal']:
            self.navigable_check.setChecked(True)
        else:
            self.navigable_check.setChecked(False)
        
        if waterway_type in ['stream', 'creek']:
            self.seasonal_check.setChecked(True)
        else:
            self.seasonal_check.setChecked(False)
        
        if waterway_type in ['canal', 'ditch']:
            self.artificial_check.setChecked(True)
        else:
            self.artificial_check.setChecked(False)
        
        # Tactical information (based on type and width)
        if waterway_type == 'river' or width > 10:
            self.crossing_difficulty_label.setText("High")
            self.cover_value_label.setText("Medium")
            self.movement_penalty_label.setText("Major")
        elif waterway_type in ['stream', 'creek'] or width > 2:
            self.crossing_difficulty_label.setText("Medium")
            self.cover_value_label.setText("Low")
            self.movement_penalty_label.setText("Minor")
        else:
            self.crossing_difficulty_label.setText("Low")
            self.cover_value_label.setText("Minimal")
            self.movement_penalty_label.setText("Minimal")
        
        # Technical info
        waterway_id = waterway_metadata.get('original_waterway_id', 'Unknown')
        self.waterway_id_label.setText(str(waterway_id))
        
        # Enable highlight button
        self.highlight_btn.setEnabled(True)
        
        # Reset highlight state
        self.is_highlighted = False
        self.highlight_btn.setText("Highlight Waterway")
    
    def clear_selection(self):
        """Clear waterway selection."""
        self.current_waterway = None
        self.name_label.setText("No waterway selected")
        self.type_label.setText("-")
        self.width_label.setText("-")
        self.segments_label.setText("-")
        self.length_label.setText("-")
        self.hex_cells_label.setText("-")
        self.crossing_difficulty_label.setText("-")
        self.cover_value_label.setText("-")
        self.movement_penalty_label.setText("-")
        self.waterway_id_label.setText("-")
        
        self.navigable_check.setChecked(False)
        self.seasonal_check.setChecked(False)
        self.artificial_check.setChecked(False)
        
        self.highlight_btn.setEnabled(False)
        self.is_highlighted = False


class RoadInfoWidget(QWidget):
    """Widget for displaying road information."""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self.current_road: Optional[Dict[str, Any]] = None
    
    def _setup_ui(self):
        """Setup the road info UI."""
        layout = QVBoxLayout(self)
        
        # Road name with styling
        self.name_label = QLabel("No road selected")
        self.name_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.name_label.setStyleSheet("QLabel { color: #FF9800; padding: 8px; background-color: #FFF3E0; border-radius: 3px; }")
        self.name_label.setWordWrap(True)
        layout.addWidget(self.name_label)
        
        # Road properties
        road_group = QGroupBox("Road Properties")
        road_layout = QFormLayout(road_group)
        
        self.ref_label = QLabel("-")
        road_layout.addRow("Reference:", self.ref_label)
        
        self.type_label = QLabel("-")
        road_layout.addRow("Type:", self.type_label)
        
        self.speed_label = QLabel("-")
        road_layout.addRow("Speed Limit:", self.speed_label)
        
        self.segments_label = QLabel("-")
        road_layout.addRow("Segments:", self.segments_label)
        
        layout.addWidget(road_group)
        
        # Special features
        features_group = QGroupBox("Features")
        features_layout = QVBoxLayout(features_group)
        
        self.oneway_check = QCheckBox("One-way")
        self.oneway_check.setEnabled(False)
        features_layout.addWidget(self.oneway_check)
        
        self.bridge_check = QCheckBox("Has Bridges")
        self.bridge_check.setEnabled(False)
        features_layout.addWidget(self.bridge_check)
        
        self.tunnel_check = QCheckBox("Has Tunnels")
        self.tunnel_check.setEnabled(False)
        features_layout.addWidget(self.tunnel_check)
        
        self.multilayer_check = QCheckBox("Multi-layer")
        self.multilayer_check.setEnabled(False)
        features_layout.addWidget(self.multilayer_check)
        
        layout.addWidget(features_group)
        
        # Technical info
        tech_group = QGroupBox("Technical Information")
        tech_layout = QFormLayout(tech_group)
        
        self.osm_label = QLabel("-")
        tech_layout.addRow("OSM ID:", self.osm_label)
        
        layout.addWidget(tech_group)
        
        # Add stretch to push everything to top
        layout.addStretch()
    
    def display_road_info(self, road_metadata: Dict[str, Any]):
        """Display road information."""
        self.current_road = road_metadata
        
        # Update road name
        name = road_metadata.get('name', 'Unnamed Road')
        ref = road_metadata.get('ref', '')
        
        if name != 'Unnamed Road' and ref:
            display_name = f"{name} ({ref})"
        elif name != 'Unnamed Road':
            display_name = name
        elif ref:
            display_name = ref
        else:
            display_name = "Unnamed Road"
        
        self.name_label.setText(display_name)
        
        # Update road properties
        self.ref_label.setText(ref if ref else "None")
        self.type_label.setText(road_metadata.get('type', 'unknown').title())
        
        speed = road_metadata.get('maxspeed', 0)
        if speed > 0:
            self.speed_label.setText(f"{speed} km/h")
        else:
            self.speed_label.setText("No limit specified")
        
        segments = road_metadata.get('segment_count', 0)
        self.segments_label.setText(str(segments))
        
        # Update features
        self.oneway_check.setChecked(road_metadata.get('oneway', False))
        
        features = road_metadata.get('special_features', [])
        self.bridge_check.setChecked('bridge' in features)
        self.tunnel_check.setChecked('tunnel' in features)
        self.multilayer_check.setChecked(any(f.startswith('layer_') for f in features))
        
        # Update technical info
        osm_id = road_metadata.get('osm_id', '')
        if osm_id:
            self.osm_label.setText(str(osm_id))
        else:
            self.osm_label.setText("Not available")
    
    def clear_info(self):
        """Clear road information."""
        self.current_road = None
        self.name_label.setText("No road selected")
        
        # Clear all labels
        for label in [self.ref_label, self.type_label, self.speed_label, 
                     self.segments_label, self.osm_label]:
            label.setText("-")
        
        # Clear all checkboxes
        for checkbox in [self.oneway_check, self.bridge_check, 
                        self.tunnel_check, self.multilayer_check]:
            checkbox.setChecked(False)


class TerrainInfoWidget(QWidget):
    """Widget for displaying terrain information."""
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self.current_hex: Optional[HexCell] = None
    
    def _setup_ui(self):
        """Setup the terrain info UI."""
        layout = QVBoxLayout(self)
        
        # Hex coordinates with styling
        self.coords_label = QLabel("No hex selected")
        self.coords_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.coords_label.setStyleSheet("QLabel { color: #2196F3; padding: 5px; background-color: #E3F2FD; border-radius: 3px; }")
        layout.addWidget(self.coords_label)
        
        # Terrain properties
        terrain_group = QGroupBox("Terrain Properties")
        terrain_layout = QFormLayout(terrain_group)
        
        self.terrain_type_label = QLabel("-")
        terrain_layout.addRow("Type:", self.terrain_type_label)
        
        self.elevation_label = QLabel("-")
        terrain_layout.addRow("Elevation:", self.elevation_label)
        
        self.slope_label = QLabel("-")
        terrain_layout.addRow("Slope:", self.slope_label)
        
        self.land_use_label = QLabel("-")
        terrain_layout.addRow("Land Use:", self.land_use_label)
        
        layout.addWidget(terrain_group)
        
        # Features
        features_group = QGroupBox("Features")
        features_layout = QVBoxLayout(features_group)
        
        self.roads_check = QCheckBox("Roads")
        self.roads_check.setEnabled(False)
        features_layout.addWidget(self.roads_check)
        
        self.buildings_check = QCheckBox("Buildings")
        self.buildings_check.setEnabled(False)
        features_layout.addWidget(self.buildings_check)
        
        self.water_check = QCheckBox("Water")
        self.water_check.setEnabled(False)
        features_layout.addWidget(self.water_check)
        
        layout.addWidget(features_group)
        
        # Movement costs
        movement_group = QGroupBox("Movement Costs")
        movement_layout = QFormLayout(movement_group)
        
        self.infantry_cost_label = QLabel("-")
        movement_layout.addRow("Infantry:", self.infantry_cost_label)
        
        self.vehicle_cost_label = QLabel("-")
        movement_layout.addRow("Vehicle:", self.vehicle_cost_label)
        
        self.aircraft_cost_label = QLabel("-")
        movement_layout.addRow("Aircraft:", self.aircraft_cost_label)
        
        layout.addWidget(movement_group)
        
        # Tactical properties
        tactical_group = QGroupBox("Tactical Properties")
        tactical_layout = QFormLayout(tactical_group)
        
        self.cover_label = QLabel("-")
        tactical_layout.addRow("Cover:", self.cover_label)
        
        self.concealment_label = QLabel("-")
        tactical_layout.addRow("Concealment:", self.concealment_label)
        
        self.los_height_label = QLabel("-")
        tactical_layout.addRow("LOS Height:", self.los_height_label)
        
        layout.addWidget(tactical_group)
        
        # Stretch to fill remaining space
        layout.addStretch()
    
    def update_hex_info(self, hex_cell: HexCell):
        """Update display with hex cell information."""
        self.current_hex = hex_cell
        
        # Coordinates with highlighting
        coord_text = f"Hex ({hex_cell.q}, {hex_cell.r}) - SELECTED"
        self.coords_label.setText(coord_text)
        
        # Terrain properties with better formatting
        terrain_type = hex_cell.terrain_type if hex_cell.terrain_type else "Unknown"
        self.terrain_type_label.setText(terrain_type.title())
        
        elevation = hex_cell.elevation_mean if hex_cell.elevation_mean is not None else 0.0
        self.elevation_label.setText(f"{elevation:.1f}m")
        
        slope = hex_cell.slope if hex_cell.slope is not None else 0.0
        self.slope_label.setText(f"{slope:.1f}°")
        
        land_use = hex_cell.land_use if hex_cell.land_use else "Unclassified"
        self.land_use_label.setText(land_use.title())
        
        # Features
        self.roads_check.setChecked(hex_cell.has_roads)
        self.buildings_check.setChecked(hex_cell.has_buildings)
        self.water_check.setChecked(hex_cell.has_water)
        
        # Movement costs
        infantry_cost = hex_cell.movement_cost.get('infantry', 1.0)
        vehicle_cost = hex_cell.movement_cost.get('vehicle', 1.0)
        aircraft_cost = hex_cell.movement_cost.get('aircraft', 1.0)
        
        self.infantry_cost_label.setText(f"{infantry_cost:.1f}" if infantry_cost != float('inf') else "Impassable")
        self.vehicle_cost_label.setText(f"{vehicle_cost:.1f}" if vehicle_cost != float('inf') else "Impassable")
        self.aircraft_cost_label.setText(f"{aircraft_cost:.1f}")
        
        # Tactical properties
        self.cover_label.setText(f"{hex_cell.cover_value:.2f}")
        self.concealment_label.setText(f"{hex_cell.concealment:.2f}")
        self.los_height_label.setText(f"{hex_cell.los_blocking_height:.1f}m")
    
    def clear_selection(self):
        """Clear the current selection."""
        self.current_hex = None
        self.coords_label.setText("No hex selected")
        
        # Clear all fields
        self.terrain_type_label.setText("-")
        self.elevation_label.setText("-")
        self.slope_label.setText("-")
        self.land_use_label.setText("-")
        
        self.roads_check.setChecked(False)
        self.buildings_check.setChecked(False)
        self.water_check.setChecked(False)
        
        self.infantry_cost_label.setText("-")
        self.vehicle_cost_label.setText("-")
        self.aircraft_cost_label.setText("-")
        
        self.cover_label.setText("-")
        self.concealment_label.setText("-")
        self.los_height_label.setText("-")
    
    def clear_info(self):
        """Clear the displayed information."""
        self.current_hex = None
        self.coords_label.setText("No hex selected")
        
        # Clear all labels
        for label in [self.terrain_type_label, self.elevation_label, self.slope_label,
                     self.land_use_label, self.infantry_cost_label, self.vehicle_cost_label,
                     self.aircraft_cost_label, self.cover_label, self.concealment_label,
                     self.los_height_label]:
            label.setText("-")
        
        # Clear checkboxes
        for checkbox in [self.roads_check, self.buildings_check, self.water_check]:
            checkbox.setChecked(False)


class UnitInfoWidget(QWidget):
    """Widget for displaying unit information and issuing orders."""
    
    unit_order_issued = pyqtSignal(str, dict)  # order_type, kwargs
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self.current_unit: Optional[Unit] = None
        self.simulation: Optional[Simulation] = None
    
    def _setup_ui(self):
        """Setup the unit info UI."""
        layout = QVBoxLayout(self)
        
        # Unit identity
        self.unit_name_label = QLabel("No unit selected")
        self.unit_name_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(self.unit_name_label)
        
        # Unit status
        status_group = QGroupBox("Status")
        status_layout = QFormLayout(status_group)
        
        self.unit_type_label = QLabel("-")
        status_layout.addRow("Type:", self.unit_type_label)
        
        self.side_label = QLabel("-")
        status_layout.addRow("Side:", self.side_label)
        
        self.position_label = QLabel("-")
        status_layout.addRow("Position:", self.position_label)
        
        layout.addWidget(status_group)
        
        # Combat status
        combat_group = QGroupBox("Combat Status")
        combat_layout = QVBoxLayout(combat_group)
        
        # Strength
        strength_layout = QHBoxLayout()
        strength_layout.addWidget(QLabel("Strength:"))
        self.strength_bar = QProgressBar()
        self.strength_bar.setMaximum(100)
        self.strength_label = QLabel("100/100")
        strength_layout.addWidget(self.strength_bar)
        strength_layout.addWidget(self.strength_label)
        combat_layout.addLayout(strength_layout)
        
        # Morale
        morale_layout = QHBoxLayout()
        morale_layout.addWidget(QLabel("Morale:"))
        self.morale_bar = QProgressBar()
        self.morale_bar.setMaximum(100)
        self.morale_label = QLabel("100/100")
        morale_layout.addWidget(self.morale_bar)
        morale_layout.addWidget(self.morale_label)
        combat_layout.addLayout(morale_layout)
        
        # Movement points
        movement_layout = QHBoxLayout()
        movement_layout.addWidget(QLabel("Movement:"))
        self.movement_bar = QProgressBar()
        self.movement_bar.setMaximum(100)
        self.movement_label = QLabel("10/10")
        movement_layout.addWidget(self.movement_bar)
        movement_layout.addWidget(self.movement_label)
        combat_layout.addLayout(movement_layout)
        
        # Suppression
        suppression_layout = QHBoxLayout()
        suppression_layout.addWidget(QLabel("Suppression:"))
        self.suppression_bar = QProgressBar()
        self.suppression_bar.setMaximum(100)
        self.suppression_label = QLabel("0%")
        suppression_layout.addWidget(self.suppression_bar)
        suppression_layout.addWidget(self.suppression_label)
        combat_layout.addLayout(suppression_layout)
        
        layout.addWidget(combat_group)
        
        # Orders
        orders_group = QGroupBox("Orders")
        orders_layout = QVBoxLayout(orders_group)
        
        # Movement order
        self.move_btn = QPushButton("Issue Move Order")
        self.move_btn.clicked.connect(self._issue_move_order)
        orders_layout.addWidget(self.move_btn)
        
        # Attack order
        self.attack_btn = QPushButton("Issue Attack Order")
        self.attack_btn.clicked.connect(self._issue_attack_order)
        orders_layout.addWidget(self.attack_btn)
        
        layout.addWidget(orders_group)
        
        # Weapons
        weapons_group = QGroupBox("Weapons")
        weapons_layout = QVBoxLayout(weapons_group)
        
        self.weapons_list = QListWidget()
        weapons_layout.addWidget(self.weapons_list)
        
        layout.addWidget(weapons_group)
        
        # Detected enemies
        enemies_group = QGroupBox("Detected Enemies")
        enemies_layout = QVBoxLayout(enemies_group)
        
        self.enemies_list = QListWidget()
        enemies_layout.addWidget(self.enemies_list)
        
        layout.addWidget(enemies_group)
        
        # Stretch to fill remaining space
        layout.addStretch()
        
        # Initially disable buttons
        self.move_btn.setEnabled(False)
        self.attack_btn.setEnabled(False)
    
    def set_simulation(self, simulation: Simulation):
        """Set the simulation reference."""
        self.simulation = simulation
    
    def update_unit_info(self, unit: Unit):
        """Update display with unit information."""
        self.current_unit = unit
        
        # Unit identity
        self.unit_name_label.setText(unit.name)
        self.unit_type_label.setText(unit.unit_type.value.title())
        self.side_label.setText(unit.side.value.title())
        
        # Position
        if unit.position:
            self.position_label.setText(f"({unit.position.q}, {unit.position.r})")
        else:
            self.position_label.setText("Unpositioned")
        
        # Combat status
        self.strength_bar.setValue(int(unit.strength))
        self.strength_label.setText(f"{unit.strength:.0f}/{unit.max_strength:.0f}")
        
        self.morale_bar.setValue(int(unit.morale))
        self.morale_label.setText(f"{unit.morale:.0f}/100")
        
        movement_percent = int((unit.movement_points / unit.max_movement_points) * 100)
        self.movement_bar.setValue(movement_percent)
        self.movement_label.setText(f"{unit.movement_points:.1f}/{unit.max_movement_points:.1f}")
        
        self.suppression_bar.setValue(int(unit.suppression_level))
        self.suppression_label.setText(f"{unit.suppression_level:.0f}%")
        
        # Weapons
        self.weapons_list.clear()
        for weapon in unit.weapons:
            item_text = f"{weapon.name} (Range: {weapon.max_range}m)"
            self.weapons_list.addItem(item_text)
        
        # Detected enemies
        self.enemies_list.clear()
        if self.simulation:
            for enemy_id in unit.detected_enemies:
                if enemy_id in self.simulation.units:
                    enemy = self.simulation.units[enemy_id]
                    distance = unit.distance_to(enemy)
                    item_text = f"{enemy.name} ({distance:.0f}m)"
                    self.enemies_list.addItem(item_text)
        
        # Enable/disable buttons
        print(f"DEBUG: Unit mobility - is_alive: {unit.is_alive}, movement_points: {unit.movement_points}, suppression: {unit.suppression_level}, is_mobile: {unit.is_mobile}")
        self.move_btn.setEnabled(unit.is_mobile)
        self.attack_btn.setEnabled(unit.is_alive and len(unit.detected_enemies) > 0)
    
    def clear_info(self):
        """Clear the displayed information."""
        self.current_unit = None
        self.unit_name_label.setText("No unit selected")
        
        # Clear labels
        for label in [self.unit_type_label, self.side_label, self.position_label,
                     self.strength_label, self.morale_label, self.movement_label,
                     self.suppression_label]:
            label.setText("-")
        
        # Clear progress bars
        for bar in [self.strength_bar, self.morale_bar, self.movement_bar, self.suppression_bar]:
            bar.setValue(0)
        
        # Clear lists
        self.weapons_list.clear()
        self.enemies_list.clear()
        
        # Disable buttons
        self.move_btn.setEnabled(False)
        self.attack_btn.setEnabled(False)
    
    def _issue_move_order(self):
        """Issue a movement order."""
        print(f"DEBUG: _issue_move_order called, current_unit = {self.current_unit}")
        if self.current_unit:
            print(f"DEBUG: Emitting enter_movement_mode signal for unit {self.current_unit.id}")
            # For now, emit signal to enter movement mode
            # The main window will handle the actual movement selection
            self.unit_order_issued.emit("enter_movement_mode", {"unit_id": self.current_unit.id})
        else:
            print("DEBUG: No current unit selected")
    
    def _issue_attack_order(self):
        """Issue an attack order."""
        if not self.current_unit or not self.current_unit.detected_enemies:
            return
        
        # For simplicity, attack the first detected enemy
        # In a full implementation, this would open a target selection dialog
        target_id = list(self.current_unit.detected_enemies.keys())[0]
        self.unit_order_issued.emit("attack", {
            "attacker_id": self.current_unit.id,
            "target_id": target_id
        })


class DisplayModeLegend(QWidget):
    """Widget that shows color legend for different display modes."""
    
    def __init__(self):
        super().__init__()
        self.current_mode = "Terrain"  # Set before _setup_ui
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup the legend UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        # Title
        title = QLabel("Legend")
        title.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Scroll area for legend items
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMaximumHeight(150)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.legend_widget = QWidget()
        self.legend_layout = QVBoxLayout(self.legend_widget)
        self.legend_layout.setContentsMargins(2, 2, 2, 2)
        self.legend_layout.setSpacing(1)
        
        self.scroll_area.setWidget(self.legend_widget)
        layout.addWidget(self.scroll_area)
        
        # Initialize with terrain mode
        self.update_legend("Terrain")
    
    def _create_color_swatch(self, color: QColor, size: int = 16) -> QPixmap:
        """Create a color swatch pixmap."""
        pixmap = QPixmap(size, size)
        pixmap.fill(color)
        
        # Add border
        painter = QPainter(pixmap)
        painter.setPen(QColor(0, 0, 0))
        painter.drawRect(0, 0, size - 1, size - 1)
        painter.end()
        
        return pixmap
    
    def _add_legend_item(self, color: QColor, text: str):
        """Add a legend item with color swatch and text."""
        item_widget = QWidget()
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(2, 1, 2, 1)
        item_layout.setSpacing(5)
        
        # Color swatch
        swatch_label = QLabel()
        swatch_label.setPixmap(self._create_color_swatch(color, 12))
        swatch_label.setFixedSize(12, 12)
        item_layout.addWidget(swatch_label)
        
        # Text
        text_label = QLabel(text)
        text_label.setFont(QFont("Arial", 8))
        item_layout.addWidget(text_label)
        item_layout.addStretch()
        
        self.legend_layout.addWidget(item_widget)
    
    def update_legend(self, display_mode: str):
        """Update legend based on display mode."""
        if self.current_mode == display_mode:
            return
            
        self.current_mode = display_mode
        
        # Clear existing items
        for i in reversed(range(self.legend_layout.count())):
            item = self.legend_layout.itemAt(i)
            if item:
                child = item.widget()
                if child:
                    child.setParent(None)
        
        # Add legend items based on display mode
        if display_mode == "Terrain":
            self._add_terrain_legend()
        elif display_mode == "Elevation":
            self._add_elevation_legend()
        elif display_mode == "Movement Cost":
            self._add_movement_cost_legend()
        elif display_mode == "Cover":
            self._add_cover_legend()
        elif display_mode == "LOS Blocking":
            self._add_los_blocking_legend()
        elif display_mode == "Control":
            self._add_control_legend()
    
    def _add_terrain_legend(self):
        """Add terrain legend items."""
        # Water
        self._add_legend_item(QColor(0, 100, 255, 180), "Sea")
        self._add_legend_item(QColor(70, 130, 200, 170), "Lake")
        self._add_legend_item(QColor(100, 150, 220, 160), "River")
        
        # Urban
        self._add_legend_item(QColor(140, 140, 140, 180), "Urban Dense")
        self._add_legend_item(QColor(180, 180, 180, 150), "Highway")
        
        # Forest
        self._add_legend_item(QColor(40, 120, 40, 170), "Forest Lowland")
        self._add_legend_item(QColor(30, 100, 30, 170), "Forest Hills")
        self._add_legend_item(QColor(20, 80, 20, 170), "Forest Mountain")
        
        # Agriculture
        self._add_legend_item(QColor(180, 200, 120, 150), "Farmland")
        self._add_legend_item(QColor(120, 160, 80, 150), "Pasture")
        
        # Terrain
        self._add_legend_item(QColor(160, 200, 120, 150), "Plains")
        self._add_legend_item(QColor(120, 160, 80, 160), "Hills")
        self._add_legend_item(QColor(70, 70, 70, 180), "High Mountain")
        self._add_legend_item(QColor(200, 180, 120, 150), "Desert")
    
    def _add_elevation_legend(self):
        """Add elevation legend items."""
        # Use colors that match the matplotlib terrain colormap
        try:
            import matplotlib.pyplot as plt
            cmap = plt.cm.get_cmap('terrain')
            
            # Sample the colormap at different elevations
            colors_and_labels = [
                (0.0, "Sea Level (0m)"),
                (0.2, "Low (100m)"),
                (0.4, "Medium (200m)"),
                (0.6, "High (300m)"),
                (0.8, "Very High (400m)"),
                (1.0, "Peak (500m+)")
            ]
            
            for normalized, label in colors_and_labels:
                rgba = cmap(normalized)
                color = QColor(int(rgba[0] * 255), int(rgba[1] * 255), 
                              int(rgba[2] * 255), 150)
                self._add_legend_item(color, label)
        except ImportError:
            # Fallback colors if matplotlib not available
            self._add_legend_item(QColor(0, 50, 100, 150), "Sea Level (0m)")
            self._add_legend_item(QColor(50, 100, 50, 150), "Low (100m)")
            self._add_legend_item(QColor(100, 150, 50, 150), "Medium (200m)")
            self._add_legend_item(QColor(150, 100, 50, 150), "High (300m)")
            self._add_legend_item(QColor(200, 150, 100, 150), "Very High (400m)")
            self._add_legend_item(QColor(220, 180, 120, 150), "Peak (500m+)")
    
    def _add_movement_cost_legend(self):
        """Add movement cost legend items."""
        # Match the actual gradient calculation from map_view.py
        costs_and_labels = [
            (1.0, "Easy (1x cost)"),
            (1.5, "Moderate (1.5x cost)"),
            (2.0, "Difficult (2x cost)"),
            (3.0, "Hard (3x cost)"),
            (float('inf'), "Impassable")
        ]
        
        for cost, label in costs_and_labels:
            if cost == float('inf'):
                color = QColor(255, 0, 0, 150)  # Red for impassable
            else:
                # Replicate the gradient calculation from _get_movement_cost_color
                normalized = max(0, min(1, (cost - 1.0) / 3.0))
                
                if normalized < 0.5:
                    # Green to yellow
                    red = int(255 * normalized * 2)
                    green = 255
                else:
                    # Yellow to red
                    red = 255
                    green = int(255 * (1 - normalized) * 2)
                
                color = QColor(red, green, 0, 150)
            
            self._add_legend_item(color, label)
    
    def _add_cover_legend(self):
        """Add cover legend items."""
        self._add_legend_item(QColor(255, 255, 255, 150), "No Cover (0%)")
        self._add_legend_item(QColor(200, 200, 200, 150), "Light Cover (25%)")
        self._add_legend_item(QColor(128, 128, 128, 150), "Medium Cover (50%)")
        self._add_legend_item(QColor(64, 64, 64, 150), "Heavy Cover (75%)")
        self._add_legend_item(QColor(0, 0, 0, 150), "Full Cover (100%)")
    
    def _add_los_blocking_legend(self):
        """Add LOS blocking legend items."""
        # Match the actual purple gradient calculation from map_view.py
        heights_and_labels = [
            (0.0, "No Obstruction (0m)"),
            (5.0, "Low Obstruction (5m)"),
            (10.0, "Medium Obstruction (10m)"),
            (15.0, "High Obstruction (15m)"),
            (20.0, "Complete Obstruction (20m+)")
        ]
        
        for height, label in heights_and_labels:
            # Replicate the gradient calculation from _get_los_blocking_color
            normalized = max(0, min(1, height / 20.0))
            purple_value = int(128 + 127 * normalized)
            color = QColor(purple_value, 0, purple_value, 150)
            self._add_legend_item(color, label)
    
    def _add_control_legend(self):
        """Add control legend items."""
        self._add_legend_item(QColor(255, 50, 50, 200), "Red Controlled")
        self._add_legend_item(QColor(50, 50, 255, 200), "Blue Controlled")
        self._add_legend_item(QColor(200, 200, 200, 80), "Neutral")


class SimulationControlWidget(QWidget):
    """Widget for simulation control and statistics."""
    
    display_mode_changed = pyqtSignal(str)  # display_mode_name
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self.simulation: Optional[Simulation] = None
        
        # Update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_stats)
        self.update_timer.start(1000)  # Update every second
    
    def _setup_ui(self):
        """Setup the simulation control UI."""
        layout = QVBoxLayout(self)
        
        # Simulation status
        status_group = QGroupBox("Simulation Status")
        status_layout = QFormLayout(status_group)
        
        self.state_label = QLabel("Stopped")
        status_layout.addRow("State:", self.state_label)
        
        self.turn_label = QLabel("0")
        status_layout.addRow("Turn:", self.turn_label)
        
        self.processing_time_label = QLabel("0.0ms")
        status_layout.addRow("Processing Time:", self.processing_time_label)
        
        layout.addWidget(status_group)
        
        # Unit statistics
        units_group = QGroupBox("Unit Statistics")
        units_layout = QFormLayout(units_group)
        
        self.total_units_label = QLabel("0")
        units_layout.addRow("Total Units:", self.total_units_label)
        
        self.red_units_label = QLabel("0")
        units_layout.addRow("Red Units:", self.red_units_label)
        
        self.blue_units_label = QLabel("0")
        units_layout.addRow("Blue Units:", self.blue_units_label)
        
        layout.addWidget(units_group)
        
        # Combat statistics
        combat_group = QGroupBox("Combat Statistics")
        combat_layout = QFormLayout(combat_group)
        
        self.engagements_label = QLabel("0")
        combat_layout.addRow("Engagements:", self.engagements_label)
        
        self.casualties_label = QLabel("0")
        combat_layout.addRow("Casualties:", self.casualties_label)
        
        layout.addWidget(combat_group)
        
        # Display mode control
        display_group = QGroupBox("Display Mode")
        display_layout = QFormLayout(display_group)
        
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItems([
            "Terrain", "Elevation", "Movement Cost", 
            "Cover", "LOS Blocking", "Control"
        ])
        self.display_mode_combo.currentTextChanged.connect(self.display_mode_changed.emit)
        display_layout.addWidget(self.display_mode_combo)
        
        # Add legend widget
        self.legend_widget = DisplayModeLegend()
        self.display_mode_combo.currentTextChanged.connect(self.legend_widget.update_legend)
        display_layout.addWidget(self.legend_widget)
        
        layout.addWidget(display_group)
        
        # Settings
        settings_group = QGroupBox("Settings")
        settings_layout = QFormLayout(settings_group)
        
        self.turn_duration_spin = QDoubleSpinBox()
        self.turn_duration_spin.setRange(1.0, 300.0)
        # Use config for default turn duration
        config = get_config()
        self.turn_duration_spin.setValue(config.simulation.turn_duration)
        self.turn_duration_spin.setSuffix(" seconds")
        settings_layout.addRow("Turn Duration:", self.turn_duration_spin)
        
        layout.addWidget(settings_group)
        
        # Stretch to fill remaining space
        layout.addStretch()
    
    def set_simulation(self, simulation: Simulation):
        """Set the simulation reference."""
        self.simulation = simulation
        
        # Connect turn duration setting
        self.turn_duration_spin.valueChanged.connect(
            lambda value: setattr(simulation, 'turn_duration', value)
        )
    
    def _update_stats(self):
        """Update simulation statistics."""
        if not self.simulation:
            return
        
        stats = self.simulation.get_simulation_stats()
        
        # Simulation status
        self.state_label.setText(stats['state'].title())
        self.turn_label.setText(str(stats['current_turn']))
        self.processing_time_label.setText(f"{stats['turn_processing_time'] * 1000:.1f}ms")
        
        # Unit statistics
        self.total_units_label.setText(str(stats['total_units']))
        self.red_units_label.setText(str(stats['red_units']))
        self.blue_units_label.setText(str(stats['blue_units']))
        
        # Combat statistics
        self.engagements_label.setText(str(stats['combat_engagements']))
        
        # Calculate casualties
        casualties = stats['total_units'] - stats['active_units']
        self.casualties_label.setText(str(casualties))


class SidePanel(QWidget):
    """
    Main side panel widget containing tabs for different information displays.
    """
    
    unit_order_issued = pyqtSignal(str, dict)  # order_type, kwargs
    display_mode_changed = pyqtSignal(str)  # display_mode_name
    waterway_highlight_requested = pyqtSignal(str, bool)  # waterway_name, highlight_on
    
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self.simulation: Optional[Simulation] = None
    
    def _setup_ui(self):
        """Setup the side panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Terrain info tab
        self.terrain_widget = TerrainInfoWidget()
        self.tab_widget.addTab(self.terrain_widget, "Terrain")
        
        # Road info tab
        self.road_widget = RoadInfoWidget()
        self.tab_widget.addTab(self.road_widget, "Roads")
        
        # Waterway info tab
        self.waterway_widget = WaterwayInfoWidget()
        self.waterway_widget.waterway_highlight_requested.connect(self.waterway_highlight_requested.emit)
        self.tab_widget.addTab(self.waterway_widget, "Waterways")
        
        # Unit info tab
        self.unit_widget = UnitInfoWidget()
        self.unit_widget.unit_order_issued.connect(self.unit_order_issued)
        self.tab_widget.addTab(self.unit_widget, "Unit")
        
        # Simulation control tab
        self.simulation_widget = SimulationControlWidget()
        self.simulation_widget.display_mode_changed.connect(self.display_mode_changed.emit)
        self.tab_widget.addTab(self.simulation_widget, "Simulation")
        
        # Set minimum width
        self.setMinimumWidth(300)
        self.setMaximumWidth(400)
    
    def set_simulation(self, simulation: Simulation):
        """Set the simulation reference."""
        self.simulation = simulation
        self.unit_widget.set_simulation(simulation)
        self.simulation_widget.set_simulation(simulation)
    
    def show_hex_info(self, hex_cell: HexCell):
        """Show hex cell information."""
        self.terrain_widget.update_hex_info(hex_cell)
        self.tab_widget.setCurrentWidget(self.terrain_widget)
    
    def show_unit_info(self, unit: Unit):
        """Show unit information."""
        self.unit_widget.update_unit_info(unit)
        self.tab_widget.setCurrentWidget(self.unit_widget)
    
    def display_road_info(self, road_metadata: Dict[str, Any]):
        """Display road information."""
        self.road_widget.display_road_info(road_metadata)
        self.tab_widget.setCurrentWidget(self.road_widget)
    
    def display_waterway_info(self, waterway_metadata: Dict[str, Any], segments: Optional[list] = None):
        """Display waterway information and segments."""
        self.waterway_widget.display_waterway_info(waterway_metadata, segments)
        self.tab_widget.setCurrentWidget(self.waterway_widget)
    
    def update_display(self):
        """Update the display with current information."""
        # Update unit info if a unit is selected
        if self.unit_widget.current_unit:
            self.unit_widget.update_unit_info(self.unit_widget.current_unit)
    
    def clear_selection(self):
        """Clear current selection."""
        self.terrain_widget.clear_info()
        self.road_widget.clear_info()
        self.waterway_widget.clear_selection()
        self.unit_widget.clear_info()