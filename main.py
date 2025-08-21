#!/usr/bin/env python3
"""
Scanner Extension - Main Application Entry Point

This module serves as the application entry point, handling initialization,
dependency checking, logging setup, and global exception handling.
"""

import sys
import os
import logging
import traceback
from pathlib import Path
from typing import List, Optional

# Add the src directory to the Python path
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Import after path setup
try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QFont, QIcon
except ImportError as e:
    print(f"Error: PySide6 not found. Please install it with: pip install PySide6")
    print(f"Import error: {e}")
    sys.exit(1)

from src.core.application import ScannerExtensionApp
from src.core.exceptions import ScannerExtensionError, ConfigurationError


def check_dependencies() -> List[str]:
    """
    Check if all required dependencies are available.

    Returns:
        List[str]: List of missing dependencies (empty if all present)
    """
    missing_deps = []

    # Required packages with their import names
    required_packages = [
        ("PySide6", "PySide6.QtWidgets"),
        ("PyPDF2 or pypdf", "PyPDF2"),  # We'll check for either
        ("Pillow", "PIL"),
        ("pathlib", "pathlib"),  # Should be built-in for Python 3.4+
    ]

    for package_name, import_name in required_packages:
        try:
            if import_name == "PyPDF2":
                # Try PyPDF2 first, then pypdf
                try:
                    import PyPDF2
                except ImportError:
                    import pypdf
            else:
                __import__(import_name)
        except ImportError:
            missing_deps.append(package_name)

    return missing_deps


def setup_logging() -> None:
    """Configure application logging system."""
    # Create logs directory
    log_dir = Path.home() / ".scanner_extension" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Determine log level
    log_level = logging.INFO
    if "--debug" in sys.argv:
        log_level = logging.DEBUG
    elif "--quiet" in sys.argv:
        log_level = logging.WARNING

    # Configure logging format
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # Create file handler
    log_file = log_dir / "scanner_extension.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))

    # Create console handler (only if not quiet mode)
    handlers = [file_handler]
    if "--quiet" not in sys.argv:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        handlers.append(console_handler)

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True  # Override any existing configuration
    )

    # Log startup information
    logging.info("=" * 60)
    logging.info("Scanner Extension Starting Up")
    logging.info("=" * 60)
    logging.info(f"Python version: {sys.version}")
    logging.info(f"Application directory: {Path(__file__).parent}")
    logging.info(f"Log level: {logging.getLevelName(log_level)}")


def handle_exceptions(exc_type, exc_value, exc_traceback) -> None:
    """
    Global exception handler for unhandled exceptions.

    Args:
        exc_type: Exception type
        exc_value: Exception value
        exc_traceback: Exception traceback
    """
    # Don't handle KeyboardInterrupt
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Log the exception
    logging.critical(
        "Uncaught exception occurred",
        exc_info=(exc_type, exc_value, exc_traceback)
    )

    # Format error message
    error_msg = f"An unexpected error occurred:\n\n{exc_value}"

    # Try to show GUI error dialog if possible
    try:
        # Check if QApplication exists
        app = QApplication.instance()
        if app is not None:
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("Scanner Extension - Critical Error")
            msg_box.setText("A critical error has occurred and the application must close.")
            msg_box.setDetailedText(
                f"Exception Type: {exc_type.__name__}\n"
                f"Message: {exc_value}\n\n"
                f"Traceback:\n{''.join(traceback.format_tb(exc_traceback))}"
            )
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.exec()
    except Exception:
        # If GUI fails, just print to console
        print(f"\nCRITICAL ERROR: {error_msg}", file=sys.stderr)
        print(f"See log file for details.", file=sys.stderr)

    # Exit with error code
    sys.exit(1)


def show_startup_error(title: str, message: str, details: Optional[str] = None) -> None:
    """
    Show startup error dialog.

    Args:
        title: Error dialog title
        message: Main error message
        details: Optional detailed error information
    """
    try:
        # Create minimal QApplication for error dialog
        if not QApplication.instance():
            app = QApplication([])
            app.setQuitOnLastWindowClosed(True)

        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(f"Scanner Extension - {title}")
        msg_box.setText(message)

        if details:
            msg_box.setDetailedText(details)

        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()

    except Exception as e:
        # Fallback to console output
        print(f"\nERROR: {title}", file=sys.stderr)
        print(f"{message}", file=sys.stderr)
        if details:
            print(f"\nDetails:\n{details}", file=sys.stderr)


def parse_command_line_args() -> dict:
    """
    Parse command line arguments.

    Returns:
        dict: Parsed arguments
    """
    args = {
        'debug': '--debug' in sys.argv,
        'quiet': '--quiet' in sys.argv,
        'help': '--help' in sys.argv or '-h' in sys.argv,
        'version': '--version' in sys.argv or '-v' in sys.argv,
        'config_dir': None,
        'no_monitoring': '--no-monitoring' in sys.argv,
        'batch_dir': None
    }

    # Extract config directory if specified
    for i, arg in enumerate(sys.argv):
        if arg == '--config-dir' and i + 1 < len(sys.argv):
            args['config_dir'] = sys.argv[i + 1]
        elif arg.startswith('--config-dir='):
            args['config_dir'] = arg.split('=', 1)[1]
        elif not arg.startswith('--') and i > 0 and not sys.argv[i - 1].startswith('--'):
            # Assume it's a batch directory
            args['batch_dir'] = arg

    return args


def show_help() -> None:
    """Display help information."""
    help_text = """
Scanner Extension - Document Processing Tool

USAGE:
    python main.py [OPTIONS] [BATCH_DIRECTORY]

OPTIONS:
    --debug             Enable debug logging
    --quiet             Suppress console output (log to file only)
    --config-dir DIR    Use custom configuration directory
    --no-monitoring     Disable automatic file monitoring
    --version, -v       Show version information
    --help, -h          Show this help message

ARGUMENTS:
    BATCH_DIRECTORY     Directory to load as initial batch (optional)

EXAMPLES:
    python main.py
    python main.py --debug
    python main.py /path/to/scanned/documents
    python main.py --config-dir /custom/config /path/to/documents

LOG FILES:
    Logs are stored in: ~/.scanner_extension/logs/scanner_extension.log

For more information, see the documentation in the docs/ directory.
"""
    print(help_text)


def show_version() -> None:
    """Display version information."""
    version_text = """
Scanner Extension v1.0.0

A document processing and indexing tool for NAPS2 scanned documents.

Features:
- Custom indexing schemas
- Batch document processing  
- Automated folder organization
- Real-time file monitoring
- PDF manipulation and merging

Built with PySide6 and Python 3.8+

Copyright (c) 2024 Scanner Extension Project
"""
    print(version_text)


def setup_application_style(app: QApplication) -> None:
    """
    Configure application-wide styling and appearance.

    Args:
        app: QApplication instance
    """
    try:
        # Set application properties
        app.setApplicationDisplayName("Scanner Extension")
        app.setApplicationName("ScannerExtension")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("ScannerExtension")
        app.setOrganizationDomain("scannerextension.local")

        # Set default font
        font = QFont("Segoe UI", 9)  # Windows default
        if sys.platform == "darwin":  # macOS
            font = QFont("SF Pro Text", 13)
        elif sys.platform.startswith("linux"):  # Linux
            font = QFont("Ubuntu", 10)

        app.setFont(font)

        # Enable high DPI support
        app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        # Set window icon if available
        icon_path = Path(__file__).parent / "resources" / "icons" / "app_icon.png"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))

        # Apply custom stylesheet if available
        style_path = Path(__file__).parent / "resources" / "styles" / "main.qss"
        if style_path.exists():
            try:
                with open(style_path, 'r', encoding='utf-8') as f:
                    app.setStyleSheet(f.read())
                logging.info("Custom stylesheet applied")
            except Exception as e:
                logging.warning(f"Failed to apply custom stylesheet: {e}")

        logging.info("Application styling configured")

    except Exception as e:
        logging.warning(f"Failed to configure application styling: {e}")


def main() -> int:
    """
    Main application entry point.

    Returns:
        int: Exit code (0 for success, non-zero for error)
    """
    try:
        # Parse command line arguments
        args = parse_command_line_args()

        # Handle help and version requests
        if args['help']:
            show_help()
            return 0

        if args['version']:
            show_version()
            return 0

        # Setup logging early
        setup_logging()

        # Install global exception handler
        sys.excepthook = handle_exceptions

        logging.info("Starting Scanner Extension application")

        # Check for required dependencies
        missing_deps = check_dependencies()
        if missing_deps:
            error_msg = "Missing required dependencies"
            details = (
                f"The following packages are required but not found:\n\n"
                f"{chr(10).join('• ' + dep for dep in missing_deps)}\n\n"
                f"Please install them using pip:\n"
                f"pip install {' '.join(missing_deps)}"
            )

            logging.critical(f"Missing dependencies: {missing_deps}")
            show_startup_error("Dependency Error", error_msg, details)
            return 1

        logging.info("All dependencies found")

        # Create QApplication with proper arguments
        # Filter out our custom arguments that Qt doesn't understand
        qt_args = [arg for arg in sys.argv if not arg.startswith('--') or
                   arg in ['--help', '--version']]

        app = ScannerExtensionApp(qt_args)

        # Configure application styling
        setup_application_style(app)

        # Set custom config directory if specified
        if args['config_dir']:
            config_path = Path(args['config_dir'])
            if not config_path.exists():
                try:
                    config_path.mkdir(parents=True)
                    logging.info(f"Created custom config directory: {config_path}")
                except OSError as e:
                    logging.error(f"Failed to create config directory: {e}")
                    show_startup_error(
                        "Configuration Error",
                        f"Cannot create config directory: {config_path}",
                        str(e)
                    )
                    return 1

        # Initialize application components
        logging.info("Initializing application components...")

        if not app.initialize_components():
            logging.critical("Application initialization failed")
            show_startup_error(
                "Initialization Error",
                "Failed to initialize application components. Check the log file for details."
            )
            return 1

        logging.info("Application initialization completed successfully")

        # Load initial batch if specified
        if args['batch_dir']:
            batch_path = Path(args['batch_dir'])
            if batch_path.exists() and batch_path.is_dir():
                logging.info(f"Loading initial batch from: {batch_path}")
                # Signal to load the batch (this will be handled by the main window)
                QTimer.singleShot(500, lambda: app.main_window.batch_load_requested.emit(str(batch_path)))
            else:
                logging.warning(f"Batch directory not found or invalid: {batch_path}")

        # Disable monitoring if requested
        if args['no_monitoring']:
            logging.info("File monitoring disabled by command line option")

        logging.info("Starting Qt event loop...")

        # Start the Qt event loop
        exit_code = app.exec()

        logging.info(f"Application exiting with code: {exit_code}")
        return exit_code

    except KeyboardInterrupt:
        logging.info("Application interrupted by user (Ctrl+C)")
        return 0

    except ConfigurationError as e:
        logging.error(f"Configuration error: {e}")
        show_startup_error("Configuration Error", str(e))
        return 1

    except ScannerExtensionError as e:
        logging.error(f"Application error: {e}")
        show_startup_error("Application Error", str(e))
        return 1

    except Exception as e:
        logging.critical(f"Unexpected error during startup: {e}", exc_info=True)
        show_startup_error(
            "Startup Error",
            "An unexpected error occurred during application startup.",
            str(e)
        )
        return 1


if __name__ == "__main__":
    # Ensure proper cleanup on exit
    import atexit


    def cleanup():
        """Cleanup function called on exit."""
        logging.info("Application cleanup completed")


    atexit.register(cleanup)

    # Run the application
    exit_code = main()
    sys.exit(exit_code)