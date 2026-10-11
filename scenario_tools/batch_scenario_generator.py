#!/usr/bin/env python3
"""
Batch Scenario Generator

This script processes multiple terrain datasets in batch to generate
scenario files for the wargame application.

Usage:
    python batch_scenario_generator.py --input-dir /path/to/datasets --output-dir /path/to/scenarios
    python batch_scenario_generator.py --config batch_config.ini
"""

import os
import sys
import argparse
import configparser
import logging
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from scenario_generator import ScenarioGenerator


class BatchScenarioGenerator:
    """Batch processor for generating multiple scenario files."""
    
    def __init__(self, config_file: Optional[str] = None, max_workers: int = 2):
        """Initialize batch generator.
        
        Args:
            config_file: Configuration file path
            max_workers: Maximum number of parallel workers
        """
        self.logger = self._setup_logging()
        self.config = self._load_config(config_file)
        self.max_workers = max_workers
        self.generator = ScenarioGenerator(config_file)
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for batch processing."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(f'batch_generation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
            ]
        )
        return logging.getLogger(__name__)
    
    def _load_config(self, config_file: Optional[str]) -> configparser.ConfigParser:
        """Load batch configuration."""
        config = configparser.ConfigParser()
        
        if config_file and Path(config_file).exists():
            self.logger.info(f"Loading batch configuration from: {config_file}")
            config.read(config_file)
        else:
            self.logger.info("Using default batch configuration")
            
        return config
    
    def discover_datasets(self, input_dir: str) -> List[Dict[str, str]]:
        """Discover terrain datasets in input directory.
        
        Args:
            input_dir: Directory to scan for datasets
            
        Returns:
            List of dataset dictionaries with paths and names
        """
        datasets = []
        input_path = Path(input_dir)
        
        if not input_path.exists():
            self.logger.error(f"Input directory does not exist: {input_dir}")
            return datasets
            
        self.logger.info(f"Scanning for datasets in: {input_dir}")
        
        # Look for directories containing data
        for item in input_path.iterdir():
            if item.is_dir():
                # Check if directory contains terrain data
                if self._is_valid_dataset(item):
                    datasets.append({
                        'name': item.name,
                        'path': str(item),
                        'data_dir': str(item)
                    })
                    self.logger.info(f"Found dataset: {item.name}")
                else:
                    # Check subdirectories
                    for subitem in item.iterdir():
                        if subitem.is_dir() and self._is_valid_dataset(subitem):
                            datasets.append({
                                'name': f"{item.name}_{subitem.name}",
                                'path': str(subitem),
                                'data_dir': str(subitem)
                            })
                            self.logger.info(f"Found dataset: {item.name}_{subitem.name}")
        
        self.logger.info(f"Discovered {len(datasets)} datasets")
        return datasets
    
    def _is_valid_dataset(self, path: Path) -> bool:
        """Check if directory contains valid terrain dataset.
        
        Args:
            path: Directory path to check
            
        Returns:
            True if valid dataset, False otherwise
        """
        # Look for DEM data
        dem_dir = path / 'DEM'
        if dem_dir.exists():
            dem_files = list(dem_dir.glob('*.tif')) + list(dem_dir.glob('*.tiff'))
            if dem_files:
                return True
                
        # Look for vector data
        vector_dir = path / 'Vector'
        if vector_dir.exists():
            vector_files = list(vector_dir.glob('*.shp'))
            if vector_files:
                return True
                
        return False
    
    def generate_batch(self, 
                      input_dir: str,
                      output_dir: str,
                      settings_override: Optional[Dict[str, Any]] = None) -> Dict[str, bool]:
        """Generate scenarios for all datasets in batch.
        
        Args:
            input_dir: Directory containing datasets
            output_dir: Directory for output scenario files
            settings_override: Override settings for all generations
            
        Returns:
            Dictionary mapping dataset names to success status
        """
        start_time = time.time()
        results = {}
        
        # Discover datasets
        datasets = self.discover_datasets(input_dir)
        if not datasets:
            self.logger.error("No valid datasets found")
            return results
            
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Process datasets
        if self.max_workers > 1:
            results = self._process_parallel(datasets, output_path, settings_override)
        else:
            results = self._process_sequential(datasets, output_path, settings_override)
        
        # Summary
        total_time = time.time() - start_time
        successful = sum(1 for success in results.values() if success)
        failed = len(results) - successful
        
        self.logger.info(f"\n{'='*50}")
        self.logger.info(f"BATCH GENERATION COMPLETE")
        self.logger.info(f"{'='*50}")
        self.logger.info(f"Total datasets: {len(datasets)}")
        self.logger.info(f"Successful: {successful}")
        self.logger.info(f"Failed: {failed}")
        self.logger.info(f"Total time: {total_time:.2f} seconds")
        self.logger.info(f"Average time per dataset: {total_time/len(datasets):.2f} seconds")
        
        if failed > 0:
            self.logger.warning(f"Failed datasets:")
            for name, success in results.items():
                if not success:
                    self.logger.warning(f"  - {name}")
        
        return results
    
    def _process_sequential(self, 
                           datasets: List[Dict[str, str]], 
                           output_path: Path, 
                           settings_override: Optional[Dict[str, Any]]) -> Dict[str, bool]:
        """Process datasets sequentially.
        
        Args:
            datasets: List of dataset dictionaries
            output_path: Output directory path
            settings_override: Settings override
            
        Returns:
            Results dictionary
        """
        results = {}
        
        for i, dataset in enumerate(datasets, 1):
            self.logger.info(f"\n[{i}/{len(datasets)}] Processing: {dataset['name']}")
            
            output_file = output_path / f"{dataset['name']}.scenario.gz"
            
            success = self.generator.generate_scenario(
                data_dir=dataset['data_dir'],
                output_file=str(output_file),
                scenario_name=dataset['name'],
                description=f"Auto-generated from {dataset['path']}",
                settings_override=settings_override
            )
            
            results[dataset['name']] = success
            
            if success:
                self.logger.info(f"✅ {dataset['name']} completed successfully")
            else:
                self.logger.error(f"❌ {dataset['name']} failed")
                
        return results
    
    def _process_parallel(self, 
                         datasets: List[Dict[str, str]], 
                         output_path: Path, 
                         settings_override: Optional[Dict[str, Any]]) -> Dict[str, bool]:
        """Process datasets in parallel.
        
        Args:
            datasets: List of dataset dictionaries
            output_path: Output directory path
            settings_override: Settings override
            
        Returns:
            Results dictionary
        """
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_dataset = {}
            for dataset in datasets:
                output_file = output_path / f"{dataset['name']}.scenario.gz"
                
                future = executor.submit(
                    self._generate_single_scenario,
                    dataset,
                    str(output_file),
                    settings_override
                )
                future_to_dataset[future] = dataset
            
            # Process completed tasks
            completed = 0
            for future in as_completed(future_to_dataset):
                dataset = future_to_dataset[future]
                completed += 1
                
                try:
                    success = future.result()
                    results[dataset['name']] = success
                    
                    if success:
                        self.logger.info(f"✅ [{completed}/{len(datasets)}] {dataset['name']} completed")
                    else:
                        self.logger.error(f"❌ [{completed}/{len(datasets)}] {dataset['name']} failed")
                        
                except Exception as e:
                    self.logger.error(f"💥 [{completed}/{len(datasets)}] {dataset['name']} error: {e}")
                    results[dataset['name']] = False
        
        return results
    
    def _generate_single_scenario(self, 
                                 dataset: Dict[str, str], 
                                 output_file: str, 
                                 settings_override: Optional[Dict[str, Any]]) -> bool:
        """Generate a single scenario (for parallel processing).
        
        Args:
            dataset: Dataset dictionary
            output_file: Output file path
            settings_override: Settings override
            
        Returns:
            True if successful, False otherwise
        """
        # Create a new generator instance for thread safety
        generator = ScenarioGenerator(self.generator.config)
        
        return generator.generate_scenario(
            data_dir=dataset['data_dir'],
            output_file=output_file,
            scenario_name=dataset['name'],
            description=f"Auto-generated from {dataset['path']}",
            settings_override=settings_override
        )


def main():
    """Main function for batch generation."""
    parser = argparse.ArgumentParser(
        description="Batch generate terrain scenario files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all datasets in a directory
  python batch_scenario_generator.py --input-dir ./datasets --output-dir ./scenarios
  
  # Parallel processing with custom settings
  python batch_scenario_generator.py --input-dir ./data --output-dir ./out --workers 4 --hex-size 50
        """
    )
    
    parser.add_argument('--input-dir', '-i', required=True,
                       help='Directory containing terrain datasets')
    parser.add_argument('--output-dir', '-o', required=True,
                       help='Output directory for scenario files')
    parser.add_argument('--config', '-c',
                       help='Configuration file path')
    parser.add_argument('--workers', '-w', type=int, default=2,
                       help='Number of parallel workers (default: 2)')
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
    
    # Initialize batch generator
    try:
        batch_generator = BatchScenarioGenerator(
            config_file=args.config,
            max_workers=args.workers
        )
        
        # Run batch generation
        results = batch_generator.generate_batch(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            settings_override=settings_override
        )
        
        # Exit with appropriate code
        successful = sum(1 for success in results.values() if success)
        if successful == len(results):
            print(f"\n🎉 All {len(results)} scenarios generated successfully!")
            sys.exit(0)
        elif successful > 0:
            print(f"\n⚠️  {successful}/{len(results)} scenarios generated successfully")
            sys.exit(1)
        else:
            print(f"\n💥 All {len(results)} scenarios failed!")
            sys.exit(2)
            
    except KeyboardInterrupt:
        print("\n🛑 Batch generation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()