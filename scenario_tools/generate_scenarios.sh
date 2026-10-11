#!/bin/bash

# Wargame Scenario Generator Wrapper Script
# This script provides easy access to scenario generation tools

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_CMD="python3"

# Check if we have a virtual environment
if [[ -f "$PROJECT_ROOT/venv/bin/python" ]]; then
    PYTHON_CMD="$PROJECT_ROOT/venv/bin/python"
    export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"
fi

# Function to print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check if Python dependencies are available
check_dependencies() {
    print_color $BLUE "Checking dependencies..."
    
    if ! command -v $PYTHON_CMD &> /dev/null; then
        print_color $RED "Error: Python 3 is not installed or not in PATH"
        exit 1
    fi
    
    # Check if required Python modules are available
    local required_modules=("geopandas" "numpy" "rasterio")
    for module in "${required_modules[@]}"; do
        if ! $PYTHON_CMD -c "import $module" &> /dev/null; then
            print_color $RED "Error: Python module '$module' is not installed"
            print_color $YELLOW "Install with: pip install $module"
            exit 1
        fi
    done
    
    print_color $GREEN "✓ All dependencies are available"
}

# Function to show usage
show_usage() {
    cat << EOF
🎮 Wargame Scenario Generator

USAGE:
    $0 <command> [options]

COMMANDS:
    single      Generate a single scenario from data directory
    batch       Generate multiple scenarios from datasets
    check       Check data directory for valid terrain data
    config      Create/edit configuration file
    help        Show this help message

EXAMPLES:
    # Generate single scenario
    $0 single --data ./data --output terrain.json

    # Batch process multiple datasets
    $0 batch --input ./datasets --output ./scenarios

    # Check if data directory is valid
    $0 check --data ./data

    # Create default configuration file
    $0 config --create

For detailed command options, use:
    $0 <command> --help

EOF
}

# Function to generate single scenario
generate_single() {
    shift # Remove 'single' from args
    print_color $BLUE "🎯 Generating single scenario..."
    cd "$PROJECT_ROOT"
    $PYTHON_CMD "$SCRIPT_DIR/scenario_generator.py" "$@"
}

# Function to generate batch scenarios
generate_batch() {
    shift # Remove 'batch' from args
    print_color $BLUE "🚀 Starting batch scenario generation..."
    cd "$PROJECT_ROOT"
    $PYTHON_CMD "$SCRIPT_DIR/batch_scenario_generator.py" "$@"
}

# Function to check data directory
check_data() {
    shift # Remove 'check' from args
    local data_dir=""
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --data|-d)
                data_dir="$2"
                shift 2
                ;;
            --help|-h)
                cat << EOF
Check Data Directory

USAGE:
    $0 check --data <directory>

OPTIONS:
    --data, -d      Data directory to check
    --help, -h      Show this help

DESCRIPTION:
    Validates if a directory contains valid terrain data for scenario generation.
    Checks for DEM files, vector data, and proper directory structure.

EOF
                return 0
                ;;
            *)
                print_color $RED "Unknown option: $1"
                return 1
                ;;
        esac
    done
    
    if [[ -z "$data_dir" ]]; then
        print_color $RED "Error: --data directory is required"
        return 1
    fi
    
    if [[ ! -d "$data_dir" ]]; then
        print_color $RED "Error: Directory '$data_dir' does not exist"
        return 1
    fi
    
    print_color $BLUE "🔍 Checking data directory: $data_dir"
    
    # Check for DEM data
    if [[ -d "$data_dir/DEM" ]]; then
        local dem_files=$(find "$data_dir/DEM" -name "*.tif" -o -name "*.tiff" | wc -l)
        if [[ $dem_files -gt 0 ]]; then
            print_color $GREEN "✓ Found $dem_files DEM file(s)"
        else
            print_color $YELLOW "⚠ DEM directory exists but no .tif/.tiff files found"
        fi
    else
        print_color $YELLOW "⚠ No DEM directory found"
    fi
    
    # Check for Vector data
    if [[ -d "$data_dir/Vector" ]]; then
        local vector_files=$(find "$data_dir/Vector" -name "*.shp" | wc -l)
        if [[ $vector_files -gt 0 ]]; then
            print_color $GREEN "✓ Found $vector_files vector file(s)"
            
            # List specific vector files
            for file in "$data_dir/Vector"/*.shp; do
                if [[ -f "$file" ]]; then
                    print_color $BLUE "  - $(basename "$file")"
                fi
            done
        else
            print_color $YELLOW "⚠ Vector directory exists but no .shp files found"
        fi
    else
        print_color $YELLOW "⚠ No Vector directory found"
    fi
    
    # Overall assessment
    local dem_valid=false
    local vector_valid=false
    
    if [[ -d "$data_dir/DEM" ]] && [[ $(find "$data_dir/DEM" -name "*.tif" -o -name "*.tiff" | wc -l) -gt 0 ]]; then
        dem_valid=true
    fi
    
    if [[ -d "$data_dir/Vector" ]] && [[ $(find "$data_dir/Vector" -name "*.shp" | wc -l) -gt 0 ]]; then
        vector_valid=true
    fi
    
    if [[ "$dem_valid" == true ]] || [[ "$vector_valid" == true ]]; then
        print_color $GREEN "✅ Directory contains valid terrain data"
        return 0
    else
        print_color $RED "❌ Directory does not contain valid terrain data"
        print_color $YELLOW "Expected structure:"
        print_color $YELLOW "  $data_dir/"
        print_color $YELLOW "  ├── DEM/           (elevation data: .tif, .tiff files)"
        print_color $YELLOW "  └── Vector/        (vector data: .shp files)"
        return 1
    fi
}

# Function to handle configuration
handle_config() {
    shift # Remove 'config' from args
    
    local create_config=false
    local edit_config=false
    local config_file="$SCRIPT_DIR/scenario_generator_config.ini"
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --create|-c)
                create_config=true
                shift
                ;;
            --edit|-e)
                edit_config=true
                shift
                ;;
            --file|-f)
                config_file="$2"
                shift 2
                ;;
            --help|-h)
                cat << EOF
Configuration Management

USAGE:
    $0 config [options]

OPTIONS:
    --create, -c    Create default configuration file
    --edit, -e      Edit configuration file
    --file, -f      Specify configuration file path
    --help, -h      Show this help

DESCRIPTION:
    Manage configuration files for scenario generation.

EOF
                return 0
                ;;
            *)
                print_color $RED "Unknown option: $1"
                return 1
                ;;
        esac
    done
    
    if [[ "$create_config" == true ]]; then
        if [[ -f "$config_file" ]]; then
            print_color $YELLOW "Configuration file already exists: $config_file"
            read -p "Overwrite? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                print_color $BLUE "Keeping existing configuration"
                return 0
            fi
        fi
        
        cp "$SCRIPT_DIR/scenario_generator_config.ini" "$config_file"
        print_color $GREEN "✓ Created configuration file: $config_file"
        print_color $BLUE "Edit this file to customize scenario generation settings"
        
    elif [[ "$edit_config" == true ]]; then
        if [[ ! -f "$config_file" ]]; then
            print_color $RED "Configuration file not found: $config_file"
            print_color $BLUE "Use --create to create a default configuration file"
            return 1
        fi
        
        # Try to open with common editors
        if command -v nano &> /dev/null; then
            nano "$config_file"
        elif command -v vim &> /dev/null; then
            vim "$config_file"
        elif command -v gedit &> /dev/null; then
            gedit "$config_file"
        else
            print_color $YELLOW "No editor found. Configuration file location:"
            print_color $BLUE "$config_file"
        fi
        
    else
        print_color $BLUE "📝 Configuration file location: $config_file"
        if [[ -f "$config_file" ]]; then
            print_color $GREEN "✓ Configuration file exists"
        else
            print_color $YELLOW "⚠ Configuration file not found"
            print_color $BLUE "Use: $0 config --create"
        fi
    fi
}

# Main script logic
main() {
    if [[ $# -eq 0 ]]; then
        show_usage
        exit 1
    fi
    
    local command="$1"
    
    case "$command" in
        single)
            check_dependencies
            generate_single "$@"
            ;;
        batch)
            check_dependencies
            generate_batch "$@"
            ;;
        check)
            check_data "$@"
            ;;
        config)
            handle_config "$@"
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            print_color $RED "Unknown command: $command"
            print_color $BLUE "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"