#!/usr/bin/env python3
"""
Military Unit Icon Generator
Creates SVG icons based on Russian/NATO military symbology standards.
"""

import os
from pathlib import Path
from typing import Dict, Tuple

def create_svg_icon(symbol: str, color: str, size: int = 64) -> str:
    """Create SVG icon with military symbol."""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <style>
            .unit-bg {{ fill: {color}; stroke: #000; stroke-width: 2; }}
            .unit-symbol {{ fill: #000; stroke: none; font-family: Arial, sans-serif; font-weight: bold; text-anchor: middle; dominant-baseline: central; }}
        </style>
    </defs>
    {symbol}
</svg>'''

def create_infantry_icon(color: str, size: int = 64) -> str:
    """Create infantry unit icon (rectangle with X)."""
    symbol = f'''
    <rect class="unit-bg" x="8" y="16" width="{size-16}" height="{size-32}" rx="4"/>
    <line x1="16" y1="24" x2="{size-16}" y2="{size-24}" stroke="#000" stroke-width="3"/>
    <line x1="{size-16}" y1="24" x2="16" y2="{size-24}" stroke="#000" stroke-width="3"/>
    '''
    return create_svg_icon(symbol, color, size)

def create_armor_icon(color: str, size: int = 64) -> str:
    """Create armored unit icon (oval with tank symbol)."""
    symbol = f'''
    <ellipse class="unit-bg" cx="{size//2}" cy="{size//2}" rx="{size//2-8}" ry="{size//2-12}"/>
    <rect x="{size//2-16}" y="{size//2-6}" width="32" height="12" fill="#000" rx="2"/>
    <rect x="{size//2-2}" y="{size//2-12}" width="4" height="12" fill="#000"/>
    <circle cx="{size//2-10}" cy="{size//2}" r="3" fill="#000"/>
    <circle cx="{size//2+10}" cy="{size//2}" r="3" fill="#000"/>
    '''
    return create_svg_icon(symbol, color, size)

def create_artillery_icon(color: str, size: int = 64) -> str:
    """Create artillery unit icon (rectangle with circle)."""
    symbol = f'''
    <rect class="unit-bg" x="8" y="16" width="{size-16}" height="{size-32}" rx="4"/>
    <circle cx="{size//2}" cy="{size//2}" r="12" fill="none" stroke="#000" stroke-width="3"/>
    <circle cx="{size//2}" cy="{size//2}" r="4" fill="#000"/>
    '''
    return create_svg_icon(symbol, color, size)

def create_recon_icon(color: str, size: int = 64) -> str:
    """Create reconnaissance unit icon (diamond)."""
    symbol = f'''
    <polygon class="unit-bg" points="{size//2},8 {size-8},{size//2} {size//2},{size-8} 8,{size//2}"/>
    <text class="unit-symbol" x="{size//2}" y="{size//2}" font-size="16">R</text>
    '''
    return create_svg_icon(symbol, color, size)

def create_command_icon(color: str, size: int = 64) -> str:
    """Create command unit icon (hexagon with star)."""
    h = size // 2
    w = int(h * 0.866)  # height of hexagon side
    symbol = f'''
    <polygon class="unit-bg" points="{h},{8} {h+w},{h//2+4} {h+w},{h+h//2-4} {h},{size-8} {h-w},{h+h//2-4} {h-w},{h//2+4}"/>
    <polygon points="{h},{h-8} {h+6},{h-2} {h+10},{h+6} {h+4},{h+6} {h},{h+12} {h-4},{h+6} {h-10},{h+6} {h-6},{h-2}" fill="#000"/>
    '''
    return create_svg_icon(symbol, color, size)

def create_support_icon(color: str, size: int = 64) -> str:
    """Create support unit icon (rectangle with +)."""
    symbol = f'''
    <rect class="unit-bg" x="8" y="16" width="{size-16}" height="{size-32}" rx="4"/>
    <line x1="{size//2}" y1="24" x2="{size//2}" y2="{size-24}" stroke="#000" stroke-width="4"/>
    <line x1="16" y1="{size//2}" x2="{size-16}" y2="{size//2}" stroke="#000" stroke-width="4"/>
    '''
    return create_svg_icon(symbol, color, size)

def create_air_defense_icon(color: str, size: int = 64) -> str:
    """Create air defense unit icon (rectangle with triangle)."""
    symbol = f'''
    <rect class="unit-bg" x="8" y="16" width="{size-16}" height="{size-32}" rx="4"/>
    <polygon points="{size//2},{size//2-8} {size//2-8},{size//2+8} {size//2+8},{size//2+8}" fill="#000"/>
    <line x1="{size//2}" y1="{size//2-8}" x2="{size//2}" y2="{size//2-16}" stroke="#000" stroke-width="2"/>
    '''
    return create_svg_icon(symbol, color, size)

def create_engineer_icon(color: str, size: int = 64) -> str:
    """Create engineer unit icon (rectangle with crossed tools)."""
    symbol = f'''
    <rect class="unit-bg" x="8" y="16" width="{size-16}" height="{size-32}" rx="4"/>
    <line x1="18" y1="26" x2="{size-18}" y2="{size-26}" stroke="#000" stroke-width="3"/>
    <line x1="{size-18}" y1="26" x2="18" y2="{size-26}" stroke="#000" stroke-width="3"/>
    <rect x="16" y="{size//2-2}" width="6" height="4" fill="#000"/>
    <rect x="{size-22}" y="{size//2-2}" width="6" height="4" fill="#000"/>
    '''
    return create_svg_icon(symbol, color, size)

def generate_unit_icons(output_dir: Path):
    """Generate all military unit icons."""
    # Color schemes for different sides
    colors = {
        'red': '#DC143C',    # Red side
        'blue': '#1E90FF',   # Blue side
        'neutral': '#808080' # Neutral/Unknown
    }
    
    # Unit types and their icon generators
    unit_types = {
        'infantry': create_infantry_icon,
        'armor': create_armor_icon,
        'tank': create_armor_icon,  # Alias for armor
        'artillery': create_artillery_icon,
        'recon': create_recon_icon,
        'command': create_command_icon,
        'support': create_support_icon,
        'air_defense': create_air_defense_icon,
        'engineer': create_engineer_icon,
    }
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate icons for each combination
    for side, color in colors.items():
        for unit_type, icon_func in unit_types.items():
            # Create icon
            svg_content = icon_func(color)
            
            # Save to file
            filename = f"{side}_{unit_type}.svg"
            filepath = output_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(svg_content)
            
            print(f"Created: {filename}")

def create_generic_icons(output_dir: Path):
    """Create generic UI icons."""
    
    # Zoom in icon
    zoom_in_svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <circle cx="11" cy="11" r="8" fill="none" stroke="#000" stroke-width="2"/>
    <path d="m21 21-4.35-4.35"/>
    <line x1="8" y1="11" x2="14" y2="11" stroke="#000" stroke-width="2"/>
    <line x1="11" y1="8" x2="11" y2="14" stroke="#000" stroke-width="2"/>
</svg>'''
    
    # Zoom out icon
    zoom_out_svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <circle cx="11" cy="11" r="8" fill="none" stroke="#000" stroke-width="2"/>
    <path d="m21 21-4.35-4.35"/>
    <line x1="8" y1="11" x2="14" y2="11" stroke="#000" stroke-width="2"/>
</svg>'''
    
    # Fit to view icon
    fit_view_svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <rect x="3" y="3" width="18" height="18" fill="none" stroke="#000" stroke-width="2" rx="2"/>
    <polyline points="9,9 15,9 15,15 9,15 9,9" fill="none" stroke="#000" stroke-width="2"/>
    <path d="M7 13L3 17M17 7L21 3M7 7L3 3M17 17L21 21"/>
</svg>'''
    
    # Play icon
    play_svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <polygon points="5,3 19,12 5,21" fill="#22C55E"/>
</svg>'''
    
    # Pause icon
    pause_svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <rect x="6" y="4" width="4" height="16" fill="#F59E0B"/>
    <rect x="14" y="4" width="4" height="16" fill="#F59E0B"/>
</svg>'''
    
    # Step icon
    step_svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <polygon points="5,3 15,12 5,21" fill="#3B82F6"/>
    <rect x="17" y="4" width="2" height="16" fill="#3B82F6"/>
</svg>'''
    
    # Reset icon
    reset_svg = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <polyline points="1,4 1,10 7,10" fill="none" stroke="#EF4444" stroke-width="2"/>
    <path d="M3.51,15a9,9,0,0,0,2.13,3.09,9,9,0,0,0,13.62,0,9,9,0,0,0,0-12.72,9,9,0,0,0-13.62,0A8.84,8.84,0,0,0,3.51,9" fill="none" stroke="#EF4444" stroke-width="2"/>
</svg>'''
    
    # Save generic icons
    generic_icons = {
        'zoom_in.svg': zoom_in_svg,
        'zoom_out.svg': zoom_out_svg,
        'fit_view.svg': fit_view_svg,
        'play.svg': play_svg,
        'pause.svg': pause_svg,
        'step.svg': step_svg,
        'reset.svg': reset_svg,
    }
    
    for filename, svg_content in generic_icons.items():
        filepath = output_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        print(f"Created: {filename}")

if __name__ == "__main__":
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    icons_dir = project_root / "ui" / "icons"
    
    print(f"Generating icons in: {icons_dir}")
    
    # Generate all icons
    generate_unit_icons(icons_dir)
    create_generic_icons(icons_dir)
    
    print(f"\nGenerated {len(list(icons_dir.glob('*.svg')))} icons successfully!")
    print("Icons are ready for use in the application.")