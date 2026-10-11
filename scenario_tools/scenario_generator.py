#!/usr/bin/env python3
"""
Standalone Scenario Generator for Wargame Application

This script generates terrain scenario files independently of the main application
to enable faster app loading by pre-processing terrain data.

Usage:
    python scenario_generator.py --data-dir /path/to/data --output scenario.json
    python scenario_generator.py --config config.ini --data-dir ./data --output terrain_scenario.json
    python scenario_generator.py --help

Author: Wargame Development Team
"""

import sys
import os
import argparse
import configparser
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

# Add the project root to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from core.terrain import TerrainAnalyzer
    from core.hexgrid import HexGrid
    from core.scenario_manager import ScenarioManager
    from utils.geo_utils import load_vector_layers
    import geopandas as gpd
except ImportError as e:
    print(f"ERROR: Failed to import required modules: {e}")
    print("Make sure you're running this script from the wargame project directory.")
    sys.exit(1)


class ScenarioGenerator:
    """Standalone scenario generator for pre-processing terrain data."""
    
    def __init__(self, config_file: Optional[str] = None):
        """Initialize the scenario generator.
        
        Args:
            config_file: Path to configuration file (optional)
        """
        self.logger = self._setup_logging()
        self.config = self._load_config(config_file)
        self.scenario_manager = ScenarioManager()
        
        # Default generation settings
        self.default_settings = {
            'hex_size': 100.0,
            'map_bounds': None,  # Will be auto-calculated
            'terrain_analysis': True,
            'include_roads': True,
            'include_waterways': True,
            'compression_level': 6
        }
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for the generator."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('scenario_generator.log')
            ]
        )
        return logging.getLogger(__name__)
    
    def _load_config(self, config_file: Optional[str]) -> configparser.ConfigParser:
        """Load configuration from file.
        
        Args:
            config_file: Path to configuration file
            
        Returns:
            ConfigParser object with loaded configuration
        """
        config = configparser.ConfigParser()
        
        # Try to load config file
        if config_file and Path(config_file).exists():
            self.logger.info(f"Loading configuration from: {config_file}")
            config.read(config_file)
        elif Path('config.ini').exists():
            self.logger.info("Loading default configuration from: config.ini")
            config.read('config.ini')
        else:
            self.logger.warning("No configuration file found, using defaults")
            
        return config
    
    def generate_scenario(self, 
                         data_dir: str,
                         output_file: str,
                         scenario_name: Optional[str] = None,
                         description: Optional[str] = None,
                         settings_override: Optional[Dict[str, Any]] = None) -> bool:
        """Generate a terrain scenario file.
        
        Args:
            data_dir: Directory containing terrain and vector data
            output_file: Output scenario file path
            scenario_name: Name for the scenario (optional)
            description: Description for the scenario (optional)
            settings_override: Override default settings (optional)
            
        Returns:
            True if generation successful, False otherwise
        """
        try:
            start_time = time.time()
            self.logger.info(f"Starting scenario generation for data directory: {data_dir}")
            
            # Validate input directory
            data_path = Path(data_dir)
            if not data_path.exists():
                self.logger.error(f"Data directory does not exist: {data_dir}")
                return False
                
            # Merge settings
            settings = self.default_settings.copy()
            if settings_override:
                settings.update(settings_override)
                
            # Apply config file settings
            self._apply_config_settings(settings)
            
            # Step 1: Initialize terrain analyzer
            self.logger.info("Initializing terrain analyzer...")
            terrain_analyzer = TerrainAnalyzer(data_dir=str(data_path))
            
            # Load terrain data
            self.logger.info("Loading terrain data...")
            if not terrain_analyzer.load_data():
                self.logger.error("Failed to load terrain data")
                return False
            
            # Step 2: Generate hex grid
            self.logger.info("Generating hex grid...")
            hex_grid = self._generate_hex_grid(terrain_analyzer, settings)
            if not hex_grid:
                self.logger.error("Failed to generate hex grid")
                return False
                
            # Step 3: Perform terrain analysis
            if settings.get('terrain_analysis', True):
                self.logger.info("Performing terrain analysis...")
                if not self._perform_terrain_analysis(terrain_analyzer, hex_grid):
                    self.logger.warning("Terrain analysis failed, continuing without it")
            
            # Step 4: Load vector data
            roads_data, waterways_data = self._load_vector_data(data_path, settings)
            
            # Step 5: Prepare metadata
            metadata = self._prepare_metadata(
                scenario_name or f"Generated_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                description or f"Auto-generated terrain scenario from {data_dir}",
                data_dir,
                settings
            )
            
            # Step 6: Prepare app settings
            app_settings = self._prepare_app_settings()
            
            # Step 7: Save scenario
            self.logger.info(f"Saving scenario to: {output_file}")
            success = self.scenario_manager.save_scenario(
                scenario_path=output_file,
                hex_grid=hex_grid,
                terrain_analyzer=terrain_analyzer,
                roads_data=roads_data,
                waterways_data=waterways_data,
                app_settings=app_settings,
                metadata=metadata
            )
            
            if success:
                generation_time = time.time() - start_time
                
                # Handle the actual output filename (scenario manager may add .json extension)
                actual_file = Path(output_file)
                if not actual_file.exists():
                    # Check if scenario manager added .json extension
                    if not actual_file.suffix == '.json':
                        actual_file = actual_file.with_suffix('.json')
                
                if actual_file.exists():
                    file_size = actual_file.stat().st_size / (1024 * 1024)
                    
                    self.logger.info(f"Scenario generation completed successfully!")
                    self.logger.info(f"Generation time: {generation_time:.2f} seconds")
                    self.logger.info(f"Output file: {actual_file}")
                    self.logger.info(f"File size: {file_size:.2f} MB")
                    self.logger.info(f"Hex cells: {len(hex_grid.cells) if hex_grid else 0}")
                    self.logger.info(f"Roads: {len(roads_data) if roads_data else 0}")
                    self.logger.info(f"Waterways: {len(waterways_data) if waterways_data else 0}")
                else:
                    self.logger.error(f"Scenario file not found at expected location: {output_file}")
                    return False
                
                return True
            else:
                self.logger.error("Failed to save scenario file")
                return False
                
        except Exception as e:
            self.logger.error(f"Scenario generation failed: {e}", exc_info=True)
            return False
    
    def _apply_config_settings(self, settings: Dict[str, Any]) -> None:
        """Apply settings from configuration file.
        
        Args:
            settings: Settings dictionary to update
        """
        try:
            # Apply hex grid settings
            if self.config.has_section('HexGrid'):
                if self.config.has_option('HexGrid', 'hex_size'):
                    settings['hex_size'] = self.config.getfloat('HexGrid', 'hex_size')
                    
            # Apply terrain settings
            if self.config.has_section('Terrain'):
                if self.config.has_option('Terrain', 'enable_analysis'):
                    settings['terrain_analysis'] = self.config.getboolean('Terrain', 'enable_analysis')
                    
            # Apply vector data settings
            if self.config.has_section('VectorData'):
                if self.config.has_option('VectorData', 'include_roads'):
                    settings['include_roads'] = self.config.getboolean('VectorData', 'include_roads')
                if self.config.has_option('VectorData', 'include_waterways'):
                    settings['include_waterways'] = self.config.getboolean('VectorData', 'include_waterways')
                    
            # Apply compression settings
            if self.config.has_section('ScenarioManager'):
                if self.config.has_option('ScenarioManager', 'compression_level'):
                    settings['compression_level'] = self.config.getint('ScenarioManager', 'compression_level')
                    
            self.logger.debug(f"Applied config settings: {settings}")
            
        except Exception as e:
            self.logger.warning(f"Failed to apply some config settings: {e}")
    
    def _generate_hex_grid(self, terrain_analyzer: TerrainAnalyzer, settings: Dict[str, Any]) -> Optional[HexGrid]:
        """Generate hex grid from terrain data.
        
        Args:
            terrain_analyzer: Initialized terrain analyzer
            settings: Generation settings
            
        Returns:
            Generated HexGrid or None if failed
        """
        try:
            # Get map bounds from terrain data or use settings
            bounds = settings.get('map_bounds')
            if not bounds and hasattr(terrain_analyzer, 'get_data_bounds'):
                bounds = terrain_analyzer.get_data_bounds()
                
            if not bounds:
                self.logger.error("Could not determine map bounds for hex grid generation")
                return None
                
            # Create hex grid
            hex_size = settings.get('hex_size', 100.0)
            hex_grid = HexGrid(hex_size=hex_size)
            
            # Generate the grid with the bounds
            hex_grid.generate_grid(bounds)
            
            self.logger.info(f"Generated hex grid with {len(hex_grid.cells)} hexes")
            return hex_grid
            
        except Exception as e:
            self.logger.error(f"Failed to generate hex grid: {e}")
            return None
    
    def _perform_terrain_analysis(self, terrain_analyzer: TerrainAnalyzer, hex_grid: HexGrid) -> bool:
        """Perform terrain analysis on hex grid.
        
        Args:
            terrain_analyzer: Terrain analyzer instance
            hex_grid: Hex grid to analyze
            
        Returns:
            True if analysis successful, False otherwise
        """
        try:
            # Perform analysis using existing terrain analyzer
            self.logger.info("Running terrain analysis...")
            
            # This will use the GPU-accelerated terrain analysis we implemented
            terrain_analyzer.analyze_grid(hex_grid)
            self.logger.info("Terrain analysis completed successfully")
            return True
                
        except Exception as e:
            self.logger.error(f"Terrain analysis failed: {e}")
            return False
    
    def _load_vector_data(self, data_path: Path, settings: Dict[str, Any]) -> tuple[List[Dict], List[Dict]]:
        """Load vector data (roads and waterways).
        
        Args:
            data_path: Path to data directory
            settings: Generation settings
            
        Returns:
            Tuple of (roads_data, waterways_data)
        """
        roads_data = []
        waterways_data = []
        
        try:
            vector_dir = data_path / 'Vector'
            
            # Load roads
            if settings.get('include_roads', True):
                roads_file = vector_dir / 'roads.shp'
                if roads_file.exists():
                    self.logger.info("Loading roads data...")
                    try:
                        roads_gdf = gpd.read_file(str(roads_file))
                        if roads_gdf is not None and not roads_gdf.empty:
                            roads_data = self._convert_geodataframe_to_dict(roads_gdf)
                            self.logger.info(f"Loaded {len(roads_data)} roads")
                        else:
                            self.logger.warning("No roads data loaded")
                    except Exception as e:
                        self.logger.warning(f"Failed to load roads: {e}")
                else:
                    self.logger.info("No roads file found")
            
            # Load waterways
            if settings.get('include_waterways', True):
                waterways_files = ['water_ways.shp', 'water_zones.shp']
                for filename in waterways_files:
                    waterways_file = vector_dir / filename
                    if waterways_file.exists():
                        self.logger.info(f"Loading waterways data from {filename}...")
                        try:
                            waterways_gdf = gpd.read_file(str(waterways_file))
                            if waterways_gdf is not None and not waterways_gdf.empty:
                                waterway_data = self._convert_geodataframe_to_dict(waterways_gdf)
                                waterways_data.extend(waterway_data)
                                self.logger.info(f"Loaded {len(waterway_data)} waterways from {filename}")
                        except Exception as e:
                            self.logger.warning(f"Failed to load waterways from {filename}: {e}")
                
                if waterways_data:
                    self.logger.info(f"Total waterways loaded: {len(waterways_data)}")
                else:
                    self.logger.info("No waterways data found")
            
        except Exception as e:
            self.logger.error(f"Failed to load vector data: {e}")
            
        return roads_data, waterways_data
    
    def _convert_geodataframe_to_dict(self, gdf) -> List[Dict[str, Any]]:
        """Convert GeoDataFrame to list of dictionaries.
        
        Args:
            gdf: GeoDataFrame to convert
            
        Returns:
            List of feature dictionaries
        """
        try:
            features = []
            for idx, row in gdf.iterrows():
                feature = {
                    'id': idx,
                    'geometry': row.geometry.__geo_interface__ if hasattr(row.geometry, '__geo_interface__') else str(row.geometry),
                    'properties': {}
                }
                
                # Add all non-geometry columns as properties
                for col in gdf.columns:
                    if col != 'geometry':
                        feature['properties'][col] = row[col]
                        
                features.append(feature)
                
            return features
            
        except Exception as e:
            self.logger.error(f"Failed to convert GeoDataFrame: {e}")
            return []
    
    def _prepare_metadata(self, name: str, description: str, data_source: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare scenario metadata.
        
        Args:
            name: Scenario name
            description: Scenario description
            data_source: Source data directory
            settings: Generation settings
            
        Returns:
            Metadata dictionary
        """
        return {
            'name': name,
            'description': description,
            'created_by': 'Scenario Generator',
            'generator_version': '1.0',
            'data_source': str(data_source),
            'generation_settings': settings.copy(),
            'created_at': datetime.now().isoformat(),
            'terrain_analysis_enabled': settings.get('terrain_analysis', True),
            'hex_size': settings.get('hex_size', 100.0),
            'includes_roads': settings.get('include_roads', True),
            'includes_waterways': settings.get('include_waterways', True)
        }
    
    def _prepare_app_settings(self) -> Dict[str, Any]:
        """Prepare application settings for scenario.
        
        Returns:
            Application settings dictionary
        """
        app_settings = {
            'version': '1.0',
            'view': {
                'show_grid': True,
                'show_coordinates': False,
                'zoom_level': 1.0,
                'default_display_mode': 'elevation'
            },
            'terrain': {
                'analysis_enabled': True,
                'classification_method': 'elevation_slope',
                'gpu_acceleration': True
            },
            'performance': {
                'cache_terrain_analysis': True,
                'use_gpu_when_available': True,
                'compression_level': 6
            }
        }
        
        # Override with config file settings if available
        try:
            if self.config.has_section('Display'):
                for key, value in self.config.items('Display'):
                    if key in app_settings['view']:
                        if key in ['show_grid', 'show_coordinates']:
                            app_settings['view'][key] = self.config.getboolean('Display', key)
                        elif key == 'zoom_level':
                            app_settings['view'][key] = self.config.getfloat('Display', key)
                        else:
                            app_settings['view'][key] = value
                            
        except Exception as e:
            self.logger.warning(f"Failed to apply some app settings from config: {e}")
            
        return app_settings


def main():
    """Main function for command-line interface."""
    parser = argparse.ArgumentParser(
        description="Generate terrain scenario files for faster wargame app loading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python scenario_generator.py --data-dir ./data --output terrain.json
  
  # With custom configuration
  python scenario_generator.py --config custom.ini --data-dir /path/to/data --output scenario.json
  
  # With custom settings
  python scenario_generator.py --data-dir ./data --output test.json --hex-size 50 --name "Test Scenario"
        """
    )
    
    parser.add_argument('--data-dir', '-d', required=True,
                       help='Directory containing terrain and vector data')
    parser.add_argument('--output', '-o', required=True,
                       help='Output scenario file path')
    parser.add_argument('--config', '-c',
                       help='Configuration file path (default: config.ini)')
    parser.add_argument('--name', '-n',
                       help='Scenario name')
    parser.add_argument('--description',
                       help='Scenario description')
    parser.add_argument('--hex-size', type=float, default=100.0,
                       help='Hex size in meters (default: 100.0)')
    parser.add_argument('--no-terrain-analysis', action='store_true',
                       help='Skip terrain analysis')
    parser.add_argument('--no-roads', action='store_true',
                       help='Skip roads data')
    parser.add_argument('--no-waterways', action='store_true',
                       help='Skip waterways data')
    parser.add_argument('--compression-level', type=int, default=6, choices=range(1, 10),
                       help='Compression level (1-9, default: 6)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Set up logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Prepare settings override
    settings_override = {
        'hex_size': args.hex_size,
        'terrain_analysis': not args.no_terrain_analysis,
        'include_roads': not args.no_roads,
        'include_waterways': not args.no_waterways,
        'compression_level': args.compression_level
    }
    
    # Initialize generator
    try:
        generator = ScenarioGenerator(config_file=args.config)
        
        # Generate scenario
        success = generator.generate_scenario(
            data_dir=args.data_dir,
            output_file=args.output,
            scenario_name=args.name,
            description=args.description,
            settings_override=settings_override
        )
        
        if success:
            print(f"\n✅ Scenario generation completed successfully!")
            print(f"📁 Output file: {args.output}")
            sys.exit(0)
        else:
            print(f"\n❌ Scenario generation failed!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Generation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()