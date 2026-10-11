"""
Settings dialog for configuring wargame simulation parameters.
"""
import configparser
from pathlib import Path
from typing import Dict, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox,
    QPushButton, QLineEdit, QGroupBox, QDialogButtonBox, QLabel,
    QSlider, QMessageBox, QFileDialog, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIntValidator, QDoubleValidator

from utils.logger import get_logger


class SettingsDialog(QDialog):
    """
    Comprehensive settings dialog with tabbed interface for all configuration options.
    """
    
    settings_changed = pyqtSignal(dict)  # Emitted when settings are applied
    
    def __init__(self, parent=None, config_file="config.ini"):
        super().__init__(parent)
        
        self.logger = get_logger('ui.settings')
        self.config_file = Path(config_file)
        self.config = configparser.ConfigParser()
        
        # Load current settings
        self._load_settings()
        
        self._setup_ui()
        self._load_values_from_config()
        
    def _setup_ui(self):
        """Setup the settings dialog UI."""
        self.setWindowTitle("Wargame Simulation Settings")
        self.setModal(True)
        self.resize(600, 500)
        
        # Main layout
        layout = QVBoxLayout(self)
        
        # Create tabbed interface
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Create tabs
        self._create_simulation_tab()
        self._create_display_tab()
        self._create_performance_tab()
        self._create_units_tab()
        self._create_terrain_tab()
        self._create_ui_tab()
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Reset to defaults button
        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self._reset_to_defaults)
        button_layout.addWidget(self.reset_button)
        
        # Import/Export buttons
        self.import_button = QPushButton("Import Settings...")
        self.import_button.clicked.connect(self._import_settings)
        button_layout.addWidget(self.import_button)
        
        self.export_button = QPushButton("Export Settings...")
        self.export_button.clicked.connect(self._export_settings)
        button_layout.addWidget(self.export_button)
        
        button_layout.addStretch()
        
        # Standard dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel | 
            QDialogButtonBox.StandardButton.Apply
        )
        self.button_box.accepted.connect(self._apply_and_close)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_settings)
        button_layout.addWidget(self.button_box)
        
        layout.addLayout(button_layout)
    
    def _create_simulation_tab(self):
        """Create simulation settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Grid settings group
        grid_group = QGroupBox("Grid Configuration")
        grid_layout = QFormLayout(grid_group)
        
        self.hex_size_spin = QDoubleSpinBox()
        self.hex_size_spin.setRange(1.0, 10000.0)
        self.hex_size_spin.setSuffix(" meters")
        self.hex_size_spin.setToolTip("Size of each hexagonal cell in meters")
        grid_layout.addRow("Hex Size:", self.hex_size_spin)
        
        layout.addWidget(grid_group)
        
        # Timing settings group
        timing_group = QGroupBox("Timing Configuration")
        timing_layout = QFormLayout(timing_group)
        
        self.turn_duration_spin = QDoubleSpinBox()
        self.turn_duration_spin.setRange(0.1, 300.0)
        self.turn_duration_spin.setSuffix(" seconds")
        self.turn_duration_spin.setToolTip("Duration of each turn in real-time mode")
        timing_layout.addRow("Turn Duration:", self.turn_duration_spin)
        
        layout.addWidget(timing_group)
        
        # Random settings group
        random_group = QGroupBox("Randomization")
        random_layout = QFormLayout(random_group)
        
        self.random_seed_spin = QSpinBox()
        self.random_seed_spin.setRange(0, 999999)
        self.random_seed_spin.setSpecialValueText("Random")
        self.random_seed_spin.setToolTip("Random seed for reproducible results (0 = random)")
        random_layout.addRow("Random Seed:", self.random_seed_spin)
        
        layout.addWidget(random_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Simulation")
    
    def _create_display_tab(self):
        """Create display settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Display mode group
        mode_group = QGroupBox("Display Mode")
        mode_layout = QFormLayout(mode_group)
        
        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItems([
            "terrain", "elevation", "movement_cost", 
            "cover", "los_blocking", "control"
        ])
        self.display_mode_combo.setToolTip("Default display mode for the map")
        mode_layout.addRow("Default Display Mode:", self.display_mode_combo)
        
        layout.addWidget(mode_group)
        
        # Visual options group
        visual_group = QGroupBox("Visual Options")
        visual_layout = QFormLayout(visual_group)
        
        self.show_grid_check = QCheckBox()
        self.show_grid_check.setToolTip("Show hexagonal grid lines on the map")
        visual_layout.addRow("Show Grid Lines:", self.show_grid_check)
        
        self.show_coordinates_check = QCheckBox()
        self.show_coordinates_check.setToolTip("Show hex coordinates on each cell")
        visual_layout.addRow("Show Coordinates:", self.show_coordinates_check)
        
        self.antialiasing_check = QCheckBox()
        self.antialiasing_check.setToolTip("Enable antialiasing for smoother graphics")
        visual_layout.addRow("Antialiasing:", self.antialiasing_check)
        
        layout.addWidget(visual_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Display")
    
    def _create_performance_tab(self):
        """Create performance settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Cache settings group
        cache_group = QGroupBox("Caching")
        cache_layout = QFormLayout(cache_group)
        
        self.los_cache_spin = QSpinBox()
        self.los_cache_spin.setRange(1000, 100000)
        self.los_cache_spin.setToolTip("Maximum number of line-of-sight calculations to cache")
        cache_layout.addRow("LOS Cache Size:", self.los_cache_spin)
        
        layout.addWidget(cache_group)
        
        # Animation settings group
        animation_group = QGroupBox("Animation")
        animation_layout = QFormLayout(animation_group)
        
        self.animation_fps_spin = QSpinBox()
        self.animation_fps_spin.setRange(10, 120)
        self.animation_fps_spin.setSuffix(" FPS")
        self.animation_fps_spin.setToolTip("Target frame rate for animations")
        animation_layout.addRow("Animation FPS:", self.animation_fps_spin)
        
        layout.addWidget(animation_group)
        
        # Pathfinding settings group
        pathfinding_group = QGroupBox("Pathfinding")
        pathfinding_layout = QFormLayout(pathfinding_group)
        
        self.max_pathfinding_spin = QSpinBox()
        self.max_pathfinding_spin.setRange(1000, 100000)
        self.max_pathfinding_spin.setToolTip("Maximum iterations for pathfinding algorithms")
        pathfinding_layout.addRow("Max Iterations:", self.max_pathfinding_spin)
        
        layout.addWidget(pathfinding_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Performance")
    
    def _create_units_tab(self):
        """Create unit settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Default movement group
        movement_group = QGroupBox("Default Movement")
        movement_layout = QFormLayout(movement_group)
        
        self.infantry_movement_spin = QDoubleSpinBox()
        self.infantry_movement_spin.setRange(1.0, 50.0)
        self.infantry_movement_spin.setSuffix(" points")
        self.infantry_movement_spin.setToolTip("Default movement points for infantry units")
        movement_layout.addRow("Infantry Movement:", self.infantry_movement_spin)
        
        self.vehicle_movement_spin = QDoubleSpinBox()
        self.vehicle_movement_spin.setRange(1.0, 100.0)
        self.vehicle_movement_spin.setSuffix(" points")
        self.vehicle_movement_spin.setToolTip("Default movement points for vehicle units")
        movement_layout.addRow("Vehicle Movement:", self.vehicle_movement_spin)
        
        layout.addWidget(movement_group)
        
        # Sensor settings group
        sensor_group = QGroupBox("Sensors")
        sensor_layout = QFormLayout(sensor_group)
        
        self.sensor_range_spin = QDoubleSpinBox()
        self.sensor_range_spin.setRange(100.0, 5000.0)
        self.sensor_range_spin.setSuffix(" meters")
        self.sensor_range_spin.setToolTip("Default sensor detection range")
        sensor_layout.addRow("Default Sensor Range:", self.sensor_range_spin)
        
        layout.addWidget(sensor_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Units")
    
    def _create_terrain_tab(self):
        """Create terrain settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Height settings group
        height_group = QGroupBox("Terrain Heights")
        height_layout = QFormLayout(height_group)
        
        self.forest_height_spin = QDoubleSpinBox()
        self.forest_height_spin.setRange(1.0, 50.0)
        self.forest_height_spin.setSuffix(" meters")
        self.forest_height_spin.setToolTip("Average height of forest vegetation")
        height_layout.addRow("Forest Height:", self.forest_height_spin)
        
        self.building_height_spin = QDoubleSpinBox()
        self.building_height_spin.setRange(3.0, 100.0)
        self.building_height_spin.setSuffix(" meters")
        self.building_height_spin.setToolTip("Average height of buildings")
        height_layout.addRow("Building Height:", self.building_height_spin)
        
        layout.addWidget(height_group)
        
        # Slope settings group
        slope_group = QGroupBox("Terrain Restrictions")
        slope_layout = QFormLayout(slope_group)
        
        self.max_slope_spin = QDoubleSpinBox()
        self.max_slope_spin.setRange(10.0, 90.0)
        self.max_slope_spin.setSuffix("°")
        self.max_slope_spin.setToolTip("Maximum slope angle for vehicle movement")
        slope_layout.addRow("Max Vehicle Slope:", self.max_slope_spin)
        
        layout.addWidget(slope_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Terrain")
    
    def _create_ui_tab(self):
        """Create UI settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Window settings group
        window_group = QGroupBox("Window Settings")
        window_layout = QFormLayout(window_group)
        
        self.window_width_spin = QSpinBox()
        self.window_width_spin.setRange(800, 3840)
        self.window_width_spin.setSuffix(" px")
        self.window_width_spin.setToolTip("Default window width")
        window_layout.addRow("Window Width:", self.window_width_spin)
        
        self.window_height_spin = QSpinBox()
        self.window_height_spin.setRange(600, 2160)
        self.window_height_spin.setSuffix(" px")
        self.window_height_spin.setToolTip("Default window height")
        window_layout.addRow("Window Height:", self.window_height_spin)
        
        layout.addWidget(window_group)
        
        # Panel settings group
        panel_group = QGroupBox("Panel Layout")
        panel_layout = QFormLayout(panel_group)
        
        self.map_ratio_spin = QDoubleSpinBox()
        self.map_ratio_spin.setRange(0.5, 0.95)
        self.map_ratio_spin.setSingleStep(0.05)
        self.map_ratio_spin.setToolTip("Proportion of window width for map view")
        panel_layout.addRow("Map View Ratio:", self.map_ratio_spin)
        
        self.side_panel_width_spin = QSpinBox()
        self.side_panel_width_spin.setRange(200, 500)
        self.side_panel_width_spin.setSuffix(" px")
        self.side_panel_width_spin.setToolTip("Width of the side information panel")
        panel_layout.addRow("Side Panel Width:", self.side_panel_width_spin)
        
        layout.addWidget(panel_group)
        
        # Font settings group
        font_group = QGroupBox("Font Settings")
        font_layout = QFormLayout(font_group)
        
        self.font_family_edit = QLineEdit()
        self.font_family_edit.setToolTip("Default font family for UI elements")
        font_layout.addRow("Font Family:", self.font_family_edit)
        
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 24)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.setToolTip("Default font size for UI elements")
        font_layout.addRow("Font Size:", self.font_size_spin)
        
        layout.addWidget(font_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "User Interface")
    
    def _load_settings(self):
        """Load settings from config file."""
        try:
            if self.config_file.exists():
                self.config.read(self.config_file)
                self.logger.info(f"Loaded settings from {self.config_file}")
            else:
                # Load from example file if config doesn't exist
                example_file = Path("config.ini.example")
                if example_file.exists():
                    self.config.read(example_file)
                    self.logger.info(f"Loaded settings from {example_file}")
                else:
                    self._create_default_config()
                    self.logger.info("Created default configuration")
        except Exception as e:
            self.logger.error(f"Failed to load settings: {e}")
            self._create_default_config()
    
    def _create_default_config(self):
        """Create default configuration."""
        self.config.add_section('Simulation')
        self.config.set('Simulation', 'hex_size', '30.0')
        self.config.set('Simulation', 'turn_duration', '30.0')
        self.config.set('Simulation', 'random_seed', '0')
        
        self.config.add_section('Display')
        self.config.set('Display', 'default_display_mode', 'terrain')
        self.config.set('Display', 'show_grid', 'true')
        self.config.set('Display', 'show_coordinates', 'false')
        self.config.set('Display', 'antialiasing', 'true')
        
        self.config.add_section('Performance')
        self.config.set('Performance', 'los_cache_size', '10000')
        self.config.set('Performance', 'animation_fps', '20')
        self.config.set('Performance', 'max_pathfinding_iterations', '10000')
        
        self.config.add_section('Units')
        self.config.set('Units', 'default_infantry_movement', '10.0')
        self.config.set('Units', 'default_vehicle_movement', '15.0')
        self.config.set('Units', 'default_sensor_range', '500.0')
        
        self.config.add_section('Terrain')
        self.config.set('Terrain', 'forest_height', '15.0')
        self.config.set('Terrain', 'building_height', '10.0')
        self.config.set('Terrain', 'max_slope_for_vehicles', '45.0')
        
        self.config.add_section('UI')
        self.config.set('UI', 'window_width', '1200')
        self.config.set('UI', 'window_height', '800')
        self.config.set('UI', 'map_view_ratio', '0.75')
        self.config.set('UI', 'side_panel_width', '300')
        self.config.set('UI', 'default_font_family', 'Arial')
        self.config.set('UI', 'default_font_size', '9')
    
    def _load_values_from_config(self):
        """Load values from config into UI controls."""
        try:
            # Simulation
            self.hex_size_spin.setValue(self.config.getfloat('Simulation', 'hex_size', fallback=30.0))
            self.turn_duration_spin.setValue(self.config.getfloat('Simulation', 'turn_duration', fallback=30.0))
            self.random_seed_spin.setValue(self.config.getint('Simulation', 'random_seed', fallback=0))
            
            # Display
            mode = self.config.get('Display', 'default_display_mode', fallback='terrain')
            index = self.display_mode_combo.findText(mode)
            if index >= 0:
                self.display_mode_combo.setCurrentIndex(index)
            
            self.show_grid_check.setChecked(self.config.getboolean('Display', 'show_grid', fallback=True))
            self.show_coordinates_check.setChecked(self.config.getboolean('Display', 'show_coordinates', fallback=False))
            self.antialiasing_check.setChecked(self.config.getboolean('Display', 'antialiasing', fallback=True))
            
            # Performance
            self.los_cache_spin.setValue(self.config.getint('Performance', 'los_cache_size', fallback=10000))
            self.animation_fps_spin.setValue(self.config.getint('Performance', 'animation_fps', fallback=20))
            self.max_pathfinding_spin.setValue(self.config.getint('Performance', 'max_pathfinding_iterations', fallback=10000))
            
            # Units
            self.infantry_movement_spin.setValue(self.config.getfloat('Units', 'default_infantry_movement', fallback=10.0))
            self.vehicle_movement_spin.setValue(self.config.getfloat('Units', 'default_vehicle_movement', fallback=15.0))
            self.sensor_range_spin.setValue(self.config.getfloat('Units', 'default_sensor_range', fallback=500.0))
            
            # Terrain
            self.forest_height_spin.setValue(self.config.getfloat('Terrain', 'forest_height', fallback=15.0))
            self.building_height_spin.setValue(self.config.getfloat('Terrain', 'building_height', fallback=10.0))
            self.max_slope_spin.setValue(self.config.getfloat('Terrain', 'max_slope_for_vehicles', fallback=45.0))
            
            # UI
            self.window_width_spin.setValue(self.config.getint('UI', 'window_width', fallback=1200))
            self.window_height_spin.setValue(self.config.getint('UI', 'window_height', fallback=800))
            self.map_ratio_spin.setValue(self.config.getfloat('UI', 'map_view_ratio', fallback=0.75))
            self.side_panel_width_spin.setValue(self.config.getint('UI', 'side_panel_width', fallback=300))
            self.font_family_edit.setText(self.config.get('UI', 'default_font_family', fallback='Arial'))
            self.font_size_spin.setValue(self.config.getint('UI', 'default_font_size', fallback=9))
            
        except Exception as e:
            self.logger.error(f"Error loading values from config: {e}")
    
    def _save_values_to_config(self):
        """Save values from UI controls to config."""
        try:
            # Simulation
            self.config.set('Simulation', 'hex_size', str(self.hex_size_spin.value()))
            self.config.set('Simulation', 'turn_duration', str(self.turn_duration_spin.value()))
            self.config.set('Simulation', 'random_seed', str(self.random_seed_spin.value()))
            
            # Display
            self.config.set('Display', 'default_display_mode', self.display_mode_combo.currentText())
            self.config.set('Display', 'show_grid', str(self.show_grid_check.isChecked()).lower())
            self.config.set('Display', 'show_coordinates', str(self.show_coordinates_check.isChecked()).lower())
            self.config.set('Display', 'antialiasing', str(self.antialiasing_check.isChecked()).lower())
            
            # Performance
            self.config.set('Performance', 'los_cache_size', str(self.los_cache_spin.value()))
            self.config.set('Performance', 'animation_fps', str(self.animation_fps_spin.value()))
            self.config.set('Performance', 'max_pathfinding_iterations', str(self.max_pathfinding_spin.value()))
            
            # Units
            self.config.set('Units', 'default_infantry_movement', str(self.infantry_movement_spin.value()))
            self.config.set('Units', 'default_vehicle_movement', str(self.vehicle_movement_spin.value()))
            self.config.set('Units', 'default_sensor_range', str(self.sensor_range_spin.value()))
            
            # Terrain
            self.config.set('Terrain', 'forest_height', str(self.forest_height_spin.value()))
            self.config.set('Terrain', 'building_height', str(self.building_height_spin.value()))
            self.config.set('Terrain', 'max_slope_for_vehicles', str(self.max_slope_spin.value()))
            
            # UI
            self.config.set('UI', 'window_width', str(self.window_width_spin.value()))
            self.config.set('UI', 'window_height', str(self.window_height_spin.value()))
            self.config.set('UI', 'map_view_ratio', str(self.map_ratio_spin.value()))
            self.config.set('UI', 'side_panel_width', str(self.side_panel_width_spin.value()))
            self.config.set('UI', 'default_font_family', self.font_family_edit.text())
            self.config.set('UI', 'default_font_size', str(self.font_size_spin.value()))
            
        except Exception as e:
            self.logger.error(f"Error saving values to config: {e}")
            raise
    
    def _apply_settings(self):
        """Apply current settings."""
        try:
            # Save values to config
            self._save_values_to_config()
            
            # Write config file
            with open(self.config_file, 'w') as f:
                self.config.write(f)
            
            # Convert config to dictionary for signal
            settings_dict = {}
            for section_name in self.config.sections():
                settings_dict[section_name] = dict(self.config.items(section_name))
            
            # Emit settings changed signal
            self.settings_changed.emit(settings_dict)
            
            self.logger.info(f"Settings applied and saved to {self.config_file}")
            QMessageBox.information(self, "Settings Applied", "Settings have been applied successfully.")
            
        except Exception as e:
            self.logger.error(f"Failed to apply settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to apply settings:\n{str(e)}")
    
    def _apply_and_close(self):
        """Apply settings and close dialog."""
        self._apply_settings()
        self.accept()
    
    def _reset_to_defaults(self):
        """Reset all settings to default values."""
        reply = QMessageBox.question(
            self, "Reset Settings",
            "Are you sure you want to reset all settings to default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self._create_default_config()
            self._load_values_from_config()
            self.logger.info("Settings reset to defaults")
    
    def _import_settings(self):
        """Import settings from file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", "",
            "INI Files (*.ini);;All Files (*)"
        )
        
        if file_path:
            try:
                temp_config = configparser.ConfigParser()
                temp_config.read(file_path)
                self.config = temp_config
                self._load_values_from_config()
                self.logger.info(f"Settings imported from {file_path}")
                QMessageBox.information(self, "Import Complete", f"Settings imported from {Path(file_path).name}")
            except Exception as e:
                self.logger.error(f"Failed to import settings: {e}")
                QMessageBox.critical(self, "Import Error", f"Failed to import settings:\n{str(e)}")
    
    def _export_settings(self):
        """Export settings to file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Settings", "wargame_settings.ini",
            "INI Files (*.ini);;All Files (*)"
        )
        
        if file_path:
            try:
                self._save_values_to_config()
                with open(file_path, 'w') as f:
                    self.config.write(f)
                self.logger.info(f"Settings exported to {file_path}")
                QMessageBox.information(self, "Export Complete", f"Settings exported to {Path(file_path).name}")
            except Exception as e:
                self.logger.error(f"Failed to export settings: {e}")
                QMessageBox.critical(self, "Export Error", f"Failed to export settings:\n{str(e)}")