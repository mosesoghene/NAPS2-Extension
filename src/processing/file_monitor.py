"""
File system monitor for detecting new scanned files from NAPS2.

Monitors a designated directory for new PDF files, handles file completion
detection, and batches files for processing.
"""

import logging
import time
from pathlib import Path
from typing import Set, List, Optional, Dict
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QFileSystemWatcher, QTimer, pyqtSignal
from PySide6.QtCore import QThread, QMutex, QMutexLocker

from ..core.exceptions import FileProcessingError
from ..core.signals import app_signals


class FileMonitor(QObject):
    """Monitors NAPS2 staging directory for new scanned files."""

    # Signals
    file_detected = pyqtSignal(object)  # Path
    batch_ready = pyqtSignal(list)  # List[Path]
    monitoring_started = pyqtSignal(object)  # Path
    monitoring_stopped = pyqtSignal()
    file_size_stabilized = pyqtSignal(object)  # Path
    monitoring_error = pyqtSignal(str)  # error_message

    def __init__(self, parent=None):
        """
        Initialize file monitor.

        Args:
            parent: Parent QObject
        """
        super().__init__(parent)

        # Core properties
        self.watched_directory: Optional[Path] = None
        self.file_watcher: Optional[QFileSystemWatcher] = None
        self.scan_timeout: int = 30  # seconds
        self.file_detection_delay: float = 2.0  # seconds

        # File tracking
        self.pending_files: Dict[Path, datetime] = {}
        self.completed_files: Set[Path] = set()
        self.file_sizes: Dict[Path, int] = {}

        # Timers
        self.scan_timer: Optional[QTimer] = None
        self.cleanup_timer: Optional[QTimer] = None

        # Thread safety
        self.mutex = QMutex()

        # Configuration
        self.supported_extensions = {'.pdf'}
        self.ignore_hidden_files = True
        self.min_file_size = 1024  # bytes
        self.max_batch_size = 50
        self.batch_timeout = 60  # seconds

        # State tracking
        self.is_monitoring = False
        self.last_batch_time: Optional[datetime] = None

        # Initialize timers
        self._setup_timers()

        logging.debug("FileMonitor initialized")

    def _setup_timers(self):
        """Initialize timer objects."""
        # Timer for checking file completion
        self.scan_timer = QTimer()
        self.scan_timer.timeout.connect(self._check_pending_files)
        self.scan_timer.setSingleShot(False)

        # Timer for periodic cleanup
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self._cleanup_old_entries)
        self.cleanup_timer.setSingleShot(False)

    def start_monitoring(self, directory_path: Path) -> bool:
        """
        Begin monitoring directory for new files.

        Args:
            directory_path: Path to directory to monitor

        Returns:
            bool: True if monitoring started successfully
        """
        try:
            directory_path = Path(directory_path)

            if not directory_path.exists():
                raise FileProcessingError(f"Directory does not exist: {directory_path}")

            if not directory_path.is_dir():
                raise FileProcessingError(f"Path is not a directory: {directory_path}")

            logging.info(f"Starting file monitoring for: {directory_path}")

            # Stop existing monitoring
            if self.is_monitoring:
                self.stop_monitoring()

            with QMutexLocker(self.mutex):
                self.watched_directory = directory_path

                # Set up file system watcher
                self.file_watcher = QFileSystemWatcher()
                self.file_watcher.addPath(str(directory_path))

                # Connect signals
                self.file_watcher.fileChanged.connect(self._handle_file_changed)
                self.file_watcher.directoryChanged.connect(self._handle_directory_changed)

                # Clear tracking data
                self.pending_files.clear()
                self.completed_files.clear()
                self.file_sizes.clear()

                # Start timers
                self.scan_timer.start(int(self.file_detection_delay * 1000))
                self.cleanup_timer.start(60000)  # 1 minute

                self.is_monitoring = True

            # Emit monitoring started signal
            self.monitoring_started.emit(directory_path)
            app_signals.file_monitoring_started.emit(directory_path)

            logging.info(f"File monitoring started for: {directory_path}")
            return True

        except Exception as e:
            error_msg = f"Failed to start monitoring {directory_path}: {e}"
            logging.error(error_msg)
            self.monitoring_error.emit(error_msg)
            return False

    def stop_monitoring(self):
        """Stop monitoring directory."""
        try:
            logging.info("Stopping file monitoring")

            with QMutexLocker(self.mutex):
                if self.file_watcher:
                    self.file_watcher.deleteLater()
                    self.file_watcher = None

                if self.scan_timer and self.scan_timer.isActive():
                    self.scan_timer.stop()

                if self.cleanup_timer and self.cleanup_timer.isActive():
                    self.cleanup_timer.stop()

                self.is_monitoring = False
                self.watched_directory = None

            # Emit final batch if pending files exist
            if self.pending_files:
                self._emit_final_batch()

            # Emit monitoring stopped signal
            self.monitoring_stopped.emit()
            app_signals.file_monitoring_stopped.emit()

            logging.info("File monitoring stopped")

        except Exception as e:
            logging.error(f"Error stopping file monitoring: {e}")

    def _handle_directory_changed(self, directory_path: str):
        """Handle directory change notification."""
        try:
            directory = Path(directory_path)

            if not directory.exists():
                logging.warning(f"Monitored directory no longer exists: {directory}")
                self.stop_monitoring()
                return

            # Check for new files
            self._scan_for_new_files()

        except Exception as e:
            logging.error(f"Error handling directory change: {e}")

    def _handle_file_changed(self, file_path: str):
        """Handle file change notification."""
        try:
            file_path = Path(file_path)

            if self._should_process_file(file_path):
                logging.debug(f"File changed: {file_path.name}")
                self._track_file_size(file_path)

        except Exception as e:
            logging.debug(f"Error handling file change for {file_path}: {e}")

    def _scan_for_new_files(self):
        """Scan directory for new files."""
        if not self.watched_directory or not self.watched_directory.exists():
            return

        try:
            current_files = set()

            # Scan directory
            for file_path in self.watched_directory.iterdir():
                if self._should_process_file(file_path):
                    current_files.add(file_path)

                    # Track new files
                    if file_path not in self.pending_files and file_path not in self.completed_files:
                        self._handle_new_file(file_path)

            # Clean up files that no longer exist
            with QMutexLocker(self.mutex):
                missing_files = set(self.pending_files.keys()) - current_files
                for missing_file in missing_files:
                    del self.pending_files[missing_file]
                    self.file_sizes.pop(missing_file, None)

        except Exception as e:
            logging.error(f"Error scanning for new files: {e}")

    def _handle_new_file(self, file_path: Path):
        """Handle detection of new file."""
        try:
            if not self._should_process_file(file_path):
                return

            with QMutexLocker(self.mutex):
                # Add to pending files
                self.pending_files[file_path] = datetime.now()

                # Track initial file size
                self._track_file_size(file_path)

            logging.info(f"New file detected: {file_path.name}")
            self.file_detected.emit(file_path)
            app_signals.file_detected.emit(file_path)

        except Exception as e:
            logging.error(f"Error handling new file {file_path}: {e}")

    def _check_pending_files(self):
        """Check pending files for completion."""
        try:
            current_time = datetime.now()
            completed_files = []
            timed_out_files = []

            with QMutexLocker(self.mutex):
                files_to_check = list(self.pending_files.items())

            for file_path, detection_time in files_to_check:
                try:
                    # Check if file still exists
                    if not file_path.exists():
                        with QMutexLocker(self.mutex):
                            self.pending_files.pop(file_path, None)
                            self.file_sizes.pop(file_path, None)
                        continue

                    # Check timeout
                    if (current_time - detection_time).total_seconds() > self.scan_timeout:
                        timed_out_files.append(file_path)
                        continue

                    # Check if file is complete
                    if self._is_scan_complete(file_path):
                        completed_files.append(file_path)

                except Exception as e:
                    logging.debug(f"Error checking file {file_path}: {e}")

            # Process completed files
            for file_path in completed_files:
                self._mark_file_complete(file_path)

            # Handle timed out files
            for file_path in timed_out_files:
                logging.warning(f"File scan timeout: {file_path.name}")
                self._mark_file_complete(file_path)  # Process anyway

            # Check if batch should be emitted
            self._check_batch_ready()

        except Exception as e:
            logging.error(f"Error checking pending files: {e}")

    def _is_scan_complete(self, file_path: Path) -> bool:
        """
        Check if file scan is complete.

        Args:
            file_path: Path to file to check

        Returns:
            bool: True if scan appears complete
        """
        try:
            if not file_path.exists():
                return False

            # Check file size stability
            current_size = file_path.stat().st_size

            # Must be larger than minimum size
            if current_size < self.min_file_size:
                return False

            # Check if size has stabilized
            with QMutexLocker(self.mutex):
                previous_size = self.file_sizes.get(file_path, 0)
                self.file_sizes[file_path] = current_size

            # If size hasn't changed and file is not empty, consider it complete
            if current_size > 0 and current_size == previous_size:
                # Additional check: try to read the file
                try:
                    with open(file_path, 'rb') as f:
                        # Try to read first few bytes
                        f.read(1024)
                    return True
                except (IOError, OSError):
                    # File may still be locked by scanner
                    return False

            return False

        except Exception as e:
            logging.debug(f"Error checking scan completion for {file_path}: {e}")
            return False

    def _track_file_size(self, file_path: Path):
        """Track file size for stability detection."""
        try:
            if file_path.exists():
                size = file_path.stat().st_size
                with QMutexLocker(self.mutex):
                    self.file_sizes[file_path] = size
        except Exception as e:
            logging.debug(f"Error tracking file size for {file_path}: {e}")

    def _mark_file_complete(self, file_path: Path):
        """Mark file as complete and ready for processing."""
        try:
            with QMutexLocker(self.mutex):
                if file_path in self.pending_files:
                    del self.pending_files[file_path]

                self.completed_files.add(file_path)

            logging.info(f"File scan complete: {file_path.name}")
            self.file_size_stabilized.emit(file_path)

        except Exception as e:
            logging.error(f"Error marking file complete {file_path}: {e}")

    def _check_batch_ready(self):
        """Check if batch should be emitted."""
        try:
            current_time = datetime.now()

            # Check batch conditions
            should_emit_batch = False

            with QMutexLocker(self.mutex):
                completed_count = len(self.completed_files)

                # Emit if we have maximum batch size
                if completed_count >= self.max_batch_size:
                    should_emit_batch = True

                # Emit if timeout reached and we have files
                elif (completed_count > 0 and
                      self.last_batch_time and
                      (current_time - self.last_batch_time).total_seconds() > self.batch_timeout):
                    should_emit_batch = True

                # Emit if no pending files and we have completed files
                elif completed_count > 0 and len(self.pending_files) == 0:
                    should_emit_batch = True

            if should_emit_batch:
                self._emit_batch()

        except Exception as e:
            logging.error(f"Error checking batch ready: {e}")

    def _emit_batch(self):
        """Emit batch of completed files."""
        try:
            with QMutexLocker(self.mutex):
                if not self.completed_files:
                    return

                # Prepare batch
                batch_files = list(self.completed_files)
                self.completed_files.clear()
                self.last_batch_time = datetime.now()

            logging.info(f"Emitting batch of {len(batch_files)} files")
            self.batch_ready.emit(batch_files)
            app_signals.scan_batch_ready.emit(batch_files)

        except Exception as e:
            logging.error(f"Error emitting batch: {e}")

    def _emit_final_batch(self):
        """Emit final batch on monitoring stop."""
        try:
            with QMutexLocker(self.mutex):
                all_files = list(self.completed_files) + list(self.pending_files.keys())

                if all_files:
                    logging.info(f"Emitting final batch of {len(all_files)} files")
                    self.batch_ready.emit(all_files)
                    app_signals.scan_batch_ready.emit(all_files)

        except Exception as e:
            logging.error(f"Error emitting final batch: {e}")

    def _cleanup_old_entries(self):
        """Clean up old tracking entries."""
        try:
            current_time = datetime.now()
            cleanup_age = timedelta(hours=1)

            with QMutexLocker(self.mutex):
                # Clean up old pending files
                expired_files = [
                    file_path for file_path, detection_time in self.pending_files.items()
                    if current_time - detection_time > cleanup_age
                ]

                for file_path in expired_files:
                    if file_path in self.pending_files:
                        del self.pending_files[file_path]
                    self.file_sizes.pop(file_path, None)

                # Limit completed files tracking
                if len(self.completed_files) > 100:
                    files_to_remove = list(self.completed_files)[:50]
                    for file_path in files_to_remove:
                        self.completed_files.discard(file_path)

            if expired_files:
                logging.debug(f"Cleaned up {len(expired_files)} old file entries")

        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

    def _should_process_file(self, file_path: Path) -> bool:
        """Check if file should be processed."""
        try:
            # Check if path is a file
            if not file_path.is_file():
                return False

            # Check extension
            if file_path.suffix.lower() not in self.supported_extensions:
                return False

            # Check for hidden files
            if self.ignore_hidden_files and file_path.name.startswith('.'):
                return False

            # Check for temporary files
            if file_path.name.startswith('~') or file_path.suffix in {'.tmp', '.temp'}:
                return False

            return True

        except Exception:
            return False

    # Configuration methods
    def set_scan_timeout(self, timeout: int):
        """Set scan completion timeout."""
        self.scan_timeout = max(5, timeout)

    def set_file_detection_delay(self, delay: float):
        """Set file detection delay."""
        self.file_detection_delay = max(0.5, delay)
        if self.scan_timer and self.scan_timer.isActive():
            self.scan_timer.setInterval(int(delay * 1000))

    def set_supported_extensions(self, extensions: List[str]):
        """Set supported file extensions."""
        self.supported_extensions = {ext.lower() for ext in extensions}

    def set_max_batch_size(self, size: int):
        """Set maximum batch size."""
        self.max_batch_size = max(1, size)

    def set_batch_timeout(self, timeout: int):
        """Set batch timeout in seconds."""
        self.batch_timeout = max(10, timeout)

    # Status methods
    def get_pending_files(self) -> List[Path]:
        """Return list of pending files."""
        with QMutexLocker(self.mutex):
            return list(self.pending_files.keys())

    def get_completed_files(self) -> List[Path]:
        """Return list of completed files."""
        with QMutexLocker(self.mutex):
            return list(self.completed_files)

    def clear_pending_files(self):
        """Clear pending files list."""
        with QMutexLocker(self.mutex):
            self.pending_files.clear()
            self.file_sizes.clear()

    def is_monitoring_active(self) -> bool:
        """Check if monitoring is active."""
        return self.is_monitoring

    def get_monitoring_status(self) -> Dict[str, any]:
        """Get detailed monitoring status."""
        with QMutexLocker(self.mutex):
            return {
                'is_monitoring': self.is_monitoring,
                'watched_directory': str(self.watched_directory) if self.watched_directory else None,
                'pending_files_count': len(self.pending_files),
                'completed_files_count': len(self.completed_files),
                'scan_timeout': self.scan_timeout,
                'supported_extensions': list(self.supported_extensions),
                'last_batch_time': self.last_batch_time.isoformat() if self.last_batch_time else None
            }
        