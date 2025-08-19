"""
Main application class managing global state and lifecycle.

This is the central orchestrator that initializes components, manages
application-wide state, and coordinates the overall application lifecycle.
"""

import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer, QStandardPaths
from PySide6.QtGui import QIcon

from .signals import app_signals
from .exceptions import ScannerExtensionError, ConfigurationError


class ScannerExtensionApp(QApplication):
    """
    Main application class managing global state and lifecycle.

    Handles initialization, component setup, configuration management,
    and application shutdown procedures.
    """

    def __init__(self, argv):
        super().__init__(argv)

        # Core properties
        self.main_window: Optional['MainWindow'] = None
        self.config_manager: Optional['ConfigurationManager'] = None
        self.schema_manager: Optional['SchemaManager'] = None

        # Directory paths
        self._temp_directory: Optional[Path] = None
        self._config_directory: Optional[Path] = None
        self._user_data_directory: Optional[Path] = None

        # Application state
        self._is_initialized = False
        self._shutdown_in_progress = False

        # Component registry
        self._components: Dict[str, Any] = {}

        # Setup basic application properties
        self.setApplicationName("Scanner Extension")
        self.setApplicationVersion("1.0.0")
        self.setOrganizationName("Scanner Extension")
        self.setApplicationDisplayName("NAPS2 Scanner Extension")

        # Initialize logging
        self._setup_logging()

        # Set up exception handling
        sys.excepthook = self._handle_exception

        # Connect application signals
        self.aboutToQuit.connect(self._handle_shutdown)

        logging.info("Scanner Extension application created")

    def initialize_components(self) -> bool:
        """
        Initialize all application components in the correct order.

        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logging.info("Initializing application components...")

            # Create directories
            self._ensure_directories()

            # Initialize configuration first
            self._initialize_configuration()

            # Initialize schema management
            self._initialize_schema_manager()

            # Initialize cache system
            self._initialize_cache_system()

            # Set up signal connections
            self._setup_signal_connections()

            # Create main window
            self._create_main_window()

            self._is_initialized = True
            app_signals.application_ready.emit()

            logging.info("Application components initialized successfully")
            return True

        except Exception as e:
            logging.error(f"Failed to initialize components: {e}")
            self._show_startup_error(str(e))
            return False

    def _ensure_directories(self):
        """Create necessary application directories."""
        directories = [
            self.get_temp_directory(),
            self.get_config_directory(),
            self.get_user_data_directory(),
            self.get_temp_directory() / "thumbnails",
            self.get_temp_directory() / "staging"
        ]

        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                logging.debug(f"Ensured directory exists: {directory}")
            except OSError as e:
                raise ConfigurationError(f"Cannot create directory {directory}: {e}")

    def _initialize_configuration(self):
        """Initialize configuration management."""
        try:
            # Import here to avoid circular imports
            from ..utils.config import ConfigurationManager

            config_file = self.get_config_directory() / "app_config.json"
            self.config_manager = ConfigurationManager(config_file)
            self.config_manager.load_application_config()

            self._components['config_manager'] = self.config_manager
            logging.info("Configuration manager initialized")

        except Exception as e:
            raise ConfigurationError(f"Failed to initialize configuration: {e}")

    def _initialize_schema_manager(self):
        """Initialize schema management system."""
        try:
            # Import here to avoid circular imports
            from ..utils.schema_manager import SchemaManager

            schemas_dir = self.get_config_directory() / "schemas"
            schemas_dir.mkdir(exist_ok=True)

            self.schema_manager = SchemaManager(schemas_dir)
            self._components['schema_manager'] = self.schema_manager

            logging.info("Schema manager initialized")

        except Exception as e:
            raise ConfigurationError(f"Failed to initialize schema manager: {e}")

    def _initialize_cache_system(self):
        """Initialize application cache system."""
        try:
            # Import here to avoid circular imports
            from ..utils.cache_manager import CacheManager

            cache_dir = self.get_temp_directory() / "cache"
            cache_size_mb = self.config_manager.get_setting("cache.max_size_mb", 500)

            cache_manager = CacheManager(cache_dir, cache_size_mb)
            self._components['cache_manager'] = cache_manager

            logging.info("Cache system initialized")

        except Exception as e:
            logging.warning(f"Cache system initialization failed: {e}")
            # Cache failure is not critical - continue without it

    def _setup_signal_connections(self):
        """Set up global signal connections."""
        # Connect error handling
        app_signals.error_occurred.connect(self._handle_error_signal)
        app_signals.warning_occurred.connect(self._handle_warning_signal)

        # Connect application lifecycle
        app_signals.application_startup.emit()

        logging.debug("Application signal connections established")

    def _create_main_window(self):
        """Create and show the main application window."""
        try:
            # Import here to avoid circular imports
            from ..ui.main_window import MainWindow

            self.main_window = MainWindow(self)

            # Restore window state if available
            self._restore_window_state()

            self.main_window.show()
            self._components['main_window'] = self.main_window

            logging.info("Main window created and displayed")

        except Exception as e:
            raise ScannerExtensionError(f"Failed to create main window: {e}")

    def _restore_window_state(self):
        """Restore saved window geometry and state."""
        if not self.config_manager or not self.main_window:
            return

        try:
            geometry = self.config_manager.get_setting("window.geometry")
            state = self.config_manager.get_setting("window.state")

            if geometry:
                self.main_window.restoreGeometry(geometry)
            if state:
                self.main_window.restoreState(state)

        except Exception as e:
            logging.warning(f"Could not restore window state: {e}")

    def _save_window_state(self):
        """Save current window geometry and state."""
        if not self.config_manager or not self.main_window:
            return

        try:
            self.config_manager.set_setting("window.geometry",
                                            self.main_window.saveGeometry())
            self.config_manager.set_setting("window.state",
                                            self.main_window.saveState())
            self.config_manager.save_application_config()

        except Exception as e:
            logging.warning(f"Could not save window state: {e}")

    def _handle_shutdown(self):
        """Handle application shutdown sequence."""
        if self._shutdown_in_progress:
            return

        self._shutdown_in_progress = True
        logging.info("Application shutdown initiated")

        try:
            app_signals.application_shutdown.emit()

            # Save window state
            self._save_window_state()

            # Clean up components
            self._cleanup_components()

            # Final logging
            logging.info("Application shutdown completed")

        except Exception as e:
            logging.error(f"Error during shutdown: {e}")

    def _cleanup_components(self):
        """Clean up all application components."""
        for name, component in self._components.items():
            try:
                if hasattr(component, 'cleanup'):
                    component.cleanup()
                logging.debug(f"Cleaned up component: {name}")
            except Exception as e:
                logging.warning(f"Error cleaning up {name}: {e}")

    def _setup_logging(self):
        """Configure application logging."""
        log_level = logging.INFO
        if '--debug' in sys.argv:
            log_level = logging.DEBUG

        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

        # Create logs directory
        log_dir = self.get_user_data_directory() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Set up file and console logging
        logging.basicConfig(
            level=log_level,
            format=log_format,
            handlers=[
                logging.FileHandler(log_dir / "scanner_extension.log"),
                logging.StreamHandler(sys.stdout)
            ]
        )

    def _handle_exception(self, exc_type, exc_value, exc_traceback):
        """Global exception handler."""
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logging.error("Uncaught exception",
                      exc_info=(exc_type, exc_value, exc_traceback))

        # Show error dialog if GUI is available
        if self.main_window:
            error_msg = f"An unexpected error occurred:\n\n{exc_value}"
            QMessageBox.critical(self.main_window, "Unexpected Error", error_msg)

    def _handle_error_signal(self, title: str, message: str):
        """Handle error signals by showing error dialog."""
        if self.main_window:
            QMessageBox.critical(self.main_window, title, message)

    def _handle_warning_signal(self, title: str, message: str):
        """Handle warning signals by showing warning dialog."""
        if self.main_window:
            QMessageBox.warning(self.main_window, title, message)

    def _show_startup_error(self, message: str):
        """Show startup error dialog."""
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle("Scanner Extension - Startup Error")
        msg_box.setText("The application failed to start properly.")
        msg_box.setDetailedText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()

    # Directory property methods
    def get_temp_directory(self) -> Path:
        """Get application temporary directory."""
        if not self._temp_directory:
            temp_path = QStandardPaths.writableLocation(QStandardPaths.TempLocation)
            self._temp_directory = Path(temp_path) / "scanner_extension"
        return self._temp_directory

    def get_config_directory(self) -> Path:
        """Get application configuration directory."""
        if not self._config_directory:
            config_path = QStandardPaths.writableLocation(QStandardPaths.ConfigLocation)
            self._config_directory = Path(config_path) / "scanner_extension"
        return self._config_directory

    def get_user_data_directory(self) -> Path:
        """Get application user data directory."""
        if not self._user_data_directory:
            data_path = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
            self._user_data_directory = Path(data_path)
        return self._user_data_directory

    # Component access methods
    def get_component(self, name: str) -> Optional[Any]:
        """Get a registered component by name."""
        return self._components.get(name)

    def register_component(self, name: str, component: Any):
        """Register a component for global access."""
        self._components[name] = component
        logging.debug(f"Registered component: {name}")

    # Application state methods
    @property
    def is_initialized(self) -> bool:
        """Check if application is fully initialized."""
        return self._is_initialized

    @property
    def is_shutting_down(self) -> bool:
        """Check if application is shutting down."""
        return self._shutdown_in_progress

