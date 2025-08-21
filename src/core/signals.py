"""
Centralized signal definitions for inter-component communication.

This module provides a single source of truth for all application signals,
enabling loose coupling between UI components and business logic.
"""

from PySide6.QtCore import QObject, Signal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.batch import DocumentBatch
    from ..models.schema import IndexSchema
    from ..models.assignment import PageAssignment
    from pathlib import Path


class ApplicationSignals(QObject):
    """Central hub for all application signals."""

    # Batch management signals
    batch_loaded = Signal(object)  # DocumentBatch
    batch_cleared = Signal()
    batch_updated = Signal(object)  # DocumentBatch

    # Schema management signals
    schema_changed = Signal(object)  # IndexSchema
    schema_loaded = Signal(object)  # IndexSchema
    schema_saved = Signal(str)  # schema_name
    schema_deleted = Signal(str)  # schema_name
    schema_list_updated = Signal()  # Schema list has been refreshed

    # Page selection signals
    pages_selected = Signal(list)  # List[PageReference]
    page_selection_cleared = Signal()
    page_selection_changed = Signal(list)  # List[PageReference]

    # Assignment signals
    assignment_created = Signal(object)  # PageAssignment
    assignment_updated = Signal(object)  # PageAssignment
    assignment_deleted = Signal(str)  # assignment_id
    assignment_conflict_detected = Signal(str, list)  # error_msg, conflicting_assignments

    # File monitoring signals
    file_detected = Signal(object)  # Path
    scan_batch_ready = Signal(list)  # List[Path]
    file_monitoring_started = Signal(object)  # Path
    file_monitoring_stopped = Signal()

    # Processing signals
    processing_started = Signal(object)  # DocumentBatch
    processing_progress = Signal(int, str)  # progress_percent, status_message
    processing_completed = Signal(dict)  # results
    processing_error = Signal(str)  # error_message
    processing_cancelled = Signal()
    progress_update = Signal(int, str)  # progress_percent, message

    # Export signals
    export_requested = Signal(object, object)  # DocumentBatch, output_path
    export_started = Signal(object)  # export_settings
    export_progress = Signal(int, str)  # progress_percent, current_file
    export_completed = Signal(dict)  # export_results
    export_error = Signal(str)  # error_message

    # Validation signals
    validation_error = Signal(str, str)  # field_name, error_message
    validation_warning = Signal(str, str)  # field_name, warning_message
    validation_cleared = Signal(str)  # field_name
    batch_validation_completed = Signal(bool, list)  # is_valid, error_list

    # UI state signals
    ui_state_changed = Signal(str, object)  # state_key, state_value
    window_state_changed = Signal(dict)  # window_state_dict
    panel_visibility_changed = Signal(str, bool)  # panel_name, is_visible

    # Thumbnail signals
    thumbnail_generated = Signal(str, int, object)  # file_id, page_number, thumbnail_path
    thumbnail_cache_updated = Signal()
    thumbnail_generation_progress = Signal(int, int)  # current, total

    # Configuration signals
    config_changed = Signal(str, object)  # config_key, new_value
    config_loaded = Signal()
    config_saved = Signal()
    config_reset = Signal()

    # Application lifecycle signals
    application_startup = Signal()
    application_shutdown = Signal()
    application_ready = Signal()

    # Status and notification signals
    status_message = Signal(str, int)  # message, timeout_ms
    error_occurred = Signal(str, str)  # title, message
    warning_occurred = Signal(str, str)  # title, message
    info_message = Signal(str, str)  # title, message

    # Cache signals
    cache_cleared = Signal(str)  # cache_type
    cache_size_limit_reached = Signal(str)  # cache_type
    cache_cleanup_completed = Signal(str, int)  # cache_type, items_removed

    # Recent files signals
    recent_file_added = Signal(object)  # Path
    recent_files_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def connect_all_signals(self, receiver_dict):
        """
        Connect multiple signals at once using a dictionary mapping.

        Args:
            receiver_dict: Dict mapping signal names to receiver functions
                          e.g., {'batch_loaded': self.handle_batch_loaded}
        """
        for signal_name, receiver in receiver_dict.items():
            if hasattr(self, signal_name):
                signal = getattr(self, signal_name)
                signal.connect(receiver)
            else:
                print(f"Warning: Signal '{signal_name}' not found")

    def disconnect_all_signals(self):
        """Disconnect all signals - useful for cleanup."""
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if isinstance(attr, Signal):
                attr.disconnect()

    def emit_status(self, message: str, timeout: int = 3000):
        """Convenience method to emit status messages."""
        self.status_message.emit(message, timeout)

    def emit_error(self, title: str, message: str):
        """Convenience method to emit error messages."""
        self.error_occurred.emit(title, message)

    def emit_warning(self, title: str, message: str):
        """Convenience method to emit warning messages."""
        self.warning_occurred.emit(title, message)

    def emit_info(self, title: str, message: str):
        """Convenience method to emit info messages."""
        self.info_message.emit(title, message)


# Global signals instance - imported by other modules
app_signals = ApplicationSignals()