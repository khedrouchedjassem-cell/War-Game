"""
Main simulation engine that coordinates unit movement, detection, and combat.
"""
import random
import time
from typing import List, Dict, Set, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import uuid

from core.hexgrid import HexGrid
from core.pathfinding import AStar
from core.los import LineOfSight
from models.unit import Unit, UnitSide, UnitType
from models.hexcell import HexCell
from utils.config import get_config


class SimulationState(Enum):
    """Simulation state enumeration."""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    STEP = "step"


@dataclass
class CombatResult:
    """Result of a combat engagement."""
    attacker_id: str
    target_id: str
    weapon_used: str
    hit: bool
    damage_dealt: float
    target_destroyed: bool
    turn: int


@dataclass
class DetectionEvent:
    """Detection event data."""
    observer_id: str
    target_id: str
    detected: bool
    distance: float
    turn: int


@dataclass
class MovementOrder:
    """Movement order for a unit."""
    unit_id: str
    target_q: int
    target_r: int
    path: Optional[List[Tuple[int, int]]] = None
    auto_path: bool = True


@dataclass
class AttackOrder:
    """Attack order for a unit."""
    attacker_id: str
    target_id: str
    weapon_index: int = 0


@dataclass
class SimulationLog:
    """Log entry for simulation events."""
    turn: int
    timestamp: float
    event_type: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)


class Simulation:
    """
    Main simulation engine for the wargame.
    
    Manages turns, unit actions, combat resolution, and game state.
    Provides both real-time and turn-based simulation modes.
    """
    
    def __init__(self, hex_grid: HexGrid):
        """
        Initialize simulation engine.
        
        Args:
            hex_grid: HexGrid instance for the game world
        """
        self.hex_grid = hex_grid
        self.pathfinder = AStar(hex_grid)
        self.los_calculator = LineOfSight(hex_grid)
        
        # Simulation state
        self.state = SimulationState.STOPPED
        self.current_turn = 0
        # Use config for turn duration
        config = get_config()
        self.turn_duration = config.simulation.turn_duration  # seconds per turn in real-time mode
        self.last_turn_time = 0.0
        
        # Game entities
        self.units: Dict[str, Unit] = {}
        self.red_units: Set[str] = set()
        self.blue_units: Set[str] = set()
        
        # Orders and actions
        self.movement_orders: List[MovementOrder] = []
        self.attack_orders: List[AttackOrder] = []
        
        # Simulation history
        self.combat_log: List[CombatResult] = []
        self.detection_log: List[DetectionEvent] = []
        self.simulation_log: List[SimulationLog] = []
        
        # Event callbacks
        self.on_unit_moved = None
        self.on_unit_destroyed = None
        self.on_combat_resolved = None
        self.on_detection_updated = None
        self.on_turn_completed = None
        
        # Random seed for reproducible results
        self.random_seed = None
        
        # Performance tracking
        self.turn_processing_time = 0.0
        # Movement execution tuning: how many hexes a unit may advance per simulation turn
        # Set to 1 by default to ensure multi-hex moves take multiple turns. Adjust as needed.
        self.max_hexes_per_turn = 1
        
    def set_movement_speed(self, hexes_per_turn: int):
        """Set how many hexes units can move per simulation turn."""
        self.max_hexes_per_turn = max(1, hexes_per_turn)
        self._log_event("movement_speed_changed", f"Movement speed set to {self.max_hexes_per_turn} hexes per turn")
        
    def add_unit(self, unit: Unit, q: int, r: int) -> bool:
        """
        Add a unit to the simulation.
        
        Args:
            unit: Unit to add
            q, r: Hex coordinates to place unit
            
        Returns:
            True if unit was added successfully
        """
        hex_cell = self.hex_grid.get_cell(q, r)
        if not hex_cell:
            return False
        
        if not unit.can_move_to(hex_cell):
            return False
        
        # Place unit on hex
        unit.move_to(hex_cell)
        
        # Add to simulation
        self.units[unit.id] = unit
        
        if unit.side == UnitSide.RED:
            self.red_units.add(unit.id)
        elif unit.side == UnitSide.BLUE:
            self.blue_units.add(unit.id)
        
        self._log_event("unit_added", f"Unit {unit.name} added at ({q}, {r})",
                       {"unit_id": unit.id, "position": (q, r)})
        
        return True
    
    def remove_unit(self, unit_id: str) -> bool:
        """
        Remove a unit from the simulation.
        
        Args:
            unit_id: ID of unit to remove
            
        Returns:
            True if unit was removed
        """
        if unit_id not in self.units:
            return False
        
        unit = self.units[unit_id]
        
        # Remove from hex
        if unit.position:
            unit.position.occupied_by = None
        
        # Remove from side sets
        self.red_units.discard(unit_id)
        self.blue_units.discard(unit_id)
        
        # Remove from simulation
        del self.units[unit_id]
        
        self._log_event("unit_removed", f"Unit {unit.name} removed",
                       {"unit_id": unit_id})
        
        return True
    
    def issue_movement_order(self, unit_id: str, target_q: int, target_r: int) -> bool:
        """
        Issue movement order to a unit.
        
        Args:
            unit_id: ID of unit to move
            target_q, target_r: Target hex coordinates
            
        Returns:
            True if order was accepted
        """
        if unit_id not in self.units:
            return False
        
        unit = self.units[unit_id]
        target_cell = self.hex_grid.get_cell(target_q, target_r)
        
        if not target_cell or not unit.can_move_to(target_cell):
            return False
        
        # Create movement order
        order = MovementOrder(unit_id, target_q, target_r)
        self.movement_orders.append(order)
        
        self._log_event("movement_ordered", f"Movement order for {unit.name} to ({target_q}, {target_r})",
                       {"unit_id": unit_id, "target": (target_q, target_r)})
        
        return True
    
    def issue_attack_order(self, attacker_id: str, target_id: str, weapon_index: int = 0) -> bool:
        """
        Issue attack order to a unit.
        
        Args:
            attacker_id: ID of attacking unit
            target_id: ID of target unit
            weapon_index: Index of weapon to use
            
        Returns:
            True if order was accepted
        """
        if attacker_id not in self.units or target_id not in self.units:
            return False
        
        attacker = self.units[attacker_id]
        target = self.units[target_id]
        
        if not attacker.can_engage(target):
            return False
        
        # Create attack order
        order = AttackOrder(attacker_id, target_id, weapon_index)
        self.attack_orders.append(order)
        
        self._log_event("attack_ordered", f"Attack order: {attacker.name} vs {target.name}",
                       {"attacker_id": attacker_id, "target_id": target_id})
        
        return True
    
    def start_simulation(self, seed: Optional[int] = None):
        """
        Start the simulation.
        
        Args:
            seed: Random seed for reproducible results
        """
        self.state = SimulationState.RUNNING
        self.current_turn = 0
        self.last_turn_time = time.time()
        
        if seed is not None:
            self.random_seed = seed
            random.seed(seed)
        
        self._log_event("simulation_started", "Simulation started",
                       {"seed": self.random_seed})
    
    def pause_simulation(self):
        """Pause the simulation."""
        self.state = SimulationState.PAUSED
        self._log_event("simulation_paused", "Simulation paused")
    
    def resume_simulation(self):
        """Resume the simulation."""
        if self.state == SimulationState.PAUSED:
            self.state = SimulationState.RUNNING
            self.last_turn_time = time.time()
            self._log_event("simulation_resumed", "Simulation resumed")
    
    def stop_simulation(self):
        """Stop the simulation."""
        self.state = SimulationState.STOPPED
        self._log_event("simulation_stopped", "Simulation stopped")
    
    def step_simulation(self):
        """Execute one simulation step/turn."""
        if self.state == SimulationState.STOPPED:
            self.start_simulation()
        
        start_time = time.time()
        
        # Execute turn
        self._execute_turn()
        
        # Track processing time
        self.turn_processing_time = time.time() - start_time
        
        # Update turn counter
        self.current_turn += 1
        self.last_turn_time = time.time()
        
        # Notify completion
        if self.on_turn_completed:
            self.on_turn_completed(self.current_turn)
        
        self._log_event("turn_completed", f"Turn {self.current_turn} completed",
                       {"turn": self.current_turn, "processing_time": self.turn_processing_time})
    
    def update(self) -> bool:
        """
        Update simulation (call this regularly in real-time mode).
        
        Returns:
            True if a turn was processed
        """
        if self.state != SimulationState.RUNNING:
            return False
        
        current_time = time.time()
        if current_time - self.last_turn_time >= self.turn_duration:
            self.step_simulation()
            return True
        
        return False
    
    def _execute_turn(self):
        """Execute a complete simulation turn."""
        # Phase 1: Process movement orders
        self._process_movement_phase()
        
        # Phase 2: Update visibility and detection
        self._process_detection_phase()
        
        # Phase 3: Process attack orders
        self._process_combat_phase()
        
        # Phase 4: Update unit states
        self._process_status_phase()
        
        # Phase 5: AI planning for computer-controlled units
        self._process_ai_phase()
        
        # Clear completed orders only (movement_orders are managed by _process_movement_phase)
        self.attack_orders.clear()
    
    def _process_movement_phase(self):
        """Process all movement orders incrementally.

        Each order will advance up to `self.max_hexes_per_turn` hexes (or until
        the unit's movement points are exhausted). Orders that are not complete
        are kept for the next turn.
        """
        remaining_orders: List[MovementOrder] = []

        for order in list(self.movement_orders):
            if order.unit_id not in self.units:
                continue

            unit = self.units[order.unit_id]

            # Calculate path if needed
            if order.auto_path and not order.path:
                if unit.position:
                    order.path = self.pathfinder.find_path(
                        unit.position.q, unit.position.r,
                        order.target_q, order.target_r,
                        unit
                    )
                    if order.path:
                        self._log_event("path_calculated", f"Path calculated for {unit.name}: {len(order.path)} hexes to ({order.target_q}, {order.target_r})",
                                       {"unit_id": unit.id, "path_length": len(order.path), "target": (order.target_q, order.target_r)})

            # Execute movement incrementally and get remaining path
            if order.path:
                remaining_path = self._execute_movement(unit, order.path)
                # If remaining_path still has moves left, keep the order for next turn
                if remaining_path and len(remaining_path) > 1:
                    order.path = remaining_path
                    remaining_orders.append(order)
                    self._log_event("movement_continuing", f"{unit.name} continuing journey: {len(remaining_path)-1} hexes remaining to ({order.target_q}, {order.target_r})",
                                   {"unit_id": unit.id, "hexes_remaining": len(remaining_path)-1, "target": (order.target_q, order.target_r)})
                else:
                    self._log_event("movement_completed", f"{unit.name} reached destination ({order.target_q}, {order.target_r})",
                                   {"unit_id": unit.id, "target": (order.target_q, order.target_r)})

        # Replace movement_orders with orders still pending
        self.movement_orders = remaining_orders
    
    def _execute_movement(self, unit: Unit, path: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        """
        Execute movement along a path.
        
        Args:
            unit: Unit to move
            path: List of (q, r) coordinates
        """
        if not path or len(path) <= 1:
            return path

        moved_hexes = 0
        # We will build a remaining_path to return (starts as full path)
        remaining_path = list(path)

        # Skip first position (current position)
        for i in range(1, len(path)):
            if moved_hexes >= self.max_hexes_per_turn:
                break

            q, r = path[i]
            target_cell = self.hex_grid.get_cell(q, r)

            if not target_cell:
                break

            # Check if unit can move to this cell
            if not unit.can_move_to(target_cell):
                break

            # Calculate movement cost
            cost = unit.movement_cost_to(target_cell)

            # Check if unit has enough movement points
            if cost > unit.movement_points:
                break

            # Move unit
            old_position = (unit.position.q, unit.position.r) if unit.position else None
            if unit.move_to(target_cell):
                moved_hexes += 1
                # Notify movement
                if self.on_unit_moved:
                    self.on_unit_moved(unit.id, old_position, (q, r))

                self._log_event("unit_moved", f"{unit.name} moved to ({q}, {r})",
                               {"unit_id": unit.id, "from": old_position, "to": (q, r)})
                # Remove the first visited step from remaining_path
                if len(remaining_path) > 1:
                    remaining_path.pop(1)
            else:
                break

        return remaining_path
    
    def _process_detection_phase(self):
        """Update unit detection and visibility."""
        # Clear previous detection states
        for unit in self.units.values():
            unit.detected_enemies.clear()
        
        # Calculate mutual detection
        active_units = [unit for unit in self.units.values() if unit.is_alive]
        
        for i, observer in enumerate(active_units):
            for j, target in enumerate(active_units):
                if i != j and observer.side != target.side:
                    # Check if observer can detect target
                    can_detect = self.los_calculator.can_see(observer, target)
                    
                    if can_detect:
                        observer.detected_enemies[target.id] = self.current_turn
                        
                        # Log detection event
                        distance = observer.distance_to(target)
                        detection_event = DetectionEvent(
                            observer.id, target.id, True, distance, self.current_turn
                        )
                        self.detection_log.append(detection_event)
                        
                        if self.on_detection_updated:
                            self.on_detection_updated(observer.id, target.id, True)
    
    def _process_combat_phase(self):
        """Process all attack orders."""
        for order in self.attack_orders:
            if order.attacker_id not in self.units or order.target_id not in self.units:
                continue
            
            attacker = self.units[order.attacker_id]
            target = self.units[order.target_id]
            
            # Verify attack is still valid
            if not attacker.can_engage(target):
                continue
            
            # Execute combat
            self._resolve_combat(attacker, target, order.weapon_index)
    
    def _resolve_combat(self, attacker: Unit, target: Unit, weapon_index: int):
        """
        Resolve combat between two units.
        
        Args:
            attacker: Attacking unit
            target: Target unit
            weapon_index: Index of weapon to use
        """
        if weapon_index >= len(attacker.weapons):
            return
        
        weapon = attacker.weapons[weapon_index]
        distance = attacker.distance_to(target)
        
        # Calculate hit probability
        target_cover = 0.0
        if target.position:
            # Calculate cover from attacker's direction
            bearing = 0.0  # Would calculate bearing in real implementation
            target_cover = target.position.get_cover_for_direction(bearing)
        
        hit_probability = weapon.hit_probability(distance, target_cover)
        
        # Apply experience modifiers
        hit_probability *= (attacker.experience / 100.0)
        
        # Apply suppression effects
        hit_probability *= max(0.5, 1.0 - attacker.suppression_level / 100.0)
        
        # Roll for hit
        hit = random.random() < hit_probability
        
        damage_dealt = 0.0
        target_destroyed = False
        
        if hit:
            # Calculate damage
            base_damage = weapon.damage
            
            # Apply random variation
            damage_variation = random.uniform(0.8, 1.2)
            damage_dealt = base_damage * damage_variation * 10  # Scale damage
            
            # Apply damage to target
            target.take_damage(damage_dealt)
            
            # Check if target is destroyed
            if target.strength <= 0:
                target_destroyed = True
                target.is_active = False
                
                # Remove from hex
                if target.position:
                    target.position.occupied_by = None
                
                # Notify destruction
                if self.on_unit_destroyed:
                    self.on_unit_destroyed(target.id)
                
                self._log_event("unit_destroyed", f"{target.name} destroyed by {attacker.name}",
                               {"attacker_id": attacker.id, "target_id": target.id})
            
            # Apply suppression to target
            target.suppression_level = min(100.0, target.suppression_level + damage_dealt)
        
        # Create combat result
        combat_result = CombatResult(
            attacker.id, target.id, weapon.name, hit, damage_dealt, target_destroyed, self.current_turn
        )
        
        self.combat_log.append(combat_result)
        
        # Update attacker's last fired turn
        attacker.last_fired = self.current_turn
        
        # Notify combat resolution
        if self.on_combat_resolved:
            self.on_combat_resolved(combat_result)
        
        self._log_event("combat_resolved", 
                       f"{attacker.name} {'hit' if hit else 'missed'} {target.name} with {weapon.name}",
                       {"attacker_id": attacker.id, "target_id": target.id, 
                        "weapon": weapon.name, "hit": hit, "damage": damage_dealt})
    
    def _process_status_phase(self):
        """Update unit status and recovery."""
        for unit in self.units.values():
            if unit.is_alive:
                # Restore movement points
                unit.restore_movement()
                
                # Natural healing/repair
                if unit.strength < unit.max_strength:
                    healing = min(2.0, unit.max_strength - unit.strength)
                    unit.strength += healing
                
                # Morale recovery
                if unit.morale < 100.0:
                    morale_recovery = 5.0
                    unit.morale = min(100.0, unit.morale + morale_recovery)
    
    def _process_ai_phase(self):
        """Process AI decisions for computer-controlled units."""
        # This is a simplified AI implementation
        # In a full game, this would be much more sophisticated
        
        for unit in self.units.values():
            if not unit.is_alive or not hasattr(unit, 'ai_controlled') or not unit.ai_controlled:
                continue
            
            # Simple AI: attack nearest enemy if visible
            nearest_enemy = self._find_nearest_enemy(unit)
            if nearest_enemy and unit.can_engage(nearest_enemy):
                self.issue_attack_order(unit.id, nearest_enemy.id)
            elif nearest_enemy:
                # Move towards enemy
                if unit.position and nearest_enemy.position:
                    self.issue_movement_order(unit.id, nearest_enemy.position.q, nearest_enemy.position.r)
    
    def _find_nearest_enemy(self, unit: Unit) -> Optional[Unit]:
        """Find nearest enemy unit that this unit can detect."""
        nearest_enemy = None
        min_distance = float('inf')
        
        for enemy_id in unit.detected_enemies:
            if enemy_id in self.units:
                enemy = self.units[enemy_id]
                if enemy.is_alive:
                    distance = unit.distance_to(enemy)
                    if distance < min_distance:
                        min_distance = distance
                        nearest_enemy = enemy
        
        return nearest_enemy
    
    def _log_event(self, event_type: str, message: str, data: Optional[Dict[str, Any]] = None):
        """
        Log a simulation event.
        
        Args:
            event_type: Type of event
            message: Human-readable message
            data: Additional event data
        """
        log_entry = SimulationLog(
            turn=self.current_turn,
            timestamp=time.time(),
            event_type=event_type,
            message=message,
            data=data or {}
        )
        
        self.simulation_log.append(log_entry)
    
    def get_simulation_stats(self) -> Dict[str, Any]:
        """Get simulation statistics."""
        active_units = [unit for unit in self.units.values() if unit.is_alive]
        red_active = len([unit for unit in active_units if unit.side == UnitSide.RED])
        blue_active = len([unit for unit in active_units if unit.side == UnitSide.BLUE])
        
        return {
            'current_turn': self.current_turn,
            'state': self.state.value,
            'total_units': len(self.units),
            'active_units': len(active_units),
            'red_units': red_active,
            'blue_units': blue_active,
            'combat_engagements': len(self.combat_log),
            'turn_processing_time': self.turn_processing_time,
            'log_entries': len(self.simulation_log)
        }
    
    def reset_simulation(self):
        """Reset simulation to initial state."""
        self.state = SimulationState.STOPPED
        self.current_turn = 0
        self.last_turn_time = 0.0
        
        # Clear units
        for unit in self.units.values():
            if unit.position:
                unit.position.occupied_by = None
        
        self.units.clear()
        self.red_units.clear()
        self.blue_units.clear()
        
        # Clear orders and history
        self.movement_orders.clear()
        self.attack_orders.clear()
        self.combat_log.clear()
        self.detection_log.clear()
        self.simulation_log.clear()
        
        # Clear caches
        self.los_calculator.clear_cache()
        
        self._log_event("simulation_reset", "Simulation reset to initial state")