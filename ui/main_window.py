"""
Main window for the wargame simulation application.
"""
import sys
import json
import configparser
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QToolBar, QStatusBar, QMenuBar, QMenu, QMessageBox, QFileDialog,
    QProgressBar, QLabel, QPushButton, QGroupBox, QSpinBox, QDoubleSpinBox,
    QComboBox, QCheckBox, QTextEdit, QDockWidget, QTabWidget, QScrollArea,
    QApplication
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSettings, QDateTime
from PyQt6.QtGui import QAction, QIcon, QPixmap, QKeySequence, QFont, QColor, QPalette

from core.hexgrid import HexGrid
from core.terrain import TerrainAnalyzer
from core.simulation import Simulation, SimulationState
from core.scenario_manager import ScenarioManager
from models.unit import Unit, UnitType, UnitSide, MovementType, Weapon
from ui.map_view import MapView
from ui.side_panel import SidePanel
from ui.settings_dialog import SettingsDialog
from utils.config import get_config
from utils.logger import get_logger, log_exception, get_performance_timer, log_errors, WargameLogger
from utils.icons import get_ui_icon, get_unit_icon, get_icon_manager


class DataLoadingThread(QThread):
    """Thread for loading terrain data without blocking UI."""
    
    progress_updated = pyqtSignal(int, str)
    data_loaded = pyqtSignal(bool, str)
    
    def __init__(self, data_dir: str):
        super().__init__()
        self.data_dir = data_dir
        self.terrain_analyzer = None
        self.hex_grid = None
        self.logger = get_logger('data')
    
    @log_errors('data')
    def run(self):
        """Load terrain data in background thread."""
        try:
            with get_performance_timer('data', 'terrain_data_loading'):
                self.logger.info(f"Starting terrain data loading from: {self.data_dir}")
                
                self.progress_updated.emit(10, "Initializing terrain analyzer...")
                self.terrain_analyzer = TerrainAnalyzer(self.data_dir)
                
                self.progress_updated.emit(30, "Loading DEM and vector data...")
                success = self.terrain_analyzer.load_data()
                
                if not success:
                    self.logger.error("Failed to load terrain data")
                    self.data_loaded.emit(False, "Failed to load terrain data")
                    return
                
                self.progress_updated.emit(50, "Creating hexagonal grid...")
                bounds = self.terrain_analyzer.get_data_bounds()
                
                if not bounds:
                    self.logger.error("No valid data bounds found")
                    self.data_loaded.emit(False, "No valid data bounds found")
                    return
                
                # Use hex_size from config
                config = get_config()
                self.hex_grid = HexGrid(hex_size=config.simulation.hex_size)
                self.hex_grid.generate_grid(bounds)
                self.logger.info(f"Generated hex grid with {len(self.hex_grid)} cells (hex_size={config.simulation.hex_size})")
                
                self.progress_updated.emit(80, "Analyzing terrain for hex cells...")
                self.terrain_analyzer.analyze_grid(self.hex_grid)
                
                self.progress_updated.emit(100, "Terrain analysis complete")
                self.logger.info("Terrain data loading completed successfully")
                self.data_loaded.emit(True, "Terrain data loaded successfully")
                
        except Exception as e:
            self.logger.error(f"Exception during terrain loading: {str(e)}")
            log_exception(e, 'data', 'terrain data loading')
            self.data_loaded.emit(False, f"Error loading data: {str(e)}")


class MainWindow(QMainWindow):
    """
    Main application window for the wargame simulation.
    
    Provides the primary user interface with map view, controls,
    information panels, and simulation management.
    """
    
    def __init__(self):
        super().__init__()
        
        # Initialize logging for UI
        self.logger = get_logger('ui')
        self.logger.info("Initializing MainWindow")
        
        # Core components
        self.hex_grid: Optional[HexGrid] = None
        self.terrain_analyzer: Optional[TerrainAnalyzer] = None
        self.simulation: Optional[Simulation] = None
        self.scenario_manager = ScenarioManager()
        
        # Data for scenario saving
        self.current_roads_data: List[Dict[str, Any]] = []
        self.current_waterways_data: List[Dict[str, Any]] = []
        
        # UI components
        self.map_view: Optional[MapView] = None
        self.side_panel: Optional[SidePanel] = None
        
        # Status and progress
        self.progress_bar: Optional[QProgressBar] = None
        self.status_label: Optional[QLabel] = None
        
        # Enhanced logging UI components
        self.log_display: Optional[QTextEdit] = None
        self.log_tabs: Optional[QTabWidget] = None
        
        # Simulation timer
        self.simulation_timer = QTimer()
        self.simulation_timer.timeout.connect(self._update_simulation)
        
        # Data loading thread
        self.loading_thread: Optional[DataLoadingThread] = None
        
        # Settings
        self.settings = QSettings("WargameSimulation", "MainWindow")
        
        # Current selections
        self.selected_unit: Optional[str] = None
        self.selected_hex: Optional[tuple] = None
        
        # Settings and configuration
        self.current_settings: Dict[str, Any] = {}
        
        # UI state
        self.is_data_loaded = False
        self.is_simulation_running = False
        
        # Connect to logging system
        self._connect_logging_signals()
        
        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._setup_units_toolbar()
        self._setup_status_bar()
        self._connect_signals()
        self._restore_settings()
        self._load_initial_settings()
        
        self.logger.info("MainWindow initialization completed")
    
    def _setup_ui(self):
        """Setup the main user interface layout."""
        # Use config for window size
        config = get_config()
        self.setWindowTitle("Wargame Simulation - Hex-Based Tactical Simulator")
        self.setMinimumSize(config.ui.window_width, config.ui.window_height)
        
        # Central widget with splitter
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Main splitter (horizontal)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(main_splitter)
        
        # Map view (main area)
        self.map_view = MapView()
        main_splitter.addWidget(self.map_view)
        
        # Side panel (right side)
        self.side_panel = SidePanel()
        main_splitter.addWidget(self.side_panel)
        
        # Set splitter proportions using config
        config = get_config()
        map_width = int(config.ui.window_width * config.ui.map_view_ratio)
        panel_width = config.ui.side_panel_width
        main_splitter.setSizes([map_width, panel_width])
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 0)
        
        # Console dock widget (bottom)
        self._setup_console_dock()
        
        # Initial state
        self._set_ui_enabled(False)
    
    def _setup_console_dock(self):
        """Setup enhanced console dock widget for logs and messages."""
        console_dock = QDockWidget("Enhanced Console & Logs", self)
        console_dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        
        # Console widget with tabs
        self.log_tabs = QTabWidget()
        
        # Main log display (all messages)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumHeight(200)
        self.log_display.setFont(QFont("Consolas", 9))
        self.log_tabs.addTab(self.log_display, "All Logs")
        
        # Category-specific logs
        self.ui_log = QTextEdit()
        self.ui_log.setReadOnly(True)
        self.ui_log.setFont(QFont("Consolas", 9))
        self.log_tabs.addTab(self.ui_log, "UI")
        
        self.simulation_log = QTextEdit()
        self.simulation_log.setReadOnly(True)
        self.simulation_log.setFont(QFont("Consolas", 9))
        self.log_tabs.addTab(self.simulation_log, "Simulation")
        
        self.combat_log = QTextEdit()
        self.combat_log.setReadOnly(True)
        self.combat_log.setFont(QFont("Consolas", 9))
        self.log_tabs.addTab(self.combat_log, "Combat")
        
        self.terrain_log = QTextEdit()
        self.terrain_log.setReadOnly(True)
        self.terrain_log.setFont(QFont("Consolas", 9))
        self.log_tabs.addTab(self.terrain_log, "Terrain")
        
        self.error_log = QTextEdit()
        self.error_log.setReadOnly(True)
        self.error_log.setFont(QFont("Consolas", 9))
        # Highlight errors with red background
        error_palette = self.error_log.palette()
        error_palette.setColor(QPalette.ColorRole.Base, QColor(50, 25, 25))
        error_palette.setColor(QPalette.ColorRole.Text, QColor(255, 200, 200))
        self.error_log.setPalette(error_palette)
        self.log_tabs.addTab(self.error_log, "Errors")
        
        self.performance_log = QTextEdit()
        self.performance_log.setReadOnly(True)
        self.performance_log.setFont(QFont("Consolas", 9))
        self.log_tabs.addTab(self.performance_log, "Performance")
        
        # Create control panel for log filtering
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)
        
        # Log level filter
        level_label = QLabel("Log Level:")
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.log_level_combo.setCurrentText("INFO")
        self.log_level_combo.currentTextChanged.connect(self._on_log_level_changed)
        
        # Clear logs button
        clear_btn = QPushButton("Clear Logs")
        clear_btn.clicked.connect(self._clear_logs)
        
        # Export logs button
        export_btn = QPushButton("Export Logs")
        export_btn.clicked.connect(self._export_logs)
        
        # Auto-scroll checkbox
        self.auto_scroll_check = QCheckBox("Auto-scroll")
        self.auto_scroll_check.setChecked(True)
        
        control_layout.addWidget(level_label)
        control_layout.addWidget(self.log_level_combo)
        control_layout.addWidget(clear_btn)
        control_layout.addWidget(export_btn)
        control_layout.addWidget(self.auto_scroll_check)
        control_layout.addStretch()
        
        # Main console widget
        console_widget = QWidget()
        console_layout = QVBoxLayout(console_widget)
        console_layout.addWidget(control_widget)
        console_layout.addWidget(self.log_tabs)
        
        console_dock.setWidget(console_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, console_dock)
    
    def _connect_logging_signals(self):
        """Connect to the logging system signals."""
        try:
            log_emitter = WargameLogger.get_emitter()
            log_emitter.log_message.connect(self._on_log_message)
            self.logger.debug("Connected to logging signals")
        except Exception as e:
            print(f"Failed to connect logging signals: {e}")
    
    def _on_log_message(self, level: str, logger_name: str, message: str):
        """Handle incoming log messages from the logging system."""
        try:
            # Format message with timestamp
            timestamp = QDateTime.currentDateTime().toString("hh:mm:ss.zzz")
            formatted_msg = f"[{timestamp}] [{level}] {message}"
            
            # Add to main log display
            if self.log_display:
                self.log_display.append(formatted_msg)
                if self.auto_scroll_check.isChecked():
                    self.log_display.ensureCursorVisible()
            
            # Route to appropriate category log
            if "ui" in logger_name.lower() and self.ui_log:
                self.ui_log.append(formatted_msg)
                if self.auto_scroll_check.isChecked():
                    self.ui_log.ensureCursorVisible()
            
            elif "simulation" in logger_name.lower() and self.simulation_log:
                self.simulation_log.append(formatted_msg)
                if self.auto_scroll_check.isChecked():
                    self.simulation_log.ensureCursorVisible()
            
            elif "combat" in logger_name.lower() and self.combat_log:
                self.combat_log.append(formatted_msg)
                if self.auto_scroll_check.isChecked():
                    self.combat_log.ensureCursorVisible()
            
            elif "terrain" in logger_name.lower() and self.terrain_log:
                self.terrain_log.append(formatted_msg)
                if self.auto_scroll_check.isChecked():
                    self.terrain_log.ensureCursorVisible()
            
            elif "error" in logger_name.lower() or level in ["ERROR", "CRITICAL"] and self.error_log:
                self.error_log.append(formatted_msg)
                if self.auto_scroll_check.isChecked():
                    self.error_log.ensureCursorVisible()
                # Switch to error tab if it's an error
                if level in ["ERROR", "CRITICAL"]:
                    self.log_tabs.setCurrentWidget(self.error_log)
            
            elif "performance" in logger_name.lower() and self.performance_log:
                self.performance_log.append(formatted_msg)
                if self.auto_scroll_check.isChecked():
                    self.performance_log.ensureCursorVisible()
            
        except Exception as e:
            print(f"Error displaying log message: {e}")
    
    def _on_log_level_changed(self, level_text: str):
        """Handle log level change."""
        try:
            level_map = {
                "DEBUG": 10,
                "INFO": 20,
                "WARNING": 30,
                "ERROR": 40,
                "CRITICAL": 50
            }
            
            if level_text in level_map:
                level_value = level_map[level_text]
                wargame_logger = WargameLogger()
                wargame_logger.set_global_level(level_value)
                self.logger.info(f"Log level changed to {level_text}")
        except Exception as e:
            self.logger.error(f"Failed to change log level: {e}")
    
    def _clear_logs(self):
        """Clear all log displays."""
        try:
            log_widgets = [
                self.log_display, self.ui_log, self.simulation_log,
                self.combat_log, self.terrain_log, self.error_log,
                self.performance_log
            ]
            
            for widget in log_widgets:
                if widget:
                    widget.clear()
            
            self.logger.info("Log displays cleared")
        except Exception as e:
            self.logger.error(f"Failed to clear logs: {e}")
    
    def _export_logs(self):
        """Export logs to file."""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export Logs", f"wargame_logs_{QDateTime.currentDateTime().toString('yyyyMMdd_hhmmss')}.txt",
                "Text Files (*.txt);;All Files (*)"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("=== WARGAME SIMULATION LOGS ===\n")
                    f.write(f"Exported at: {QDateTime.currentDateTime().toString()}\n\n")
                    
                    if self.log_display:
                        f.write("=== ALL LOGS ===\n")
                        f.write(self.log_display.toPlainText())
                        f.write("\n\n")
                
                self.logger.info(f"Logs exported to: {file_path}")
                QMessageBox.information(self, "Export Complete", f"Logs exported to:\n{file_path}")
                
        except Exception as e:
            self.logger.error(f"Failed to export logs: {e}")
            QMessageBox.critical(self, "Export Failed", f"Failed to export logs:\n{str(e)}")
    
    def _setup_menus(self):
        """Setup application menus."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        load_data_action = QAction("Load Terrain Data...", self)
        load_data_action.setShortcut(QKeySequence.StandardKey.Open)
        load_data_action.triggered.connect(self._load_terrain_data)
        file_menu.addAction(load_data_action)
        
        file_menu.addSeparator()
        
        save_scenario_action = QAction("Save Scenario...", self)
        save_scenario_action.setShortcut(QKeySequence.StandardKey.Save)
        save_scenario_action.triggered.connect(self._save_scenario)
        file_menu.addAction(save_scenario_action)
        
        load_scenario_action = QAction("Load Scenario...", self)
        load_scenario_action.triggered.connect(self._load_scenario)
        file_menu.addAction(load_scenario_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Simulation menu
        sim_menu = menubar.addMenu("Simulation")
        
        self.start_sim_action = QAction("Start Simulation", self)
        self.start_sim_action.triggered.connect(self._start_simulation)
        sim_menu.addAction(self.start_sim_action)
        
        self.pause_sim_action = QAction("Pause Simulation", self)
        self.pause_sim_action.triggered.connect(self._pause_simulation)
        sim_menu.addAction(self.pause_sim_action)
        
        self.step_sim_action = QAction("Step Simulation", self)
        self.step_sim_action.triggered.connect(self._step_simulation)
        sim_menu.addAction(self.step_sim_action)
        
        self.reset_sim_action = QAction("Reset Simulation", self)
        self.reset_sim_action.triggered.connect(self._reset_simulation)
        sim_menu.addAction(self.reset_sim_action)
        
        # Units menu
        units_menu = menubar.addMenu("Units")
        
        # Red units submenu
        red_units_menu = units_menu.addMenu("Add Red Unit")
        for unit_type in UnitType:
            action = QAction(f"Red {unit_type.value.replace('_', ' ').title()}", self)
            action.setIcon(get_unit_icon(unit_type.value, "red"))
            action.triggered.connect(lambda checked, ut=unit_type: self._spawn_unit_direct(UnitSide.RED, ut))
            red_units_menu.addAction(action)
        
        # Blue units submenu  
        blue_units_menu = units_menu.addMenu("Add Blue Unit")
        for unit_type in UnitType:
            action = QAction(f"Blue {unit_type.value.replace('_', ' ').title()}", self)
            action.setIcon(get_unit_icon(unit_type.value, "blue"))
            action.triggered.connect(lambda checked, ut=unit_type: self._spawn_unit_direct(UnitSide.BLUE, ut))
            blue_units_menu.addAction(action)
        
        units_menu.addSeparator()
        
        clear_units_action = QAction("Clear All Units", self)
        clear_units_action.triggered.connect(self._clear_all_units)
        units_menu.addAction(clear_units_action)
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in_action.triggered.connect(self._zoom_in)
        view_menu.addAction(zoom_in_action)
        
        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out_action.triggered.connect(self._zoom_out)
        view_menu.addAction(zoom_out_action)
        
        fit_view_action = QAction("Fit to View", self)
        fit_view_action.triggered.connect(self._fit_to_view)
        view_menu.addAction(fit_view_action)
        
        # Settings menu
        settings_menu = menubar.addMenu("Settings")
        
        preferences_action = QAction("Preferences...", self)
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.triggered.connect(self._show_preferences)
        settings_menu.addAction(preferences_action)
        
        settings_menu.addSeparator()
        
        reset_settings_action = QAction("Reset to Defaults", self)
        reset_settings_action.triggered.connect(self._reset_settings)
        settings_menu.addAction(reset_settings_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_toolbar(self):
        """Setup main toolbar with icons."""
        toolbar = QToolBar("Main Toolbar")
        self.addToolBar(toolbar)
        
        # Data loading
        load_data_btn = QPushButton("Load Data")
        load_data_btn.clicked.connect(self._load_terrain_data)
        toolbar.addWidget(load_data_btn)
        
        toolbar.addSeparator()
        
        # Simulation controls with icons
        self.start_btn = QPushButton("Start")
        self.start_btn.setIcon(get_ui_icon("play"))
        self.start_btn.clicked.connect(self._start_simulation)
        toolbar.addWidget(self.start_btn)
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setIcon(get_ui_icon("pause"))
        self.pause_btn.clicked.connect(self._pause_simulation)
        toolbar.addWidget(self.pause_btn)
        
        self.step_btn = QPushButton("Step")
        self.step_btn.setIcon(get_ui_icon("step"))
        self.step_btn.clicked.connect(self._step_simulation)
        toolbar.addWidget(self.step_btn)
        
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setIcon(get_ui_icon("reset"))
        self.reset_btn.clicked.connect(self._reset_simulation)
        toolbar.addWidget(self.reset_btn)
        
        toolbar.addSeparator()
        
        # View controls with icons
        zoom_in_btn = QPushButton("Zoom In")
        zoom_in_btn.setIcon(get_ui_icon("zoom_in"))
        zoom_in_btn.clicked.connect(self._zoom_in)
        toolbar.addWidget(zoom_in_btn)
        
        zoom_out_btn = QPushButton("Zoom Out")
        zoom_out_btn.setIcon(get_ui_icon("zoom_out"))
        zoom_out_btn.clicked.connect(self._zoom_out)
        toolbar.addWidget(zoom_out_btn)
        
        fit_view_btn = QPushButton("Fit View")
        fit_view_btn.setIcon(get_ui_icon("fit_view"))
        fit_view_btn.clicked.connect(self._fit_to_view)
        toolbar.addWidget(fit_view_btn)
        
        toolbar.addSeparator()
        
        # Vector layer controls
        show_roads_btn = QPushButton("Roads")
        show_roads_btn.setCheckable(True)
        show_roads_btn.setChecked(True)  # Start with roads visible
        show_roads_btn.clicked.connect(self._toggle_roads)
        toolbar.addWidget(show_roads_btn)
        
        show_waterways_btn = QPushButton("Waterways")
        show_waterways_btn.setCheckable(True)
        show_waterways_btn.setChecked(True)  # Start with waterways visible
        show_waterways_btn.clicked.connect(self._toggle_waterways)
        toolbar.addWidget(show_waterways_btn)
        
        center_roads_btn = QPushButton("Center on Roads")
        center_roads_btn.clicked.connect(self._center_on_roads)
        toolbar.addWidget(center_roads_btn)
        
        # Initially disable simulation controls
        self._set_simulation_controls_enabled(False)
    
    def _setup_units_toolbar(self):
        """Setup dedicated units toolbar for spawning units."""
        # Create units toolbar
        units_toolbar = self.addToolBar("Units")
        units_toolbar.setObjectName("UnitsToolbar")
        units_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        
        # Position the toolbar below the main toolbar
        self.addToolBarBreak()
        
        # Toolbar title - professional military style
        title_label = QLabel("Units Deployment")
        
        units_toolbar.addWidget(title_label)
        
        units_toolbar.addSeparator()
        
        # Red forces section
        red_label = QLabel("RED FORCES")
        red_label.setStyleSheet("""
            QLabel {
                color: #9B2C2C;
                font-weight: bold;
                margin: 0 5px;
            }
        """)
        units_toolbar.addWidget(red_label)
        
        # Add red unit buttons with professional styling
        for unit_type in UnitType:
            btn = QPushButton(unit_type.value.replace('_', ' ').title())
            btn.setIcon(get_unit_icon(unit_type.value, "red"))
            btn.setToolTip(f"Deploy Red {unit_type.value.replace('_', ' ').title()}")
            
            btn.clicked.connect(lambda checked, ut=unit_type: self._spawn_unit_direct(UnitSide.RED, ut))
            units_toolbar.addWidget(btn)
        
        units_toolbar.addSeparator()
        
        # Blue forces section
        blue_label = QLabel("BLUE FORCES")
        blue_label.setStyleSheet("""
            QLabel {
                font-weight: bold; 
                color: #2C5282; 
                margin: 0 5px; 
            }
        """)
        units_toolbar.addWidget(blue_label)
        
        # Add blue unit buttons with professional styling
        for unit_type in UnitType:
            btn = QPushButton(unit_type.value.replace('_', ' ').title())
            btn.setIcon(get_unit_icon(unit_type.value, "blue"))
            btn.setToolTip(f"Deploy Blue {unit_type.value.replace('_', ' ').title()}")
            btn.clicked.connect(lambda checked, ut=unit_type: self._spawn_unit_direct(UnitSide.BLUE, ut))
            units_toolbar.addWidget(btn)
        
        units_toolbar.addSeparator()
        
        # Clear units button - professional military style
        clear_btn = QPushButton("CLEAR ALL")
        clear_btn.setIcon(get_ui_icon("reset"))
        clear_btn.setToolTip("Remove all units from the battlefield")
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(self._clear_all_units)
        units_toolbar.addWidget(clear_btn)
    
    def _setup_status_bar(self):
        """Setup status bar with progress indicator."""
        status_bar = self.statusBar()
        
        # Status label
        self.status_label = QLabel("Ready")
        status_bar.addWidget(self.status_label)
        
        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_bar.addPermanentWidget(self.progress_bar)
        
        # Simulation info
        self.sim_info_label = QLabel("Simulation: Stopped")
        status_bar.addPermanentWidget(self.sim_info_label)
    
    def _connect_signals(self):
        """Connect UI signals to handlers."""
        # Map view signals
        if self.map_view:
            self.map_view.hex_clicked.connect(self._on_hex_clicked)
            self.map_view.unit_clicked.connect(self._on_unit_clicked)
            self.map_view.unit_move_requested.connect(self._on_unit_move_requested)
            self.map_view.road_selected.connect(self._on_road_selected)
            # TODO: Add waterway_selected signal when implemented in MapView
        
        # Side panel signals
        if self.side_panel:
            self.side_panel.unit_order_issued.connect(self._on_unit_order_issued)
            self.side_panel.display_mode_changed.connect(self._on_display_mode_changed)
            self.side_panel.waterway_highlight_requested.connect(self._on_waterway_highlight_requested)
    
    @log_errors('ui')
    def _load_terrain_data(self, checked=False):
        """Load terrain data from directory."""
        try:
            self.logger.info("Opening terrain data directory dialog")
            data_dir = QFileDialog.getExistingDirectory(
                self, "Select Data Directory", ".", 
                QFileDialog.Option.ShowDirsOnly
            )
            
            if not data_dir:
                self.logger.info("User cancelled data directory selection")
                return
            
            self.logger.info(f"Selected data directory: {data_dir}")
            
            # Validate directory structure
            data_path = Path(data_dir)
            if not (data_path / "DEM").exists() or not (data_path / "Vector").exists():
                error_msg = "Selected directory must contain 'DEM' and 'Vector' subdirectories."
                self.logger.error(f"Invalid directory structure: {error_msg}")
                QMessageBox.warning(
                    self, "Invalid Data Directory", error_msg
                )
                return
            
            # Start loading in background thread
            self._start_data_loading(data_dir)
            
        except Exception as e:
            self.logger.error(f"Error in terrain data loading: {e}")
            log_exception(e, 'ui', 'terrain data loading dialog')
    
    @log_errors('ui')
    def _start_data_loading(self, data_dir: str):
        """Start terrain data loading in background thread."""
        try:
            self.logger.info(f"Starting background data loading for: {data_dir}")
            
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.status_label.setText("Loading terrain data...")
            
            # Disable UI during loading
            self._set_ui_enabled(False)
            
            # Create and start loading thread
            self.loading_thread = DataLoadingThread(data_dir)
            self.loading_thread.progress_updated.connect(self._on_loading_progress)
            self.loading_thread.data_loaded.connect(self._on_data_loaded)
            self.loading_thread.start()
            
        except Exception as e:
            self.logger.error(f"Error starting data loading thread: {e}")
            log_exception(e, 'ui', 'data loading thread startup')
    
    def _on_loading_progress(self, progress: int, message: str):
        """Handle loading progress updates."""
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)
        self.logger.debug(f"Loading progress: {progress}% - {message}")
    
    @log_errors('ui')
    def _on_data_loaded(self, success: bool, message: str):
        """Handle completion of data loading."""
        try:
            self.progress_bar.setVisible(False)
            
            if success:
                self.logger.info("Data loading completed successfully")
                
                # Get loaded data from thread
                self.hex_grid = self.loading_thread.hex_grid
                self.terrain_analyzer = self.loading_thread.terrain_analyzer
                
                # Create simulation
                with get_performance_timer('ui', 'simulation_creation'):
                    self.simulation = Simulation(self.hex_grid)
                    self._connect_simulation_signals()
                
                # Update map view
                if self.map_view:
                    with get_performance_timer('ui', 'map_view_setup'):
                        self.map_view.set_hex_grid(self.hex_grid)
                        self.map_view.set_simulation(self.simulation)
                
                # Update side panel
                if self.side_panel:
                    self.side_panel.set_simulation(self.simulation)
                
                # Enable UI
                self.is_data_loaded = True
                self._set_ui_enabled(True)
                self._set_simulation_controls_enabled(True)
                
                self.status_label.setText("Terrain data loaded successfully")
                self.logger.info(f"Loaded {len(self.hex_grid)} hex cells successfully")
                
            else:
                self.logger.error(f"Data loading failed: {message}")
                self.status_label.setText("Failed to load terrain data")
                QMessageBox.critical(self, "Loading Error", message)
                self._set_ui_enabled(True)
            
            # Clean up thread
            self.loading_thread = None
            
        except Exception as e:
            self.logger.error(f"Error in data loading completion handler: {e}")
            log_exception(e, 'ui', 'data loading completion')
    
    @log_errors('ui')
    def _connect_simulation_signals(self):
        """Connect simulation event signals."""
        if not self.simulation:
            return
        
        try:
            self.simulation.on_unit_moved = self._on_simulation_unit_moved
            self.simulation.on_unit_destroyed = self._on_simulation_unit_destroyed
            self.simulation.on_combat_resolved = self._on_simulation_combat_resolved
            self.simulation.on_turn_completed = self._on_simulation_turn_completed
            self.logger.debug("Simulation signals connected successfully")
        except Exception as e:
            self.logger.error(f"Error connecting simulation signals: {e}")
            log_exception(e, 'ui', 'simulation signal connection')
    
    def _start_simulation(self, checked=False):
        """Start the simulation."""
        if not self.simulation or self.is_simulation_running:
            return
        
        self.simulation.start_simulation()
        self.is_simulation_running = True
        
        # Start timer for real-time updates using config FPS
        config = get_config()
        timer_interval = 1000 // config.performance.animation_fps  # Convert FPS to milliseconds
        self.simulation_timer.start(timer_interval)
        
        self._update_simulation_controls()
        self._log_system("Simulation started")
    
    def _pause_simulation(self, checked=False):
        """Pause or resume the simulation."""
        if not self.simulation:
            return
        
        if self.simulation.state == SimulationState.RUNNING:
            self.simulation.pause_simulation()
            self.simulation_timer.stop()
            self._log_system("Simulation paused")
        elif self.simulation.state == SimulationState.PAUSED:
            self.simulation.resume_simulation()
            self.simulation_timer.start(100)
            self._log_system("Simulation resumed")
        
        self._update_simulation_controls()
    
    def _step_simulation(self, checked=False):
        """Execute one simulation step."""
        if not self.simulation:
            return
        
        self.simulation.step_simulation()
        self._log_system(f"Simulation stepped - Turn {self.simulation.current_turn}")
    
    def _reset_simulation(self, checked=False):
        """Reset the simulation."""
        if not self.simulation:
            return
        
        self.simulation_timer.stop()
        self.simulation.reset_simulation()
        self.is_simulation_running = False
        
        # Update UI
        if self.map_view:
            self.map_view.clear_units()
        
        self._update_simulation_controls()
        self._log_system("Simulation reset")
    
    def _update_simulation(self):
        """Update simulation in real-time mode."""
        if self.simulation and self.simulation.update():
            # Turn was processed
            self._update_ui_state()
    
    def _update_simulation_controls(self):
        """Update simulation control button states."""
        if not self.simulation:
            return
        
        state = self.simulation.state
        
        if state == SimulationState.STOPPED:
            self.start_btn.setText("Start")
            self.start_btn.setEnabled(True)
            self.pause_btn.setText("Pause")
            self.pause_btn.setEnabled(False)
            self.sim_info_label.setText("Simulation: Stopped")
            
        elif state == SimulationState.RUNNING:
            self.start_btn.setText("Start")
            self.start_btn.setEnabled(False)
            self.pause_btn.setText("Pause")
            self.pause_btn.setEnabled(True)
            self.sim_info_label.setText(f"Simulation: Running - Turn {self.simulation.current_turn}")
            
        elif state == SimulationState.PAUSED:
            self.start_btn.setText("Start")
            self.start_btn.setEnabled(False)
            self.pause_btn.setText("Resume")
            self.pause_btn.setEnabled(True)
            self.sim_info_label.setText(f"Simulation: Paused - Turn {self.simulation.current_turn}")
    
    def _update_ui_state(self):
        """Update UI based on current simulation state."""
        self._update_simulation_controls()
        
        if self.map_view:
            self.map_view.update_display()
        
        if self.side_panel:
            self.side_panel.update_display()
    
    def _on_hex_clicked(self, q: int, r: int):
        """Handle hex cell click."""
        self.selected_hex = (q, r)
        
        if self.hex_grid:
            hex_cell = self.hex_grid.get_cell(q, r)
            if hex_cell and self.side_panel:
                self.side_panel.show_hex_info(hex_cell)
    
    def _on_unit_clicked(self, unit_id: str):
        """Handle unit click."""
        self.selected_unit = unit_id
        
        if self.simulation and unit_id in self.simulation.units:
            unit = self.simulation.units[unit_id]
            if self.side_panel:
                self.side_panel.show_unit_info(unit)
    
    def _on_road_selected(self, road_metadata: dict):
        """Handle road selection."""
        if self.side_panel:
            self.side_panel.display_road_info(road_metadata)
    
    def _on_waterway_highlight_requested(self, waterway_name: str, highlight_on: bool):
        """Handle waterway highlighting request."""
        if self.map_view:
            self.map_view.highlight_waterway(waterway_name, highlight_on)
            if highlight_on:
                self._log_system(f"Highlighting waterway: {waterway_name}")
            else:
                self._log_system(f"Removed highlight from waterway: {waterway_name}")
    
    def _on_waterway_selected(self, waterway_metadata: dict, segments: list):
        """Handle waterway selection."""
        if self.side_panel:
            self.side_panel.display_waterway_info(waterway_metadata, segments)
    
    def _on_unit_move_requested(self, unit_id: str, target_q: int, target_r: int):
        """Handle unit movement request from map."""
        if self.simulation:
            success = self.simulation.issue_movement_order(unit_id, target_q, target_r)
            if success:
                self._log_system(f"Movement order issued for unit {unit_id}")
                # Immediately update arrow display when movement order is issued
                if self.map_view:
                    self.map_view.update_display()
            else:
                self._log_system(f"Invalid movement order for unit {unit_id}")
    
    def _on_unit_order_issued(self, order_type: str, kwargs: dict):
        """Handle unit orders from side panel."""
        print(f"DEBUG: _on_unit_order_issued called with order_type='{order_type}', kwargs={kwargs}")
        if not self.simulation:
            print("DEBUG: No simulation available")
            return
        
        if order_type == "enter_movement_mode" and "unit_id" in kwargs:
            print(f"DEBUG: Entering movement mode for unit {kwargs['unit_id']}")
            # Enter movement mode for the unit (same as right-click context menu)
            if self.map_view:
                self.map_view.enter_movement_mode(kwargs["unit_id"])
            else:
                print("DEBUG: No map_view available")
        
        elif order_type == "move" and "unit_id" in kwargs and "target" in kwargs:
            target_q, target_r = kwargs["target"]
            self.simulation.issue_movement_order(kwargs["unit_id"], target_q, target_r)
            # Immediately update arrow display when movement order is issued from side panel
            if self.map_view:
                self.map_view.update_display()
        
        elif order_type == "attack" and "attacker_id" in kwargs and "target_id" in kwargs:
            self.simulation.issue_attack_order(kwargs["attacker_id"], kwargs["target_id"])
    
    def _on_display_mode_changed(self, display_mode_name: str):
        """Handle display mode change from side panel."""
        if self.map_view:
            # Convert display mode name to enum
            from ui.map_view import DisplayMode
            mode_mapping = {
                "Terrain": DisplayMode.TERRAIN,
                "Elevation": DisplayMode.ELEVATION,
                "Movement Cost": DisplayMode.MOVEMENT_COST,
                "Cover": DisplayMode.COVER,
                "LOS Blocking": DisplayMode.LOS_BLOCKING,
                "Control": DisplayMode.CONTROL
            }
            
            display_mode = mode_mapping.get(display_mode_name, DisplayMode.TERRAIN)
            self.map_view.set_display_mode(display_mode)
    
    def _on_simulation_unit_moved(self, unit_id: str, from_pos, to_pos):
        """Handle unit movement in simulation."""
        self._log_simulation(f"Unit {unit_id} moved from {from_pos} to {to_pos}")
        
        if self.map_view:
            self.map_view.update_unit_position(unit_id, to_pos)
    
    def _on_simulation_unit_destroyed(self, unit_id: str):
        """Handle unit destruction in simulation."""
        if self.simulation and unit_id in self.simulation.units:
            unit = self.simulation.units[unit_id]
            self._log_combat(f"Unit {unit.name} destroyed")
            
            if self.map_view:
                self.map_view.remove_unit(unit_id)
    
    def _on_simulation_combat_resolved(self, combat_result):
        """Handle combat resolution in simulation."""
        attacker = self.simulation.units.get(combat_result.attacker_id)
        target = self.simulation.units.get(combat_result.target_id)
        
        if attacker and target:
            result_text = f"{attacker.name} {'hit' if combat_result.hit else 'missed'} {target.name}"
            if combat_result.hit:
                result_text += f" for {combat_result.damage_dealt:.1f} damage"
            
            self._log_combat(result_text)
    
    def _on_simulation_turn_completed(self, turn: int):
        """Handle turn completion in simulation."""
        self._log_simulation(f"Turn {turn} completed")
        self._update_ui_state()
    
    def _spawn_unit_direct(self, side: UnitSide, unit_type: UnitType):
        """Directly spawn a unit of specific type and side without dialog."""
        if not self.simulation or not self.hex_grid:
            return
        
        # Get position - use selected hex or find random empty hex
        if self.selected_hex:
            q, r = self.selected_hex
        else:
            # Find a random empty hex
            empty_hexes = [cell for cell in self.hex_grid if cell.occupied_by is None]
            if not empty_hexes:
                QMessageBox.warning(self, "No Space", "No empty hex cells available")
                return
            
            import random
            hex_cell = random.choice(empty_hexes)
            q, r = hex_cell.q, hex_cell.r
        
        # Create unit of specified type
        unit = Unit(
            name=f"{side.value.title()} {unit_type.value.replace('_', ' ').title()} {len(self.simulation.units) + 1}",
            unit_type=unit_type,
            side=side
        )
        
        # Add to simulation
        success = self.simulation.add_unit(unit, q, r)
        if success:
            # Add to map view
            if self.map_view:
                self.map_view.add_unit(unit)
            
            self._log_system(f"Spawned {unit.name} at ({q}, {r})")
        else:
            QMessageBox.warning(self, "Cannot Add Unit", "Cannot place unit at selected location")
    
    def _clear_all_units(self, checked=False):
        """Clear all units from simulation."""
        if not self.simulation:
            return
        
        # Remove all units
        unit_ids = list(self.simulation.units.keys())
        for unit_id in unit_ids:
            self.simulation.remove_unit(unit_id)
        
        # Clear from map view
        if self.map_view:
            self.map_view.clear_units()
        
        self._log_system("All units cleared")
    
    def _zoom_in(self, checked=False):
        """Zoom in map view."""
        if self.map_view:
            self.map_view.zoom_in()
    
    def _zoom_out(self, checked=False):
        """Zoom out map view."""
        if self.map_view:
            self.map_view.zoom_out()
    
    def _fit_to_view(self, checked=False):
        """Fit map to view."""
        if self.map_view:
            self.map_view.fit_in_view()
    
    def _toggle_roads(self, checked=False):
        """Toggle road visibility."""
        print(f"Main window: Roads button clicked, checked={checked}")
        if self.map_view:
            self.map_view.set_show_roads(checked)
            self._log_system(f"Roads {'shown' if checked else 'hidden'}")
    
    def _toggle_waterways(self, checked=False):
        """Toggle waterway visibility."""
        print(f"Main window: Waterways button clicked, checked={checked}")
        if self.map_view:
            self.map_view.set_show_waterways(checked)
            self._log_system(f"Waterways {'shown' if checked else 'hidden'}")
    
    def _center_on_roads(self, checked=False):
        """Center view on road network."""
        if self.map_view:
            self.map_view.center_on_roads()
            self._log_system("Centered view on roads")
    
    def _save_scenario(self, checked=False):
        """Save comprehensive scenario including terrain, roads, waterways, and settings."""
        if not self.hex_grid or not self.terrain_analyzer:
            QMessageBox.warning(self, "Save Scenario", 
                              "No terrain data to save. Please load terrain data first.")
            return
        
        # Get save file path
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Scenario", 
            f"scenario_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Scenario Files (*.json);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            # Prepare metadata
            metadata = {
                "name": Path(file_path).stem,
                "description": "Comprehensive wargame scenario with terrain, roads, waterways, and settings",
                "created_by": "Wargame Application",
                "terrain_source": str(self.terrain_analyzer.data_dir) if self.terrain_analyzer.data_dir else "Unknown"
            }
            
            # Get current application settings
            app_settings = self._get_current_app_settings()
            
            # Prepare roads and waterways data
            roads_data = self._prepare_roads_data_for_save()
            waterways_data = self._prepare_waterways_data_for_save()
            
            # Save using scenario manager
            success = self.scenario_manager.save_scenario(
                scenario_path=file_path,
                hex_grid=self.hex_grid,
                terrain_analyzer=self.terrain_analyzer,
                roads_data=roads_data.get('roads', []),  # Extract list from dict
                waterways_data=waterways_data.get('waterways', []),  # Extract list from dict
                app_settings=app_settings,
                metadata=metadata
            )
            
            if success:
                self.logger.info(f"Comprehensive scenario saved to: {file_path}")
                
                # Calculate statistics safely
                roads_count = len(roads_data.get('roads', [])) if roads_data else 0
                waterways_count = len(waterways_data.get('waterways', [])) if waterways_data else 0
                
                QMessageBox.information(
                    self, "Save Scenario", 
                    f"Scenario saved successfully!\n\n"
                    f"File: {Path(file_path).name}\n"
                    f"Hex cells: {len(self.hex_grid.cells) if self.hex_grid else 0}\n"
                    f"Roads: {roads_count}\n"
                    f"Waterways: {waterways_count}\n"
                    f"Settings included: Yes"
                )
            else:
                QMessageBox.critical(self, "Save Error", "Failed to save scenario. Check logs for details.")
                
        except Exception as e:
            self.logger.error(f"Failed to save comprehensive scenario: {e}")
            QMessageBox.critical(
                self, "Save Error", 
                f"Failed to save scenario:\n{str(e)}"
            )

    def _load_scenario(self, checked=False):
        """Load comprehensive scenario including terrain regeneration."""
        # Get load file path
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Scenario", "",
            "JSON Scenario Files (*.json);;Legacy Scenario Files (*.scenario *.scenario.gz);;All Files (*)"
        )
        
        if not file_path:
            return
        
        if not Path(file_path).exists():
            QMessageBox.warning(self, "Load Scenario", "Selected file does not exist.")
            return
        
        try:
            # Load scenario data
            scenario_data = self.scenario_manager.load_scenario(file_path)
            if not scenario_data:
                QMessageBox.critical(self, "Load Error", "Failed to load scenario file.")
                return
            
            # Show loading progress
            if self.progress_bar:
                self.progress_bar.setVisible(True)
                self.progress_bar.setValue(10)
            if self.status_label:
                self.status_label.setText("Loading scenario...")
            
            # Regenerate terrain from scenario
            self._update_progress(20, "Regenerating terrain...")
            regenerated_hex_grid = self.scenario_manager.regenerate_terrain_from_scenario(scenario_data)
            
            if regenerated_hex_grid:
                self.hex_grid = regenerated_hex_grid
                self._update_progress(40, "Terrain regenerated successfully")
            else:
                QMessageBox.warning(self, "Load Warning", 
                                  "Failed to regenerate terrain. Using existing terrain if available.")
            
            # Load roads and waterways data
            self._update_progress(60, "Loading roads and waterways...")
            self._load_roads_and_waterways_from_scenario(scenario_data)
            
            # Apply settings
            self._update_progress(80, "Applying settings...")
            self._apply_scenario_settings(scenario_data)
            
            # Update map view with regenerated data
            if self.map_view and self.hex_grid:
                self._update_progress(90, "Updating map display...")
                self.map_view.set_hex_grid(self.hex_grid)
                self.map_view.update_display()
            
            # Complete
            self._update_progress(100, "Scenario loaded successfully")
            
            # Show success message
            stats = scenario_data.get('statistics', {})
            terrain_stats = stats.get('terrain', {})
            
            QMessageBox.information(
                self, "Load Scenario",
                f"Scenario loaded successfully!\n\n"
                f"File: {Path(file_path).name}\n"
                f"Hex cells: {terrain_stats.get('total_hex_cells', 'Unknown')}\n"
                f"Roads: {len(scenario_data.get('roads', {}).get('roads', []))}\n"
                f"Waterways: {len(scenario_data.get('waterways', {}).get('waterways', []))}\n"
                f"Created: {scenario_data.get('timestamp', 'Unknown')}"
            )
            
            self.logger.info(f"Comprehensive scenario loaded from: {file_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to load scenario: {e}")
            QMessageBox.critical(
                self, "Load Error",
                f"Failed to load scenario:\n{str(e)}"
            )
        finally:
            # Hide progress
            if self.progress_bar:
                self.progress_bar.setVisible(False)
            if self.status_label:
                self.status_label.setText("Ready")

    def _update_progress(self, value, message=""):
        """Update progress bar and status message."""
        if self.progress_bar:
            self.progress_bar.setValue(value)
        if self.status_label and message:
            self.status_label.setText(message)
        QApplication.processEvents()  # Allow UI to update
    
    def _load_roads_and_waterways_from_scenario(self, scenario_data):
        """Load roads and waterways from scenario data."""
        try:
            # Load roads
            roads_data = scenario_data.get('roads', {})
            if roads_data.get('roads'):
                # Convert roads data back to GeoDataFrame if needed
                # This would depend on your specific data structure
                self.logger.info(f"Loaded {len(roads_data['roads'])} roads from scenario")
            
            # Load waterways  
            waterways_data = scenario_data.get('waterways', {})
            if waterways_data.get('waterways'):
                # Convert waterways data back to GeoDataFrame if needed
                self.logger.info(f"Loaded {len(waterways_data['waterways'])} waterways from scenario")
                
        except Exception as e:
            self.logger.error(f"Failed to load roads/waterways from scenario: {e}")
    
    def _apply_scenario_settings(self, scenario_data):
        """Apply settings from scenario data."""
        try:
            settings = scenario_data.get('app_settings', {})
            if not settings:
                return
            
            # Apply view settings
            view_settings = settings.get('view', {})
            if view_settings and self.map_view:
                if 'show_grid' in view_settings:
                    # Apply grid visibility if map_view supports it
                    pass
                if 'show_coordinates' in view_settings:
                    # Apply coordinate visibility if map_view supports it
                    pass
            
            # Apply other settings as needed
            self.logger.info("Applied scenario settings")
            
        except Exception as e:
            self.logger.error(f"Failed to apply scenario settings: {e}")
    
    def _get_current_app_settings(self):
        """Get current application settings for saving."""
        try:
            settings = {
                'version': '1.0',
                'view': {
                    'show_grid': True,  # Default values
                    'show_coordinates': False,
                    'zoom_level': 1.0
                },
                'terrain': {
                    'analysis_enabled': True,
                    'classification_method': 'elevation_slope'
                }
            }
            
            # Add any specific settings from your application
            return settings
            
        except Exception as e:
            self.logger.error(f"Failed to get app settings: {e}")
            return {}
    
    def _prepare_roads_data_for_save(self):
        """Prepare roads data for scenario saving."""
        try:
            # This should extract roads data from your current application state
            # Return format should match what ScenarioManager expects
            roads_data = {
                'roads': [],
                'metadata': {
                    'total_roads': 0,
                    'road_types': []
                }
            }
            
            # Add logic to extract actual roads data from your application
            return roads_data
            
        except Exception as e:
            self.logger.error(f"Failed to prepare roads data: {e}")
            return {'roads': [], 'metadata': {'total_roads': 0, 'road_types': []}}
    
    def _prepare_waterways_data_for_save(self):
        """Prepare waterways data for scenario saving."""
        try:
            # This should extract waterways data from your current application state  
            # Return format should match what ScenarioManager expects
            waterways_data = {
                'waterways': [],
                'metadata': {
                    'total_waterways': 0,
                    'waterway_types': []
                }
            }
            
            # Add logic to extract actual waterways data from your application
            return waterways_data
            
        except Exception as e:
            self.logger.error(f"Failed to prepare waterways data: {e}")
            return {'waterways': [], 'metadata': {'total_waterways': 0, 'waterway_types': []}}

    
    def _validate_scenario_data(self, scenario_data: dict) -> bool:
        """Validate scenario data structure."""
        try:
            # Check required fields
            if "metadata" not in scenario_data:
                QMessageBox.warning(self, "Invalid Scenario", "Scenario file missing metadata.")
                return False
            
            if "units" not in scenario_data:
                QMessageBox.warning(self, "Invalid Scenario", "Scenario file missing units data.")
                return False
            
            # Check version compatibility
            metadata = scenario_data["metadata"]
            version = metadata.get("version", "unknown")
            if version != "1.0":
                reply = QMessageBox.question(
                    self, "Version Warning", 
                    f"Scenario was created with version {version}. "
                    f"Current version is 1.0. Continue loading?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return False
            
            return True
            
        except Exception as e:
            QMessageBox.critical(
                self, "Validation Error", 
                f"Error validating scenario file:\n{str(e)}"
            )
            return False
    
    def _show_about(self, checked=False):
        """Show about dialog."""
        QMessageBox.about(
            self, "About Wargame Simulation",
            "Wargame Simulation v1.0\n\n"
            "A hex-based tactical military simulation using real terrain data.\n\n"
            "Features:\n"
            "• Hexagonal grid-based movement\n"
            "• Real DEM and vector data integration\n"
            "• Line-of-sight calculations\n"
            "• A* pathfinding\n"
            "• Combat simulation\n\n"
            "Built with Python, PyQt6, and GIS libraries."
        )
    
    def _show_preferences(self, checked=False):
        """Show settings/preferences dialog."""
        try:
            settings_dialog = SettingsDialog(self, "config.ini")
            settings_dialog.settings_changed.connect(self._on_settings_changed)
            settings_dialog.exec()
        except Exception as e:
            self.logger.error(f"Failed to show preferences dialog: {e}")
            QMessageBox.critical(
                self, "Settings Error",
                f"Failed to open settings dialog:\n{str(e)}"
            )
    
    def _reset_settings(self, checked=False):
        """Reset settings to defaults."""
        reply = QMessageBox.question(
            self, "Reset Settings",
            "Are you sure you want to reset all settings to default values?\n"
            "This will restart the application with default configuration.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Remove config file to force defaults
                config_file = Path("config.ini")
                if config_file.exists():
                    config_file.unlink()
                
                self.logger.info("Settings reset to defaults")
                QMessageBox.information(
                    self, "Settings Reset",
                    "Settings have been reset to defaults.\n"
                    "Please restart the application for changes to take effect."
                )
                
            except Exception as e:
                self.logger.error(f"Failed to reset settings: {e}")
                QMessageBox.critical(
                    self, "Reset Error",
                    f"Failed to reset settings:\n{str(e)}"
                )
    
    def _on_settings_changed(self, settings: Dict[str, Any]):
        """Handle settings changes from the settings dialog."""
        try:
            self.current_settings = settings
            self.logger.info("Settings updated from preferences dialog")
            
            # Apply settings that can be changed immediately
            self._apply_display_settings(settings.get('Display', {}))
            self._apply_ui_settings(settings.get('UI', {}))
            self._apply_performance_settings(settings.get('Performance', {}))
            
            # Log settings that require restart
            restart_needed = []
            if 'Simulation' in settings:
                restart_needed.append("Simulation parameters")
            if 'Terrain' in settings:
                restart_needed.append("Terrain analysis")
            if 'Units' in settings:
                restart_needed.append("Unit defaults")
            
            if restart_needed:
                QMessageBox.information(
                    self, "Settings Applied",
                    f"Settings have been applied.\n\n"
                    f"The following changes will take effect after restart:\n"
                    f"• {', '.join(restart_needed)}"
                )
            
        except Exception as e:
            self.logger.error(f"Failed to apply settings: {e}")
            QMessageBox.critical(
                self, "Settings Error",
                f"Failed to apply settings:\n{str(e)}"
            )
    
    def _apply_display_settings(self, display_settings: Dict[str, str]):
        """Apply display settings immediately."""
        try:
            if self.map_view and display_settings:
                # Apply display mode
                if 'default_display_mode' in display_settings:
                    mode_name = display_settings['default_display_mode']
                    self._on_display_mode_changed(mode_name)
                
                # Apply grid and coordinate visibility
                if hasattr(self.map_view, 'set_grid_visible'):
                    show_grid = display_settings.get('show_grid', 'true').lower() == 'true'
                    self.map_view.set_grid_visible(show_grid)
                
                if hasattr(self.map_view, 'set_coordinates_visible'):
                    show_coords = display_settings.get('show_coordinates', 'false').lower() == 'true'
                    self.map_view.set_coordinates_visible(show_coords)
                
                self.logger.debug("Display settings applied")
                
        except Exception as e:
            self.logger.error(f"Failed to apply display settings: {e}")
    
    def _apply_ui_settings(self, ui_settings: Dict[str, str]):
        """Apply UI settings immediately."""
        try:
            if ui_settings:
                # Apply font settings
                if 'default_font_family' in ui_settings and 'default_font_size' in ui_settings:
                    font_family = ui_settings['default_font_family']
                    font_size = int(ui_settings.get('default_font_size', 9))
                    
                    # Apply to console and log displays
                    font = QFont(font_family, font_size)
                    if hasattr(self, 'log_display') and self.log_display:
                        self.log_display.setFont(font)
                    if hasattr(self, 'ui_log') and self.ui_log:
                        self.ui_log.setFont(font)
                    if hasattr(self, 'simulation_log') and self.simulation_log:
                        self.simulation_log.setFont(font)
                
                self.logger.debug("UI settings applied")
                
        except Exception as e:
            self.logger.error(f"Failed to apply UI settings: {e}")
    
    def _apply_performance_settings(self, performance_settings: Dict[str, str]):
        """Apply performance settings immediately."""
        try:
            if performance_settings:
                # Apply animation FPS
                if 'animation_fps' in performance_settings:
                    fps = int(performance_settings['animation_fps'])
                    if hasattr(self, 'simulation_timer') and self.simulation_timer:
                        # Update timer interval (1000ms / fps)
                        interval = max(10, 1000 // fps)  # Minimum 10ms interval
                        if self.simulation_timer.isActive():
                            self.simulation_timer.stop()
                            self.simulation_timer.start(interval)
                
                self.logger.debug("Performance settings applied")
                
        except Exception as e:
            self.logger.error(f"Failed to apply performance settings: {e}")
    
    def _load_initial_settings(self):
        """Load initial settings from config file."""
        try:
            config_file = Path("config.ini")
            if config_file.exists():
                import configparser
                config = configparser.ConfigParser()
                config.read(config_file)
                
                # Convert to dictionary
                settings = {}
                for section_name in config.sections():
                    settings[section_name] = dict(config.items(section_name))
                
                self.current_settings = settings
                
                # Apply initial settings
                self._apply_display_settings(settings.get('Display', {}))
                self._apply_ui_settings(settings.get('UI', {}))
                self._apply_performance_settings(settings.get('Performance', {}))
                
                self.logger.info("Initial settings loaded and applied")
                
        except Exception as e:
            self.logger.error(f"Failed to load initial settings: {e}")
    
    def _set_ui_enabled(self, enabled: bool):
        """Enable or disable UI elements."""
        # This would enable/disable various UI elements
        pass
    
    def _set_simulation_controls_enabled(self, enabled: bool):
        """Enable or disable simulation controls."""
        self.start_btn.setEnabled(enabled and self.is_data_loaded)
        self.step_btn.setEnabled(enabled and self.is_data_loaded)
        self.reset_btn.setEnabled(enabled and self.is_data_loaded)
    
    def _log_system(self, message: str):
        """Log system message."""
        self.logger.info(message)
        if self.log_display:
            timestamp = self._get_timestamp()
            self.log_display.append(f"[{timestamp}] SYSTEM: {message}")
            self.log_display.ensureCursorVisible()
    
    def _log_simulation(self, message: str):
        """Log simulation message."""
        self.logger.info(message)
        turn = self.simulation.current_turn if self.simulation else 0
        formatted_msg = f"[Turn {turn}] {message}"
        
        # Log to main display
        if self.log_display:
            self.log_display.append(f"SIMULATION: {formatted_msg}")
            self.log_display.ensureCursorVisible()
        
        # Log to simulation-specific tab
        if self.simulation_log:
            self.simulation_log.append(formatted_msg)
            self.simulation_log.ensureCursorVisible()
    
    def _log_combat(self, message: str):
        """Log combat message."""
        self.logger.info(message)
        timestamp = self._get_timestamp()
        formatted_msg = f"[{timestamp}] {message}"
        
        # Log to main display
        if self.log_display:
            self.log_display.append(f"COMBAT: {formatted_msg}")
            self.log_display.ensureCursorVisible()
        
        # Log to combat-specific tab
        if self.combat_log:
            self.combat_log.append(formatted_msg)
            self.combat_log.ensureCursorVisible()
    
    def _get_timestamp(self) -> str:
        """Get current timestamp string."""
        import datetime
        return datetime.datetime.now().strftime("%H:%M:%S")
    
    def _save_settings(self):
        """Save window settings."""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
    
    def _restore_settings(self):
        """Restore window settings."""
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        window_state = self.settings.value("windowState")
        if window_state:
            self.restoreState(window_state)
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Stop simulation
        if self.simulation:
            self.simulation_timer.stop()
            self.simulation.stop_simulation()
        
        # Save settings
        self._save_settings()
        
        # Accept close event
        event.accept()