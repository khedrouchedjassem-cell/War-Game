#!/usr/bin/env python3
"""
Scenario Generator Test and Example Script

This script demonstrates how to use the scenario generator
and provides test cases for validation.
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def test_scenario_generator():
    """Test the scenario generator with your current data."""
    
    print("🧪 Testing Scenario Generator")
    print("=" * 50)
    
    # Check if data directory exists
    data_dir = Path("./data")
    if not data_dir.exists():
        print("❌ Data directory './data' not found")
        print("📁 Please ensure your terrain data is in ./data/")
        return False
    
    print(f"✓ Found data directory: {data_dir}")
    
    # Check data structure
    dem_dir = data_dir / "DEM"
    vector_dir = data_dir / "Vector"
    
    if dem_dir.exists():
        dem_files = list(dem_dir.glob("*.tif")) + list(dem_dir.glob("*.tiff"))
        print(f"✓ DEM directory found with {len(dem_files)} elevation files")
    else:
        print("⚠ No DEM directory found")
    
    if vector_dir.exists():
        vector_files = list(vector_dir.glob("*.shp"))
        print(f"✓ Vector directory found with {len(vector_files)} shape files")
        for vf in vector_files:
            print(f"  - {vf.name}")
    else:
        print("⚠ No Vector directory found")
    
    # Test scenario generation
    print("\n🎯 Testing scenario generation...")
    
    try:
        from scenario_generator import ScenarioGenerator
        
        # Initialize generator
        generator = ScenarioGenerator()
        
        # Generate test scenario
        output_file = "test_scenario.json"
        
        print(f"📄 Generating scenario: {output_file}")
        success = generator.generate_scenario(
            data_dir=str(data_dir),
            output_file=output_file,
            scenario_name="Test Scenario",
            description="Test scenario generated for validation",
            settings_override={
                'hex_size': 100.0,
                'terrain_analysis': True,
                'include_roads': True,
                'include_waterways': True,
                'compression_level': 6
            }
        )
        
        if success:
            print("✅ Scenario generation successful!")
            
            # Check output file
            output_path = Path(output_file)
            if output_path.exists():
                file_size = output_path.stat().st_size / (1024 * 1024)
                print(f"📁 Output file: {output_file}")
                print(f"💾 File size: {file_size:.2f} MB")
                
                # Test loading the scenario
                print("\n🔄 Testing scenario loading...")
                try:
                    scenario_data = generator.scenario_manager.load_scenario(output_file)
                    if scenario_data:
                        print("✅ Scenario loading successful!")
                        
                        # Print scenario statistics
                        stats = scenario_data.get('statistics', {})
                        terrain_stats = stats.get('terrain', {})
                        
                        print(f"📊 Scenario Statistics:")
                        print(f"  - Hex cells: {terrain_stats.get('total_hex_cells', 'Unknown')}")
                        print(f"  - Roads: {len(scenario_data.get('roads', {}).get('roads', []))}")
                        print(f"  - Waterways: {len(scenario_data.get('waterways', {}).get('waterways', []))}")
                        print(f"  - Created: {scenario_data.get('timestamp', 'Unknown')}")
                        
                        return True
                    else:
                        print("❌ Failed to load generated scenario")
                        return False
                        
                except Exception as e:
                    print(f"❌ Error loading scenario: {e}")
                    return False
            else:
                print("❌ Output file was not created")
                return False
        else:
            print("❌ Scenario generation failed")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Make sure all dependencies are installed:")
        print("   pip install -r requirements.txt")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def example_single_generation():
    """Example of single scenario generation."""
    
    print("\n📝 Example: Single Scenario Generation")
    print("-" * 40)
    
    example_code = '''
from scenario_generator import ScenarioGenerator

# Initialize generator
generator = ScenarioGenerator(config_file="scenario_generator_config.ini")

# Generate scenario
success = generator.generate_scenario(
    data_dir="./data",
    output_file="my_terrain.scenario.gz",
    scenario_name="My Terrain",
    description="Custom terrain scenario",
    settings_override={
        'hex_size': 50.0,           # Smaller hexes for more detail
        'terrain_analysis': True,    # Enable terrain analysis
        'include_roads': True,       # Include roads
        'include_waterways': True,   # Include waterways
        'compression_level': 9       # Maximum compression
    }
)

if success:
    print("Scenario generated successfully!")
else:
    print("Generation failed!")
'''
    
    print(example_code)


def example_batch_generation():
    """Example of batch scenario generation."""
    
    print("\n📝 Example: Batch Scenario Generation")
    print("-" * 40)
    
    example_code = '''
from batch_scenario_generator import BatchScenarioGenerator

# Initialize batch generator
batch_generator = BatchScenarioGenerator(
    config_file="scenario_generator_config.ini",
    max_workers=4  # Process 4 scenarios simultaneously
)

# Generate scenarios for all datasets
results = batch_generator.generate_batch(
    input_dir="./datasets",      # Directory containing multiple terrain datasets
    output_dir="./scenarios",    # Output directory for scenarios
    settings_override={
        'hex_size': 100.0,
        'terrain_analysis': True,
        'compression_level': 6
    }
)

# Check results
successful = sum(1 for success in results.values() if success)
print(f"Generated {successful}/{len(results)} scenarios successfully")
'''
    
    print(example_code)


def example_command_line_usage():
    """Example of command-line usage."""
    
    print("\n📝 Example: Command Line Usage")
    print("-" * 40)
    
    examples = [
        "# Generate single scenario",
        "./generate_scenarios.sh single --data ./data --output terrain.scenario.gz",
        "",
        "# Generate with custom settings",
        "./generate_scenarios.sh single --data ./data --output detailed.scenario.gz --hex-size 50 --name 'Detailed Terrain'",
        "",
        "# Batch process multiple datasets", 
        "./generate_scenarios.sh batch --input ./datasets --output ./scenarios --workers 4",
        "",
        "# Check if data directory is valid",
        "./generate_scenarios.sh check --data ./data",
        "",
        "# Create configuration file",
        "./generate_scenarios.sh config --create",
        "",
        "# Using Python directly",
        "python scenario_generator.py --data-dir ./data --output terrain.scenario.gz --hex-size 100",
        "",
        "python batch_scenario_generator.py --input-dir ./datasets --output-dir ./scenarios --workers 2"
    ]
    
    for example in examples:
        print(example)


def main():
    """Main function."""
    
    print("🎮 Wargame Scenario Generator - Test & Examples")
    print("=" * 60)
    
    # Test with current data
    success = test_scenario_generator()
    
    # Show examples regardless of test result
    example_single_generation()
    example_batch_generation() 
    example_command_line_usage()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 All tests passed! The scenario generator is ready to use.")
        print("\n💡 Next steps:")
        print("  1. Customize settings in scenario_generator_config.ini")
        print("  2. Generate scenarios for your terrain data")
        print("  3. Use generated scenarios in the main wargame application")
    else:
        print("⚠️  Tests failed. Please check the error messages above.")
        print("\n🔧 Troubleshooting:")
        print("  1. Ensure all dependencies are installed: pip install -r requirements.txt")
        print("  2. Check that ./data directory contains valid terrain data")
        print("  3. Verify Python path and module imports")
    
    print(f"\n📚 For more help: ./generate_scenarios.sh help")


if __name__ == "__main__":
    main()