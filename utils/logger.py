"""
Enhanced logging system for wargame simulation.

Provides comprehensive logging capabilities with multiple levels,
file rotation, error tracing, and performance monitoring.
"""
import logging
import logging.handlers
import sys
import traceback
import functools
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Any, Dict
from PyQt6.QtCore import QObject, pyqtSignal


class LogLevel:
    """Standard logging levels with descriptions."""
    CRITICAL = logging.CRITICAL  # 50
    ERROR = logging.ERROR        # 40
    WARNING = logging.WARNING    # 30
    INFO = logging.INFO          # 20
    DEBUG = logging.DEBUG        # 10


class ColoredFormatter(logging.Formatter):
    """Colored console formatter for better readability."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        # Add color to levelname
        if record.levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[record.levelname]}{record.levelname}"
                f"{self.COLORS['RESET']}"
            )
        
        return super().format(record)


class PerformanceTimer:
    """Context manager for timing operations."""
    
    def __init__(self, operation_name: str, logger: logging.Logger):
        self.operation_name = operation_name
        self.logger = logger
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        self.logger.debug(f"Starting operation: {self.operation_name}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration = time.perf_counter() - self.start_time
            if exc_type is None:
                self.logger.debug(f"Operation '{self.operation_name}' completed in {duration:.4f}s")
            else:
                self.logger.error(f"Operation '{self.operation_name}' failed after {duration:.4f}s: {exc_val}")


class LogEmitter(QObject):
    """Qt signal emitter for log messages."""
    
    log_message = pyqtSignal(str, str, str)  # level, logger_name, message
    
    def emit_log(self, level: str, logger_name: str, message: str):
        """Emit log message signal."""
        self.log_message.emit(level, logger_name, message)


class WargameLogger:
    """
    Enhanced logging system for the wargame application.
    
    Features:
    - Multiple log levels and categories
    - File rotation to prevent large log files
    - Console output with colors
    - Performance timing
    - Error tracing with stack traces
    - Qt signal emission for UI integration
    """
    
    _instance: Optional['WargameLogger'] = None
    _log_emitter: Optional[LogEmitter] = None
    
    def __new__(cls) -> 'WargameLogger':
        """Singleton pattern implementation."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize logging system."""
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.loggers: Dict[str, logging.Logger] = {}
        self.log_dir = Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # Qt signal emitter
        WargameLogger._log_emitter = LogEmitter()
        
        # Setup default loggers
        self._setup_loggers()
    
    @classmethod
    def get_emitter(cls) -> LogEmitter:
        """Get the Qt signal emitter for log messages."""
        if cls._log_emitter is None:
            cls._log_emitter = LogEmitter()
        return cls._log_emitter
    
    def _setup_loggers(self):
        """Setup all application loggers."""
        # Main categories
        categories = [
            'main',        # Main application
            'ui',          # User interface
            'simulation',  # Simulation engine
            'terrain',     # Terrain processing
            'pathfinding', # Pathfinding algorithms
            'combat',      # Combat calculations
            'los',         # Line of sight
            'performance', # Performance monitoring
            'data',        # Data loading/processing
            'error'        # Error tracking
        ]
        
        for category in categories:
            self._create_logger(category)
    
    def _create_logger(self, name: str) -> logging.Logger:
        """Create a logger with file and console handlers."""
        logger = logging.getLogger(f"wargame.{name}")
        logger.setLevel(logging.DEBUG)
        
        # Prevent duplicate handlers
        if logger.handlers:
            return logger
        
        # File handler with rotation
        log_file = self.log_dir / f"{name}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        console_formatter = ColoredFormatter(
            '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        file_handler.setFormatter(detailed_formatter)
        console_handler.setFormatter(console_formatter)
        
        # Custom handler for Qt signals
        qt_handler = QtLogHandler(WargameLogger.get_emitter())
        qt_handler.setLevel(logging.INFO)
        qt_handler.setFormatter(logging.Formatter('%(levelname)s | %(message)s'))
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.addHandler(qt_handler)
        
        self.loggers[name] = logger
        return logger
    
    def get_logger(self, category: str) -> logging.Logger:
        """Get logger for specific category."""
        if category not in self.loggers:
            self._create_logger(category)
        return self.loggers[category]
    
    def log_exception(self, category: str, exc: Exception, context: str = ""):
        """Log exception with full stack trace."""
        logger = self.get_logger(category)
        
        error_msg = f"Exception in {context}: {str(exc)}"
        logger.error(error_msg)
        
        # Log full traceback
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        for line in tb_lines:
            logger.error(line.rstrip())
        
        # Also log to error category
        error_logger = self.get_logger('error')
        error_logger.error(f"[{category}] {error_msg}")
        for line in tb_lines:
            error_logger.error(line.rstrip())
    
    def timer(self, category: str, operation_name: str) -> PerformanceTimer:
        """Create a performance timer for an operation."""
        logger = self.get_logger(category)
        return PerformanceTimer(operation_name, logger)
    
    def set_level(self, category: str, level: int):
        """Set logging level for specific category."""
        if category in self.loggers:
            self.loggers[category].setLevel(level)
    
    def set_global_level(self, level: int):
        """Set logging level for all loggers."""
        for logger in self.loggers.values():
            logger.setLevel(level)


class QtLogHandler(logging.Handler):
    """Custom log handler that emits Qt signals."""
    
    def __init__(self, emitter: LogEmitter):
        super().__init__()
        self.emitter = emitter
    
    def emit(self, record):
        """Emit log record as Qt signal."""
        try:
            message = self.format(record)
            self.emitter.emit_log(record.levelname, record.name, message)
        except Exception:
            # Avoid infinite recursion if logging fails
            pass


def log_errors(category: str = 'error'):
    """Decorator to automatically log exceptions in functions."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger = WargameLogger().get_logger(category)
                logger.error(f"Error in {func.__name__}: {str(e)}")
                logger.error(f"Args: {args}, Kwargs: {kwargs}")
                
                # Log full traceback
                tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
                for line in tb_lines:
                    logger.error(line.rstrip())
                
                raise  # Re-raise the exception
        return wrapper
    return decorator


def log_performance(category: str = 'performance', threshold: float = 0.1):
    """Decorator to log function performance if it exceeds threshold."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            logger = WargameLogger().get_logger(category)
            start_time = time.perf_counter()
            
            try:
                result = func(*args, **kwargs)
                duration = time.perf_counter() - start_time
                
                if duration > threshold:
                    logger.warning(f"{func.__name__} took {duration:.4f}s (threshold: {threshold}s)")
                else:
                    logger.debug(f"{func.__name__} completed in {duration:.4f}s")
                
                return result
            except Exception as e:
                duration = time.perf_counter() - start_time
                logger.error(f"{func.__name__} failed after {duration:.4f}s: {str(e)}")
                raise
        return wrapper
    return decorator


# Global logger instance
_logger_instance = None

def get_logger(category: str = 'main') -> logging.Logger:
    """Get logger instance for category."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = WargameLogger()
    return _logger_instance.get_logger(category)


def log_exception(exc: Exception, category: str = 'error', context: str = ""):
    """Log exception with full traceback."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = WargameLogger()
    _logger_instance.log_exception(category, exc, context)


def get_performance_timer(category: str, operation_name: str) -> PerformanceTimer:
    """Get performance timer for operation."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = WargameLogger()
    return _logger_instance.timer(category, operation_name)


def setup_logging(debug: bool = False):
    """Setup global logging configuration."""
    global _logger_instance
    _logger_instance = WargameLogger()
    
    if debug:
        _logger_instance.set_global_level(logging.DEBUG)
    else:
        _logger_instance.set_global_level(logging.INFO)
    
    # Log startup
    logger = _logger_instance.get_logger('main')
    logger.info("Logging system initialized")
    logger.info(f"Log directory: {_logger_instance.log_dir.absolute()}")
    logger.info(f"Debug mode: {debug}")


# Example usage for quick testing
if __name__ == "__main__":
    # Initialize logging
    setup_logging(debug=True)
    
    # Test different log levels
    logger = get_logger('test')
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")
    
    # Test exception logging
    try:
        raise ValueError("Test exception")
    except Exception as e:
        log_exception(e, 'test', 'exception testing')
    
    # Test performance timing
    with get_performance_timer('test', 'example operation'):
        time.sleep(0.1)
    
    # Test decorators
    @log_errors('test')
    @log_performance('test', threshold=0.05)
    def test_function():
        time.sleep(0.1)
        return "success"
    
    result = test_function()
    logger.info(f"Function result: {result}")