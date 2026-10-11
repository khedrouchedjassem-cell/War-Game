# Wargame Simulation Application

A complete wargame simulation application that models territory using hexagonal cells, loads terrain data (DTM + vector layers), and allows users to visualize, command, and simulate military unit movements and engagements.

## Features

- Hexagonal grid-based terrain modeling
- Real geospatial data integration (DEM + vector layers)
- Interactive PyQt6 GUI with map visualization
- Unit movement and pathfinding (A* algorithm)
- Line-of-sight calculations using terrain
- Combat simulation and detection systems
- Performance-optimized rendering and calculations
- **Standalone scenario generation tools** for pre-processing terrain data

## Installation

1. Install Python 3.8+ 
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Main Application
Run the main wargame application:
```bash
python main.py
```

### Scenario Generator Tools
Generate terrain scenarios for faster loading:
```bash
# Generate a single scenario
./generate_scenarios single --data ./data --output terrain.json

# Batch process multiple datasets
./generate_scenarios batch --input ./datasets --output ./scenarios

# Check data directory validity
./generate_scenarios check --data ./data
```

**📖 Complete Documentation**: See `scenario_tools/README.md` for detailed usage, examples, and troubleshooting.

## Project Structure

```
project/
├── data/                      # GIS data (DEM, vector layers)
├── scenario_tools/            # 🎮 Scenario generation tools
│   ├── scenario_generator.py      # Main scenario generator
│   ├── batch_scenario_generator.py # Batch processing
│   ├── generate_scenarios.sh      # Shell wrapper
│   ├── generated_scenarios/       # Output scenarios
│   └── README.md                  # Detailed documentation
├── core/                      # Core simulation logic
│   ├── hexgrid.py                 # Hexagonal grid generation
│   ├── terrain.py                 # Terrain analysis
│   ├── scenario_manager.py        # Scenario saving/loading
│   ├── simulation.py              # Main simulation engine
│   ├── pathfinding.py             # A* pathfinding
│   └── los.py                     # Line-of-sight calculations
├── ui/                        # PyQt6 user interface
│   ├── main_window.py             # Main application window
│   ├── map_view.py                # Map visualization
│   ├── side_panel.py              # Information panels
│   └── icons/                     # UI icons and assets
├── models/                    # Data models
│   ├── hexcell.py                 # Hex cell representation
│   └── unit.py                    # Unit representation
├── utils/                     # Utility functions
│   └── geo_utils.py               # GIS utilities
├── main.py                    # Application entry point
├── generate_scenarios         # 🚀 Scenario generator launcher
└── requirements.txt           # Python dependencies
```

## Controls

- **Mouse**: Pan and zoom the map
- **Left Click**: Select hexes or units
- **Right Click**: Context menu for actions
- **Toolbar**: Load data, toggle layers, spawn units
- **Sidebar**: View terrain and unit information

## Data Requirements

Place your GIS data in the `data/` folder:
- `DEM/DEM_Projected.tif` - Digital elevation model
- `Vector/` - Shapefile layers (buildings, roads, water, landuse)

## License

MIT License