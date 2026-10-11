#!/usr/bin/env python3
"""
Wargame Simulation - Main Application Entry Point

A complete hex-based tactical military simulation using real terrain data.
Provides interactive visualization, unit management, pathfinding, line-of-sight
calculations, and combat simulation.

Features:
- Hexagonal grid-based terrain modeling
- Real DEM and vector data integration  
- Interactive PyQt6 GUI
- A* pathfinding
- Line-of-sight calculations
- Combat simulation and detection systems

Usage:
    python main.py [--data-dir DATA_DIR] [--debug] [--fullscreen]

Author: Wargame Simulation Team
Version: 1.0
"""

import sys
import os
import argparse
import logging
from pathlib import Path
from typing import Optional

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QIcon, QFont

# Import enhanced logging system
from utils.logger import setup_logging as setup_enhanced_logging, get_logger, log_exception

from ui.main_window import MainWindow


def setup_logging(debug: bool = False) -> None:
    """
    Setup enhanced application logging.
    
    Args:
        debug: Enable debug level logging
    """
    try:
        # Use enhanced logging system
        setup_enhanced_logging(debug=debug)
        logger = get_logger('main')
        logger.info(f"Enhanced logging system initialized (debug={debug})")
        
        # Also setup basic Python logging for fallback
        log_level = logging.DEBUG if debug else logging.INFO
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
        # Create logs directory
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Configure basic logging as backup
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[
                logging.FileHandler(log_dir / "basic.log", encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        logger.info("Backup logging system also configured")
        
    except Exception as e:
        # Fallback to basic logging if enhanced logging fails
        print(f"Enhanced logging setup failed: {e}")
        log_level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
        logging.error(f"Fallback to basic logging due to: {e}")
    
    # Create logs directory if it doesn't exist
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    # Setup logging to file and console
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(logs_dir / "wargame.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Logging initialized")


def check_dependencies() -> bool:
    """
    Check if all required dependencies are available.
    
    Returns:
        True if all dependencies are available, False otherwise
    """
    required_modules = [
        'PyQt6',
        'numpy',
        'matplotlib',
        'geopandas',
        'shapely',
        'rasterio'
    ]
    
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        print("Error: Missing required dependencies:")
        for module in missing_modules:
            print(f"  - {module}")
        print("\nPlease install missing dependencies using:")
        print("pip install -r requirements.txt")
        return False
    
    return True


def create_splash_screen(app: QApplication) -> QSplashScreen:
    """
    Create and show splash screen.
    
    Args:
        app: QApplication instance
        
    Returns:
        QSplashScreen instance
    """
    # Create a simple splash screen
    # In a full application, this would use a proper image
    splash_pixmap = QPixmap(400, 300)
    splash_pixmap.fill(Qt.GlobalColor.darkBlue)
    
    splash = QSplashScreen(splash_pixmap)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    
    # Show splash with message
    splash.show()
    splash.showMessage(
        "Wargame Simulation\nLoading...",
        Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom,
        Qt.GlobalColor.white
    )
    
    app.processEvents()
    return splash


def setup_application_style(app: QApplication) -> None:
    """
    Setup application style and appearance.
    
    Args:
        app: QApplication instance
    """
    # Set application properties
    app.setApplicationName("Wargame Simulation")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Wargame Simulation Team")
    
    # Set default font
    font = QFont("Arial", 9)
    app.setFont(font)
    
    # Set application icon (if available)
    icon_path = project_root / "ui" / "icons" / "app_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    # Set style sheet for dark theme (optional)
    # This could be loaded from a separate CSS file
    dark_style = """
    QMainWindow {
        background-color: #2b2b2b;
        color: #ffffff;
    }
    QGroupBox {
        border: 1px solid #555555;
        border-radius: 5px;
        margin-top: 10px;
        padding-top: 10px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px 0 5px;
    }
    QPushButton {
        background-color: #404040;
        border: 1px solid #555555;
        border-radius: 3px;
        padding: 5px;
        min-width: 80px;
    }
    QPushButton:hover {
        background-color: #505050;
    }
    QPushButton:pressed {
        background-color: #353535;
    }
    QProgressBar {
        border: 1px solid #555555;
        border-radius: 3px;
        text-align: center;
    }
    QProgressBar::chunk {
        background-color: #4CAF50;
        border-radius: 2px;
    }
    """
    
    # Uncomment to use dark theme
    # app.setStyleSheet(dark_style)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Wargame Simulation - Hex-based tactical military simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py
  python main.py --data-dir ./sample_data --debug
  python main.py --fullscreen
        """
    )
    
    parser.add_argument(
        "--data-dir",
        type=str,
        help="Directory containing DEM and Vector subdirectories with terrain data"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Start application in fullscreen mode"
    )
    
    parser.add_argument(
        "--no-splash",
        action="store_true",
        help="Skip splash screen"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="Wargame Simulation 1.0"
    )
    
    return parser.parse_args()


def show_welcome_message() -> None:
    """Show welcome message with basic usage instructions."""
    msg = QMessageBox()
    msg.setWindowTitle("Welcome to Wargame Simulation")
    msg.setIcon(QMessageBox.Icon.Information)
    
    welcome_text = """
Welcome to Wargame Simulation!

To get started:

1. Load terrain data using File → Load Terrain Data...
   Your data directory should contain:
   - DEM/ folder with .tif elevation files
   - Vector/ folder with .shp files (roads, buildings, etc.)

2. Once data is loaded, you can:
   - Add units using the toolbar buttons
   - Click on hexes to see terrain information
   - Click on units to see unit details
   - Start the simulation to see units interact

Controls:
- Mouse wheel: Zoom in/out
- Left click: Select hexes or units
- Right click: Context menu
- ESC: Clear selections

Enjoy your tactical simulation experience!
    """
    
    msg.setText(welcome_text)
    msg.exec()


def main() -> int:
    """
    Enhanced main application entry point with comprehensive error handling.
    
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Parse command line arguments
        args = parse_arguments()
        
        # Setup enhanced logging
        setup_logging(args.debug)
        logger = get_logger('main')
        logger.info("=== WARGAME SIMULATION STARTING ===")
        logger.info(f"Arguments: {vars(args)}")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Working directory: {os.getcwd()}")
        
        # Check dependencies with enhanced error handling
        logger.info("Checking dependencies...")
        if not check_dependencies():
            logger.error("Dependency check failed")
            return 1
        logger.info("All dependencies satisfied")
        
        # Create QApplication with error handling
        logger.info("Creating QApplication...")
        app = QApplication(sys.argv)
        logger.info("QApplication created successfully")
        
        # Setup global exception handler for Qt
        def handle_qt_exception(exc_type, exc_value, exc_traceback):
            """Global Qt exception handler."""
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            
            logger.critical("Unhandled Qt exception", exc_info=(exc_type, exc_value, exc_traceback))
            log_exception(Exception(exc_value), 'main', 'Qt application')
            
            # Show error dialog
            error_msg = f"An unexpected error occurred:\n\n{exc_type.__name__}: {exc_value}"
            QMessageBox.critical(None, "Critical Error", error_msg)
        
        sys.excepthook = handle_qt_exception
        
        # Setup application style and properties
        setup_application_style(app)
        
        # Show splash screen (unless disabled)
        splash = None
        if not args.no_splash:
            try:
                logger.info("Creating splash screen...")
                splash = create_splash_screen(app)
                if splash:
                    logger.info("Splash screen displayed")
            except Exception as e:
                logger.warning(f"Failed to create splash screen: {e}")
                # Continue without splash screen
        
        # Create main window with error handling
        try:
            logger.info("Creating main window...")
            if splash:
                splash.showMessage("Initializing Main Window...", Qt.AlignmentFlag.AlignBottom)
                app.processEvents()
            
            main_window = MainWindow()
            logger.info("Main window created successfully")
            
            # Configure main window based on arguments
            if args.fullscreen:
                logger.info("Starting in fullscreen mode")
                main_window.showFullScreen()
            else:
                main_window.show()
            
            # Close splash screen
            if splash:
                splash.finish(main_window)
                logger.info("Splash screen closed")
            
            # Show welcome message
            QTimer.singleShot(500, show_welcome_message)
            
            # Auto-load data if specified
            if args.data_dir:
                data_path = Path(args.data_dir)
                if data_path.exists():
                    logger.info(f"Auto-loading data from {data_path}")
                    # Schedule data loading after a short delay
                    QTimer.singleShot(1000, lambda: auto_load_data(main_window, str(data_path)))
                else:
                    logger.warning(f"Specified data directory does not exist: {data_path}")
                    QMessageBox.warning(
                        main_window,
                        "Data Directory Not Found",
                        f"The specified data directory was not found:\n{data_path}"
                    )
            
            logger.info("Application initialization completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to create main window: {e}")
            log_exception(e, 'main', 'main window creation')
            if splash:
                splash.close()
            return 1
        
        # Start event loop
        logger.info("Starting application event loop...")
        exit_code = app.exec()
        logger.info(f"Application exited with code: {exit_code}")
        return exit_code
        
    except Exception as e:
        # Handle any unhandled exceptions at the top level
        error_msg = f"Fatal error in main(): {str(e)}"
        print(error_msg, file=sys.stderr)
        
        try:
            if 'logger' in locals():
                logger.critical(error_msg)
                log_exception(e, 'main', 'top-level main function')
            else:
                # Fallback logging
                logging.error(error_msg, exc_info=True)
        except:
            # Even logging failed, just print
            print(f"Logging also failed. Original error: {e}", file=sys.stderr)
        
        if 'app' in locals():
            try:
                QMessageBox.critical(
                    None,
                    "Fatal Error",
                    f"An unexpected error occurred:\n\n{error_msg}\n\nThe application will exit."
                )
            except:
                # GUI also failed
                print("Could not display error dialog", file=sys.stderr)
        
        return 1
    
    finally:
        try:
            if 'logger' in locals():
                logger.info("=== WARGAME SIMULATION TERMINATED ===")
        except:
            print("Final logging failed", file=sys.stderr)


def auto_load_data(main_window: MainWindow, data_dir: str):
    """Auto-load data directory after startup with error handling."""
    try:
        logger = get_logger('main')
        logger.info(f"Auto-loading data from: {data_dir}")
        
        # Validate directory structure
        data_path = Path(data_dir)
        if not (data_path / "DEM").exists() or not (data_path / "Vector").exists():
            error_msg = "Data directory must contain 'DEM' and 'Vector' subdirectories."
            logger.error(f"Invalid directory structure: {error_msg}")
            QMessageBox.warning(main_window, "Invalid Data Directory", error_msg)
            return
        
        # Trigger data loading in main window
        main_window._start_data_loading(data_dir)
        
    except Exception as e:
        logger = get_logger('main')
        logger.error(f"Error in auto-load data: {e}")
        log_exception(e, 'main', 'auto data loading')
        QMessageBox.critical(
            main_window,
            "Auto-Load Error", 
            f"Failed to auto-load data:\n{str(e)}"
        )


if __name__ == "__main__":
    # Ensure we're running from the correct directory
    os.chdir(project_root)
    
    # Handle high DPI displays
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    
    # Run the application
    exit_code = main()
    sys.exit(exit_code)