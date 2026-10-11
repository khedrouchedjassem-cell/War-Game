#!/usr/bin/env python3
"""
Waterway Rules Validation Test

This script tests the implementation of waterway rules:
1. Waterways must follow hex cell edges only
2. Waterway segments of the same waterway must be connected
3. No waterway segment may cut through hex cell interiors
"""

import sys
import os
from pathlib import Path
import geopandas as gpd

# Add project root to path
sys.path.append('/home/medaly/Desktop/MyWork/wargame')

from core.hexgrid import HexGrid
from utils.waterway_validator import WaterwayValidator

def test_waterway_rules():
    """Test waterway rules implementation."""
    print("WATERWAY RULES VALIDATION TEST")
    print("=" * 50)
    
    # Create a test hex grid
    print("Setting up test hex grid...")
    bounds = (-500, -500, 500, 500)  # 1km x 1km test area
    hex_grid = HexGrid(hex_size=100)
    hex_grid.generate_grid(bounds)
    print(f"Created hex grid with {len(hex_grid.cells)} cells")
    
    # Try to load actual waterway data
    waterways_path = Path("data/Vector/water_ways.shp")
    if not waterways_path.exists():
        print("WARNING: No waterway data found - creating synthetic test data")
        # Could create synthetic test data here
        return False
    
    print(f"Loading waterway data from {waterways_path}")
    waterways_gdf = gpd.read_file(waterways_path)
    print(f"Loaded {len(waterways_gdf)} waterway features")
    
    # Initialize validator
    print("Initializing waterway validator...")
    validator = WaterwayValidator(hex_grid)
    
    # Convert GeoDataFrame to expected format
    print("Converting waterway data for validation...")
    waterway_segments = []
    for idx, row in waterways_gdf.iterrows():
        segment = {
            'geometry': row.geometry,
            'waterway_id': row.get('name', f'waterway_{idx}'),
            'segment_id': idx,
            'properties': dict(row)
        }
        waterway_segments.append(segment)
    
    print(f"Prepared {len(waterway_segments)} waterway segments for validation")
    
    # Run comprehensive validation
    print("\nRUNNING WATERWAY RULES VALIDATION...")
    print("-" * 40)
    
    validation_result = validator.validate_all_waterways(waterway_segments)
    
    # Report results
    print("\nVALIDATION RESULTS:")
    print("=" * 30)
    
    total_segments = validation_result.get('total_segments', len(waterway_segments))
    edge_violations = len(validation_result.get('edge_following_violations', []))
    connectivity_violations = len(validation_result.get('connectivity_violations', []))
    interior_violations = len(validation_result.get('interior_crossing_violations', []))
    total_violations = edge_violations + connectivity_violations + interior_violations
    
    print(f"Total segments validated: {total_segments}")
    print(f"Total rule violations found: {total_violations}")
    
    if total_violations == 0:
        print("✓ ALL WATERWAY RULES CORRECTLY IMPLEMENTED")
        print("✓ Edge following rule: PASSED")
        print("✓ Connectivity rule: PASSED") 
        print("✓ No interior crossing rule: PASSED")
        return True
    else:
        print(f"✗ FOUND {total_violations} RULE VIOLATIONS")
        
        print(f"  - Edge following violations: {edge_violations}")
        print(f"  - Connectivity violations: {connectivity_violations}")
        print(f"  - Interior crossing violations: {interior_violations}")
        
        # Show detailed violations
        all_violations = []
        all_violations.extend(validation_result.get('edge_following_violations', []))
        all_violations.extend(validation_result.get('connectivity_violations', []))
        all_violations.extend(validation_result.get('interior_crossing_violations', []))
        
        print("\nFIRST 10 VIOLATIONS:")
        for i, violation in enumerate(all_violations[:10]):
            print(f"  {i+1}. {violation}")
        
        if len(all_violations) > 10:
            print(f"  ... and {len(all_violations) - 10} more violations")
        
        return False

def main():
    """Main test function."""
    success = test_waterway_rules()
    
    if success:
        print("\n🎉 WATERWAY RULES VALIDATION: PASSED")
        print("All waterway rules are correctly implemented!")
        sys.exit(0)
    else:
        print("\n❌ WATERWAY RULES VALIDATION: FAILED")
        print("Some waterway rules need to be fixed!")
        sys.exit(1)

if __name__ == "__main__":
    main()