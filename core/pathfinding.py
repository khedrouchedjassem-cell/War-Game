"""
A* pathfinding algorithm implementation for hexagonal grids.
"""
import heapq
import math
from typing import List, Tuple, Optional, Dict, Set, Callable
from dataclasses import dataclass, field

from core.hexgrid import HexGrid
from models.hexcell import HexCell
from models.unit import Unit


@dataclass
class PathNode:
    """
    Represents a node in the pathfinding algorithm.
    """
    q: int  # Axial coordinate q
    r: int  # Axial coordinate r
    g_cost: float = 0.0  # Cost from start
    h_cost: float = 0.0  # Heuristic cost to goal
    parent: Optional['PathNode'] = None
    
    @property
    def f_cost(self) -> float:
        """Total cost (g + h)."""
        return self.g_cost + self.h_cost
    
    def __lt__(self, other: 'PathNode') -> bool:
        """For heap ordering."""
        return self.f_cost < other.f_cost
    
    def __eq__(self, other: 'PathNode') -> bool:
        """Equality comparison."""
        return self.q == other.q and self.r == other.r
    
    def __hash__(self) -> int:
        """Hash for set/dict usage."""
        return hash((self.q, self.r))


class AStar:
    """
    A* pathfinding algorithm for hexagonal grids.
    
    Finds optimal paths considering terrain costs, unit capabilities,
    and dynamic obstacles like other units or zones of control.
    """
    
    def __init__(self, hex_grid: HexGrid):
        """
        Initialize A* pathfinder.
        
        Args:
            hex_grid: HexGrid instance to pathfind on
        """
        self.hex_grid = hex_grid
        self.open_set: List[PathNode] = []
        self.closed_set: Set[Tuple[int, int]] = set()
        self.nodes: Dict[Tuple[int, int], PathNode] = {}
        
        # Pathfinding options
        self.allow_diagonal = True
        self.heuristic_weight = 1.0
        self.max_iterations = 10000
    
    def find_path(self, start_q: int, start_r: int, goal_q: int, goal_r: int,
                  unit: Unit, avoid_enemies: bool = True, 
                  max_cost: Optional[float] = None) -> Optional[List[Tuple[int, int]]]:
        """
        Find a path from start to goal using A* algorithm.
        
        Args:
            start_q, start_r: Starting hex coordinates
            goal_q, goal_r: Goal hex coordinates
            unit: Unit that will follow the path
            avoid_enemies: Whether to avoid enemy units and zones of control
            max_cost: Maximum path cost (for movement points limitation)
            
        Returns:
            List of (q, r) coordinates forming the path, or None if no path found
        """
        # Validate inputs
        start_cell = self.hex_grid.get_cell(start_q, start_r)
        goal_cell = self.hex_grid.get_cell(goal_q, goal_r)
        
        if not start_cell or not goal_cell:
            return None
        
        if not goal_cell.is_passable(unit.movement_type.value):
            return None
        
        if start_q == goal_q and start_r == goal_r:
            return [(start_q, start_r)]
        
        # Initialize pathfinding state
        self._reset()
        
        # Create start node
        start_node = PathNode(start_q, start_r, 0.0, 
                            self._heuristic(start_q, start_r, goal_q, goal_r))
        
        heapq.heappush(self.open_set, start_node)
        self.nodes[(start_q, start_r)] = start_node
        
        iterations = 0
        
        while self.open_set and iterations < self.max_iterations:
            iterations += 1
            
            # Get node with lowest f_cost
            current = heapq.heappop(self.open_set)
            self.closed_set.add((current.q, current.r))
            
            # Check if we reached the goal
            if current.q == goal_q and current.r == goal_r:
                return self._reconstruct_path(current)
            
            # Examine neighbors
            neighbors = self.hex_grid.get_neighbors(current.q, current.r)
            
            for neighbor_cell in neighbors:
                neighbor_coords = (neighbor_cell.q, neighbor_cell.r)
                
                # Skip if already processed
                if neighbor_coords in self.closed_set:
                    continue
                
                # Calculate movement cost
                move_cost = self._calculate_movement_cost(
                    current, neighbor_cell, unit, avoid_enemies
                )
                
                # Skip impassable cells
                if move_cost == float('inf'):
                    continue
                
                tentative_g = current.g_cost + move_cost
                
                # Skip if exceeds maximum cost
                if max_cost is not None and tentative_g > max_cost:
                    continue
                
                # Get or create neighbor node
                if neighbor_coords not in self.nodes:
                    neighbor_node = PathNode(
                        neighbor_cell.q, neighbor_cell.r, float('inf'),
                        self._heuristic(neighbor_cell.q, neighbor_cell.r, goal_q, goal_r)
                    )
                    self.nodes[neighbor_coords] = neighbor_node
                else:
                    neighbor_node = self.nodes[neighbor_coords]
                
                # Check if this path is better
                if tentative_g < neighbor_node.g_cost:
                    neighbor_node.g_cost = tentative_g
                    neighbor_node.parent = current
                    
                    # Add to open set if not already there
                    if neighbor_coords not in self.closed_set:
                        if neighbor_node not in self.open_set:
                            heapq.heappush(self.open_set, neighbor_node)
        
        # No path found
        return None
    
    def find_reachable_hexes(self, start_q: int, start_r: int, unit: Unit,
                           max_movement: float) -> Dict[Tuple[int, int], float]:
        """
        Find all hexes reachable within movement range.
        
        Args:
            start_q, start_r: Starting position
            unit: Unit doing the movement
            max_movement: Maximum movement points available
            
        Returns:
            Dictionary mapping (q, r) coordinates to movement cost
        """
        reachable = {}
        
        # Use Dijkstra's algorithm for reachability
        start_cell = self.hex_grid.get_cell(start_q, start_r)
        if not start_cell:
            return reachable
        
        # Priority queue: (cost, q, r)
        pq = [(0.0, start_q, start_r)]
        visited = set()
        
        while pq:
            cost, q, r = heapq.heappop(pq)
            
            if (q, r) in visited:
                continue
            
            if cost > max_movement:
                continue
            
            visited.add((q, r))
            reachable[(q, r)] = cost
            
            # Check neighbors
            cell = self.hex_grid.get_cell(q, r)
            if not cell:
                continue
            
            neighbors = self.hex_grid.get_neighbors(q, r)
            for neighbor_cell in neighbors:
                neighbor_coords = (neighbor_cell.q, neighbor_cell.r)
                
                if neighbor_coords in visited:
                    continue
                
                move_cost = neighbor_cell.get_movement_cost(unit.movement_type.value)
                if move_cost == float('inf'):
                    continue
                
                new_cost = cost + move_cost
                if new_cost <= max_movement:
                    heapq.heappush(pq, (new_cost, neighbor_cell.q, neighbor_cell.r))
        
        return reachable
    
    def find_best_position_for_attack(self, attacker_q: int, attacker_r: int,
                                    target_q: int, target_r: int, unit: Unit,
                                    max_movement: float) -> Optional[Tuple[int, int]]:
        """
        Find the best position within movement range to attack a target.
        
        Args:
            attacker_q, attacker_r: Current attacker position
            target_q, target_r: Target position
            unit: Attacking unit
            max_movement: Available movement points
            
        Returns:
            Best attack position as (q, r) or None
        """
        reachable = self.find_reachable_hexes(attacker_q, attacker_r, unit, max_movement)
        
        best_position = None
        best_score = float('-inf')
        
        target_cell = self.hex_grid.get_cell(target_q, target_r)
        if not target_cell:
            return None
        
        for (q, r), move_cost in reachable.items():
            cell = self.hex_grid.get_cell(q, r)
            if not cell:
                continue
            
            # Calculate distance to target
            distance = self.hex_grid.world_distance(q, r, target_q, target_r)
            
            # Check if target is in weapon range
            if distance > unit.max_weapon_range:
                continue
            
            # Calculate attack score
            score = self._calculate_attack_score(cell, target_cell, distance, move_cost)
            
            if score > best_score:
                best_score = score
                best_position = (q, r)
        
        return best_position
    
    def find_retreat_position(self, unit_q: int, unit_r: int, threat_positions: List[Tuple[int, int]],
                            unit: Unit, max_movement: float) -> Optional[Tuple[int, int]]:
        """
        Find a good retreat position away from threats.
        
        Args:
            unit_q, unit_r: Current unit position
            threat_positions: List of (q, r) coordinates of threats
            unit: Retreating unit
            max_movement: Available movement points
            
        Returns:
            Best retreat position as (q, r) or None
        """
        reachable = self.find_reachable_hexes(unit_q, unit_r, unit, max_movement)
        
        best_position = None
        best_score = float('-inf')
        
        for (q, r), move_cost in reachable.items():
            cell = self.hex_grid.get_cell(q, r)
            if not cell:
                continue
            
            # Calculate retreat score based on distance from threats and cover
            score = self._calculate_retreat_score(cell, threat_positions, move_cost)
            
            if score > best_score:
                best_score = score
                best_position = (q, r)
        
        return best_position
    
    def _reset(self):
        """Reset pathfinding state."""
        self.open_set.clear()
        self.closed_set.clear()
        self.nodes.clear()
    
    def _heuristic(self, q1: int, r1: int, q2: int, r2: int) -> float:
        """
        Calculate heuristic distance between two hex coordinates.
        
        Uses hex distance multiplied by minimum movement cost.
        """
        hex_dist = self.hex_grid.hex_distance(q1, r1, q2, r2)
        return hex_dist * self.heuristic_weight
    
    def _calculate_movement_cost(self, current: PathNode, target_cell: HexCell,
                               unit: Unit, avoid_enemies: bool) -> float:
        """
        Calculate movement cost from current node to target cell.
        
        Args:
            current: Current path node
            target_cell: Target hex cell
            unit: Moving unit
            avoid_enemies: Whether to avoid enemy units
            
        Returns:
            Movement cost or infinity if impassable
        """
        # Basic movement cost
        base_cost = target_cell.get_movement_cost(unit.movement_type.value)
        
        if base_cost == float('inf'):
            return float('inf')
        
        # Check if cell is occupied by another unit
        if target_cell.occupied_by and target_cell.occupied_by != unit:
            # Can't move through enemy units
            if target_cell.occupied_by.side != unit.side:
                return float('inf')
            # Friendly units can be moved through but at higher cost
            else:
                base_cost *= 2.0
        
        # Avoid enemy zones of control
        if avoid_enemies:
            enemy_penalty = self._calculate_enemy_penalty(target_cell, unit)
            base_cost += enemy_penalty
        
        return base_cost
    
    def _calculate_enemy_penalty(self, cell: HexCell, unit: Unit) -> float:
        """
        Calculate penalty for moving near enemy units.
        
        Args:
            cell: Target cell
            unit: Moving unit
            
        Returns:
            Additional movement cost penalty
        """
        penalty = 0.0
        
        # Check nearby cells for enemy units
        neighbors = self.hex_grid.get_neighbors(cell.q, cell.r)
        
        for neighbor in neighbors:
            if neighbor.occupied_by and neighbor.occupied_by.side != unit.side:
                enemy = neighbor.occupied_by
                
                # Add penalty based on enemy threat level
                if enemy.unit_type.value in ['tank', 'artillery']:
                    penalty += 2.0  # High threat units
                else:
                    penalty += 1.0  # Standard threat
        
        return penalty
    
    def _calculate_attack_score(self, position: HexCell, target: HexCell,
                              distance: float, move_cost: float) -> float:
        """
        Calculate score for an attack position.
        
        Higher scores are better positions.
        """
        score = 0.0
        
        # Prefer closer positions (but not too close)
        if distance > 100:  # Minimum safe distance
            score += max(0, 1000 - distance)  # Closer is better
        else:
            score -= 500  # Penalty for being too close
        
        # Prefer positions with good cover
        score += position.cover_value * 200
        
        # Prefer positions with concealment
        score += position.concealment * 150
        
        # Penalty for movement cost (prefer positions that are easier to reach)
        score -= move_cost * 50
        
        # Prefer higher elevation for better LOS
        elevation_diff = position.elevation_mean - target.elevation_mean
        if elevation_diff > 0:
            score += elevation_diff * 10
        
        return score
    
    def _calculate_retreat_score(self, position: HexCell, threats: List[Tuple[int, int]],
                               move_cost: float) -> float:
        """
        Calculate score for a retreat position.
        
        Higher scores are better retreat positions.
        """
        score = 0.0
        
        # Calculate minimum distance to any threat
        min_threat_distance = float('inf')
        for threat_q, threat_r in threats:
            distance = self.hex_grid.world_distance(position.q, position.r, threat_q, threat_r)
            min_threat_distance = min(min_threat_distance, distance)
        
        # Prefer positions farther from threats
        score += min_threat_distance
        
        # Strongly prefer positions with good cover
        score += position.cover_value * 500
        
        # Prefer positions with concealment
        score += position.concealment * 300
        
        # Penalty for movement cost
        score -= move_cost * 100
        
        # Prefer positions that are not in the open
        if position.terrain_type in ['flat', 'water']:
            score -= 200
        
        return score
    
    def _reconstruct_path(self, goal_node: PathNode) -> List[Tuple[int, int]]:
        """
        Reconstruct path from goal node back to start.
        
        Args:
            goal_node: The goal node reached by pathfinding
            
        Returns:
            List of (q, r) coordinates from start to goal
        """
        path = []
        current = goal_node
        
        while current:
            path.append((current.q, current.r))
            current = current.parent
        
        path.reverse()
        return path
    
    def get_path_cost(self, path: List[Tuple[int, int]], unit: Unit) -> float:
        """
        Calculate total movement cost for a path.
        
        Args:
            path: List of (q, r) coordinates
            unit: Unit that will follow the path
            
        Returns:
            Total movement cost
        """
        if len(path) <= 1:
            return 0.0
        
        total_cost = 0.0
        
        for i in range(1, len(path)):
            q, r = path[i]
            cell = self.hex_grid.get_cell(q, r)
            if cell:
                cost = cell.get_movement_cost(unit.movement_type.value)
                total_cost += cost
            else:
                return float('inf')  # Invalid path
        
        return total_cost
    
    def smooth_path(self, path: List[Tuple[int, int]], unit: Unit) -> List[Tuple[int, int]]:
        """
        Smooth path by removing unnecessary waypoints.
        
        Args:
            path: Original path
            unit: Unit that will follow the path
            
        Returns:
            Smoothed path with fewer waypoints
        """
        if len(path) <= 2:
            return path
        
        smoothed = [path[0]]
        current_idx = 0
        
        while current_idx < len(path) - 1:
            # Try to find the farthest reachable point
            farthest_idx = current_idx + 1
            
            for test_idx in range(current_idx + 2, len(path)):
                # Check if we can move directly from current to test position
                if self._can_move_directly(path[current_idx], path[test_idx], unit):
                    farthest_idx = test_idx
                else:
                    break
            
            smoothed.append(path[farthest_idx])
            current_idx = farthest_idx
        
        return smoothed
    
    def _can_move_directly(self, start: Tuple[int, int], end: Tuple[int, int], unit: Unit) -> bool:
        """
        Check if unit can move directly between two points without obstacles.
        
        Args:
            start: Starting (q, r) coordinates
            end: Ending (q, r) coordinates
            unit: Moving unit
            
        Returns:
            True if direct movement is possible
        """
        # Get line of hexes between start and end
        line_hexes = self.hex_grid.get_line_of_hexes(start[0], start[1], end[0], end[1])
        
        # Check each hex in the line
        for q, r in line_hexes[1:]:  # Skip starting position
            cell = self.hex_grid.get_cell(q, r)
            if not cell or not cell.is_passable(unit.movement_type.value):
                return False
            
            # Check for enemy units
            if cell.occupied_by and cell.occupied_by.side != unit.side:
                return False
        
        return True