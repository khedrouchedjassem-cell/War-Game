"""
Icon manager for the wargame application.
Provides easy access to military unit icons and UI icons.
"""

from pathlib import Path
from typing import Optional, Dict
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import QSize

class IconManager:
    """Manages application icons with caching and easy access."""
    
    def __init__(self):
        self.icons_dir = Path(__file__).parent.parent / "ui" / "icons"
        self._icon_cache: Dict[str, QIcon] = {}
        
    def get_unit_icon(self, unit_type: str, side: str, size: Optional[QSize] = None) -> QIcon:
        """
        Get icon for a military unit.
        
        Args:
            unit_type: Type of unit (infantry, armor, artillery, etc.)
            side: Side (red, blue, neutral)
            size: Optional size for the icon
            
        Returns:
            QIcon object for the unit
        """
        # Normalize unit type names
        unit_type = unit_type.lower().replace(' ', '_')
        side = side.lower()
        
        # Handle aliases
        if unit_type in ['tank', 'armored']:
            unit_type = 'armor'
        elif unit_type in ['reconnaissance']:
            unit_type = 'recon'
        elif unit_type in ['cmd', 'headquarters']:
            unit_type = 'command'
        elif unit_type in ['infantry_squad', 'infantry_team']:
            unit_type = 'infantry'
        
        filename = f"{side}_{unit_type}.svg"
        return self._get_icon(filename, size)
    
    def get_ui_icon(self, icon_name: str, size: Optional[QSize] = None) -> QIcon:
        """
        Get UI icon.
        
        Args:
            icon_name: Name of the icon (zoom_in, zoom_out, play, etc.)
            size: Optional size for the icon
            
        Returns:
            QIcon object
        """
        if not icon_name.endswith('.svg'):
            icon_name += '.svg'
        
        return self._get_icon(icon_name, size)
    
    def _get_icon(self, filename: str, size: Optional[QSize] = None) -> QIcon:
        """
        Internal method to get icon with caching.
        
        Args:
            filename: Icon filename
            size: Optional size
            
        Returns:
            QIcon object
        """
        cache_key = f"{filename}_{size.width() if size else 'default'}x{size.height() if size else 'default'}"
        
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]
        
        icon_path = self.icons_dir / filename
        
        if not icon_path.exists():
            # Return empty icon if file doesn't exist
            print(f"Warning: Icon not found: {icon_path}")
            return QIcon()
        
        icon = QIcon(str(icon_path))
        
        # Apply size if specified
        if size:
            pixmap = icon.pixmap(size)
            icon = QIcon(pixmap)
        
        # Cache the icon
        self._icon_cache[cache_key] = icon
        
        return icon
    
    def get_available_unit_types(self) -> list:
        """Get list of available unit types."""
        unit_types = set()
        
        for icon_file in self.icons_dir.glob("*_*.svg"):
            if icon_file.stem.startswith(('red_', 'blue_', 'neutral_')):
                unit_type = icon_file.stem.split('_', 1)[1]
                unit_types.add(unit_type)
        
        return sorted(list(unit_types))
    
    def get_available_sides(self) -> list:
        """Get list of available sides."""
        return ['red', 'blue', 'neutral']
    
    def clear_cache(self):
        """Clear the icon cache."""
        self._icon_cache.clear()

# Global icon manager instance
_icon_manager = None

def get_icon_manager() -> IconManager:
    """Get the global icon manager instance."""
    global _icon_manager
    if _icon_manager is None:
        _icon_manager = IconManager()
    return _icon_manager

def get_unit_icon(unit_type: str, side: str, size: Optional[QSize] = None) -> QIcon:
    """Convenience function to get unit icon."""
    return get_icon_manager().get_unit_icon(unit_type, side, size)

def get_ui_icon(icon_name: str, size: Optional[QSize] = None) -> QIcon:
    """Convenience function to get UI icon."""
    return get_icon_manager().get_ui_icon(icon_name, size)