"""
Primary application window and layout manager.

Manages the main UI layout with dockable panels, menus, toolbars,
and coordinates communication between UI components.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QMenuBar, QMenu, QToolBar, QStatusBar, QDockWidget, QLabel,
    QProgressBar, QMessageBox, QFileDialog, QApplication, QDialog
)
from PySide6.QtCore import Qt, Signal, QTimer, QSettings, QByteArray
from PySide6.QtGui import QAction, QIcon, QKeySequence, QCloseEvent

from src.core.application import ScannerExtensionApp
from src.models.batch import DocumentBatch
from src.models.schema import IndexSchema
from src.ui.page_panel import PagePanel
from src.ui.index_panel import IndexPanel
from src.ui.preview_panel import PreviewPanel
from src.ui.dialogs.export import ExportDialog
from src.ui.dialogs.schema import SchemaDialog
from src.ui.dialogs.settings import SettingsDialog
from src.core.signals import app_signals
from src.core.exceptions import ScannerExtensionError


class MainWindow(QMainWindow):
    """Primary application window and layout manager."""

    # Signals
    batch_load_requested = Signal(str)  # directory_path
    schema_changed = Signal(object)     # IndexSchema
    export_requested = Signal(object)  # DocumentBatch
    monitoring_toggled = Signal(bool)   # enabled

    def __init__(self, app: ScannerExtensionApp):
        super().__init__()

        self.app = app
        self.current_batch = None
        self.current_schema = None

        # UI Components
        self.page_panel = None
        self.index_panel = None
        self.preview_panel = None
        self.dock_widgets = {}

        # Status bar components
        self.status_label = None
        self.progress_bar = None
        self.monitoring_label = None

        # Settings
        self.settings = QSettings("ScannerExtension", "MainWindow")

        self._setup_ui()
        self._setup_menu_bar()
        self._setup_toolbar()
        self._setup_dock_widgets()
        self._setup_status_bar()
        self._connect_signals()
        self._restore_window_state()

    def _setup_ui(self):
        """Initialize the main UI layout."""
        self.setWindowTitle("Scanner Extension")
        self.resize(1200, 800)
        self.setMinimumSize(800, 600)

        # Set window icon if available
        # self.setWindowIcon(QIcon(":/icons/app_icon.png"))

        # Central widget with splitter layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # Create main splitter
        self.main_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.main_splitter)

        # Left panel will be populated by dock widgets
        # Main content area will be the page panel
        # Right panel will also be dock widgets

    def _setup_menu_bar(self):
        """Create the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        # New batch action
        new_batch_action = QAction("&New Batch", self)
        new_batch_action.setShortcut(QKeySequence.New)
        new_batch_action.setStatusTip("Create a new document batch")
        new_batch_action.triggered.connect(self._new_batch)
        file_menu.addAction(new_batch_action)

        # Load batch action
        load_batch_action = QAction("&Load Batch Directory", self)
        load_batch_action.setShortcut(QKeySequence.Open)
        load_batch_action.setStatusTip("Load documents from directory")
        load_batch_action.triggered.connect(self._load_batch_directory)
        file_menu.addAction(load_batch_action)

        file_menu.addSeparator()

        # Export action
        self.export_action = QAction("&Export Documents", self)
        self.export_action.setShortcut(QKeySequence("Ctrl+E"))
        self.export_action.setStatusTip("Export documents to organized structure")
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self._show_export_dialog)
        file_menu.addAction(self.export_action)

        file_menu.addSeparator()

        # Recent files submenu
        self.recent_menu = file_menu.addMenu("&Recent Directories")
        self._update_recent_menu()

        file_menu.addSeparator()

        # Exit action
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.setStatusTip("Exit application")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Schema menu
        schema_menu = menubar.addMenu("&Schema")

        # New schema action
        new_schema_action = QAction("&New Schema", self)
        new_schema_action.setStatusTip("Create a new indexing schema")
        new_schema_action.triggered.connect(self._new_schema)
        schema_menu.addAction(new_schema_action)

        # Edit schema action
        self.edit_schema_action = QAction("&Edit Current Schema", self)
        self.edit_schema_action.setStatusTip("Edit the current indexing schema")
        self.edit_schema_action.setEnabled(False)
        self.edit_schema_action.triggered.connect(self._edit_current_schema)
        schema_menu.addAction(self.edit_schema_action)

        schema_menu.addSeparator()

        # Load schema submenu
        self.schema_submenu = schema_menu.addMenu("&Load Schema")
        self._update_schema_menu()

        # View menu
        view_menu = menubar.addMenu("&View")

        # Dock widget toggles (will be populated after dock widgets are created)
        self.dock_menu = view_menu.addMenu("&Panels")

        view_menu.addSeparator()

        # Zoom actions
        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.setStatusTip("Increase thumbnail size")
        zoom_in_action.triggered.connect(self._zoom_in)
        view_menu.addAction(zoom_in_action)

        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.setStatusTip("Decrease thumbnail size")
        zoom_out_action.triggered.connect(self._zoom_out)
        view_menu.addAction(zoom_out_action)

        reset_zoom_action = QAction("&Reset Zoom", self)
        reset_zoom_action.setShortcut(QKeySequence("Ctrl+0"))
        reset_zoom_action.setStatusTip("Reset thumbnail size to default")
        reset_zoom_action.triggered.connect(self._reset_zoom)
        view_menu.addAction(reset_zoom_action)

        # Processing menu
        processing_menu = menubar.addMenu("&Processing")

        # Start monitoring action
        self.monitoring_action = QAction("Start &Monitoring", self)
        self.monitoring_action.setCheckable(True)
        self.monitoring_action.setStatusTip("Start/stop monitoring for new scanned files")
        self.monitoring_action.triggered.connect(self._toggle_monitoring)
        processing_menu.addAction(self.monitoring_action)

        processing_menu.addSeparator()

        # Clear assignments action
        self.clear_assignments_action = QAction("&Clear All Assignments", self)
        self.clear_assignments_action.setStatusTip("Clear all page assignments")
        self.clear_assignments_action.setEnabled(False)
        self.clear_assignments_action.triggered.connect(self._clear_assignments)
        processing_menu.addAction(self.clear_assignments_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        # Settings action
        settings_action = QAction("&Settings", self)
        settings_action.setStatusTip("Open application settings")
        settings_action.triggered.connect(self._show_settings_dialog)
        tools_menu.addAction(settings_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        # About action
        about_action = QAction("&About", self)
        about_action.setStatusTip("Show application information")
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        """Create the main toolbar."""
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("MainToolbar")  # For state saving
        toolbar.setMovable(True)

        # New batch button
        new_batch_btn = toolbar.addAction("New Batch")
        new_batch_btn.setStatusTip("Create a new document batch")
        new_batch_btn.triggered.connect(self._new_batch)

        # Load directory button
        load_dir_btn = toolbar.addAction("Load Directory")
        load_dir_btn.setStatusTip("Load documents from directory")
        load_dir_btn.triggered.connect(self._load_batch_directory)

        toolbar.addSeparator()

        # Export button
        self.toolbar_export_btn = toolbar.addAction("Export")
        self.toolbar_export_btn.setStatusTip("Export documents")
        self.toolbar_export_btn.setEnabled(False)
        self.toolbar_export_btn.triggered.connect(self._show_export_dialog)

        toolbar.addSeparator()

        # Monitoring toggle button
        self.toolbar_monitor_btn = toolbar.addAction("Start Monitoring")
        self.toolbar_monitor_btn.setCheckable(True)
        self.toolbar_monitor_btn.setStatusTip("Toggle file monitoring")
        self.toolbar_monitor_btn.triggered.connect(self._toggle_monitoring)

        toolbar.addSeparator()

        # Zoom controls
        toolbar.addAction("Zoom In").triggered.connect(self._zoom_in)
        toolbar.addAction("Zoom Out").triggered.connect(self._zoom_out)
        toolbar.addAction("Reset Zoom").triggered.connect(self._reset_zoom)

    def _setup_dock_widgets(self):
        """Create dockable panels."""
        # Page Panel (central - not docked)
        self.page_panel = PagePanel(self)
        self.main_splitter.addWidget(self.page_panel)

        # Index Panel (right dock)
        self.index_panel = IndexPanel(self)
        index_dock = QDockWidget("Index Panel", self)
        index_dock.setObjectName("IndexDock")  # For state saving
        index_dock.setWidget(self.index_panel)
        index_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.RightDockWidgetArea, index_dock)
        self.dock_widgets["index"] = index_dock

        # Preview Panel (bottom dock)
        self.preview_panel = PreviewPanel(self)
        preview_dock = QDockWidget("Preview Panel", self)
        preview_dock.setObjectName("PreviewDock")
        preview_dock.setWidget(self.preview_panel)
        preview_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.addDockWidget(Qt.BottomDockWidgetArea, preview_dock)
        self.dock_widgets["preview"] = preview_dock

        # Add dock toggle actions to view menu
        for name, dock in self.dock_widgets.items():
            action = dock.toggleViewAction()
            self.dock_menu.addAction(action)

        # Set initial splitter sizes (give most space to page panel)
        self.main_splitter.setSizes([800, 400])

    def _setup_status_bar(self):
        """Initialize the status bar."""
        status_bar = self.statusBar()

        # Main status label
        self.status_label = QLabel("Ready")
        status_bar.addWidget(self.status_label)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        status_bar.addPermanentWidget(self.progress_bar)

        # Monitoring status
        self.monitoring_label = QLabel("Monitoring: Off")
        status_bar.addPermanentWidget(self.monitoring_label)

        # Batch info
        self.batch_info_label = QLabel("No batch loaded")
        status_bar.addPermanentWidget(self.batch_info_label)

    def _connect_signals(self):
        """Connect signals between components."""
        # Application signals
        app_signals.batch_loaded.connect(self._on_batch_loaded)
        app_signals.schema_changed.connect(self._on_schema_changed)
        app_signals.pages_selected.connect(self._on_pages_selected)
        app_signals.assignment_created.connect(self._on_assignment_created)
        app_signals.assignment_updated.connect(self._on_assignment_updated)
        app_signals.export_progress.connect(self._on_export_progress)
        app_signals.export_completed.connect(self._on_export_completed)
        app_signals.export_error.connect(self._on_export_error)
        app_signals.validation_error.connect(self._on_validation_error)
        app_signals.progress_update.connect(self._on_progress_update)

        # Panel connections
        if self.page_panel:
            self.page_panel.pages_selected.connect(self._on_pages_selected)

        if self.index_panel:
            self.index_panel.schema_changed.connect(self._on_schema_changed)
            self.index_panel.assignment_applied.connect(self._on_assignment_applied)

        if self.preview_panel:
            self.preview_panel.export_requested.connect(self._show_export_dialog)

    def _restore_window_state(self):
        """Restore window geometry and state."""
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)

        # Restore splitter state
        splitter_state = self.settings.value("splitterState")
        if splitter_state:
            self.main_splitter.restoreState(splitter_state)

    def _save_window_state(self):
        """Save window geometry and state."""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("splitterState", self.main_splitter.saveState())

    # Menu Actions
    def _new_batch(self):
        """Create a new document batch."""
        if self.current_batch and self.current_batch.assignment_count > 0:
            reply = QMessageBox.question(
                self, "New Batch",
                "Current batch has assignments. Are you sure you want to create a new batch?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        try:
            # Signal to create new batch
            self.batch_load_requested.emit("")
            self._update_status("New batch created")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create new batch: {e}")

    def _load_batch_directory(self):
        """Load documents from selected directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Directory with Scanned Documents",
            str(Path.home())
        )

        if directory:
            try:
                self.batch_load_requested.emit(directory)
                self._add_recent_directory(directory)
                self._update_status(f"Loading batch from {directory}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load batch: {e}")

    def _show_export_dialog(self):
        """Show the export configuration dialog."""
        if not self.current_batch or self.current_batch.assignment_count == 0:
            QMessageBox.information(
                self, "No Assignments",
                "Please create some page assignments before exporting."
            )
            return

        try:
            dialog = ExportDialog(self.current_batch, self)
            dialog.export_started.connect(self._on_export_started)
            dialog.export_cancelled.connect(self._on_export_cancelled)

            result = dialog.exec()
            if result == QDialog.Accepted:
                settings = dialog.get_export_settings()
                self.export_requested.emit(self.current_batch)

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to show export dialog: {e}")

    def _new_schema(self):
        """Create a new indexing schema."""
        try:
            dialog = SchemaDialog(None, self)
            dialog.schema_created.connect(self._on_schema_created)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Schema Error", f"Failed to create schema dialog: {e}")

    def _edit_current_schema(self):
        """Edit the current indexing schema."""
        if not self.current_schema:
            return

        try:
            dialog = SchemaDialog(self.current_schema, self)
            dialog.schema_updated.connect(self._on_schema_updated)
            dialog.schema_deleted.connect(self._on_schema_deleted)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Schema Error", f"Failed to edit schema: {e}")

    def _show_settings_dialog(self):
        """Show application settings dialog."""
        try:
            dialog = SettingsDialog(self.app.config_manager, self)
            dialog.settings_applied.connect(self._on_settings_applied)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Settings Error", f"Failed to show settings: {e}")

    def _show_about_dialog(self):
        """Show about dialog."""
        QMessageBox.about(
            self, "About Scanner Extension",
            "<h2>Scanner Extension v1.0</h2>"
            "<p>Document processing and indexing tool for NAPS2 scanned documents.</p>"
            "<p>Organize your scanned documents with custom schemas and automated processing.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Custom indexing schemas</li>"
            "<li>Batch document processing</li>"
            "<li>Automated folder organization</li>"
            "<li>Real-time monitoring</li>"
            "</ul>"
        )

    def _toggle_monitoring(self):
        """Toggle file monitoring on/off."""
        enabled = self.monitoring_action.isChecked()
        self.monitoring_toggled.emit(enabled)

        status = "On" if enabled else "Off"
        self.monitoring_label.setText(f"Monitoring: {status}")

        # Update toolbar button text
        text = "Stop Monitoring" if enabled else "Start Monitoring"
        self.toolbar_monitor_btn.setText(text)

    def _clear_assignments(self):
        """Clear all page assignments."""
        if not self.current_batch:
            return

        reply = QMessageBox.question(
            self, "Clear Assignments",
            "Are you sure you want to clear all page assignments?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                self.current_batch.clear_assignments()
                self._update_ui_for_batch(self.current_batch)
                self._update_status("All assignments cleared")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear assignments: {e}")

    # Zoom Actions
    def _zoom_in(self):
        """Increase thumbnail size."""
        if self.page_panel:
            self.page_panel.zoom_in()

    def _zoom_out(self):
        """Decrease thumbnail size."""
        if self.page_panel:
            self.page_panel.zoom_out()

    def _reset_zoom(self):
        """Reset thumbnail size to default."""
        if self.page_panel:
            self.page_panel.reset_zoom()

    # Signal Handlers
    def _on_batch_loaded(self, batch: DocumentBatch):
        """Handle batch loaded signal."""
        self.current_batch = batch
        self._update_ui_for_batch(batch)

        page_count = batch.total_pages if batch else 0
        file_count = len(batch.scanned_files) if batch else 0

        self.batch_info_label.setText(f"Batch: {file_count} files, {page_count} pages")
        self._update_status(f"Loaded batch with {file_count} files ({page_count} pages)")

    def _on_schema_changed(self, schema: IndexSchema):
        """Handle schema change signal."""
        self.current_schema = schema
        self.edit_schema_action.setEnabled(schema is not None)

        schema_name = schema.name if schema else "None"
        self._update_status(f"Schema changed to: {schema_name}")

    def _on_pages_selected(self, selected_pages: List):
        """Handle page selection changes."""
        count = len(selected_pages)
        if count == 0:
            self._update_status("No pages selected")
        elif count == 1:
            self._update_status("1 page selected")
        else:
            self._update_status(f"{count} pages selected")

    def _on_assignment_created(self, assignment):
        """Handle new assignment creation."""
        self._update_ui_for_batch(self.current_batch)
        self._update_status("New assignment created")

    def _on_assignment_updated(self, assignment):
        """Handle assignment updates."""
        self._update_ui_for_batch(self.current_batch)
        self._update_status("Assignment updated")

    def _on_assignment_applied(self, assignment):
        """Handle assignment application from index panel."""
        if self.preview_panel:
            self.preview_panel.update_preview(self.current_batch)

    def _on_schema_created(self, schema: IndexSchema):
        """Handle new schema creation."""
        self._update_schema_menu()
        self._update_status(f"Schema '{schema.name}' created")

    def _on_schema_updated(self, schema: IndexSchema):
        """Handle schema updates."""
        if self.current_schema and self.current_schema.name == schema.name:
            self.current_schema = schema
        self._update_schema_menu()
        self._update_status(f"Schema '{schema.name}' updated")

    def _on_schema_deleted(self, schema_name: str):
        """Handle schema deletion."""
        if self.current_schema and self.current_schema.name == schema_name:
            self.current_schema = None
            self.edit_schema_action.setEnabled(False)
        self._update_schema_menu()
        self._update_status(f"Schema '{schema_name}' deleted")

    def _on_settings_applied(self, settings: Dict[str, Any]):
        """Handle settings changes."""
        self._update_status("Settings applied")

    def _on_export_started(self, settings: Dict[str, Any]):
        """Handle export start."""
        self._show_progress("Exporting documents...")

    def _on_export_cancelled(self):
        """Handle export cancellation."""
        self._hide_progress()
        self._update_status("Export cancelled")

    def _on_export_progress(self, progress: int, message: str):
        """Handle export progress updates."""
        self.progress_bar.setValue(progress)
        self._update_status(message)

    def _on_export_completed(self, results: Dict[str, Any]):
        """Handle export completion."""
        self._hide_progress()
        documents = results.get('documents_exported', 0)
        self._update_status(f"Export completed - {documents} documents exported")

    def _on_export_error(self, error_message: str):
        """Handle export errors."""
        self._hide_progress()
        self._update_status("Export failed")
        QMessageBox.critical(self, "Export Error", f"Export failed: {error_message}")

    def _on_validation_error(self, field_name: str, message: str):
        """Handle validation errors."""
        self._update_status(f"Validation error in {field_name}: {message}")

    def _on_progress_update(self, progress: int, message: str):
        """Handle general progress updates."""
        if progress >= 0:
            self._show_progress(message, progress)
        else:
            self._hide_progress()
            self._update_status(message)

    # UI Update Methods
    def _update_ui_for_batch(self, batch: Optional[DocumentBatch]):
        """Update UI elements based on current batch."""
        has_batch = batch is not None
        has_assignments = has_batch and batch.assignment_count > 0

        # Update actions
        self.export_action.setEnabled(has_assignments)
        self.toolbar_export_btn.setEnabled(has_assignments)
        self.clear_assignments_action.setEnabled(has_assignments)

        # Update panels
        if self.page_panel:
            self.page_panel.load_batch(batch)

        if self.index_panel:
            self.index_panel.set_batch(batch)

        if self.preview_panel:
            self.preview_panel.update_preview(batch)

    def _update_recent_menu(self):
        """Update the recent directories menu."""
        self.recent_menu.clear()

        recent_dirs = self.settings.value("recent_directories", [])
        if not isinstance(recent_dirs, list):
            recent_dirs = []

        for directory in recent_dirs[:10]:  # Show last 10
            if Path(directory).exists():
                action = self.recent_menu.addAction(str(directory))
                action.triggered.connect(lambda checked, d=directory: self.batch_load_requested.emit(d))

        if recent_dirs:
            self.recent_menu.addSeparator()
            clear_action = self.recent_menu.addAction("Clear Recent")
            clear_action.triggered.connect(self._clear_recent_directories)
        else:
            self.recent_menu.addAction("(No recent directories)").setEnabled(False)

    def _update_schema_menu(self):
        """Update the schema loading menu."""
        self.schema_submenu.clear()

        try:
            schemas = self.app.schema_manager.list_available_schemas()
            for schema_name in schemas:
                action = self.schema_submenu.addAction(schema_name)
                action.triggered.connect(lambda checked, name=schema_name: self._load_schema(name))

            if not schemas:
                self.schema_submenu.addAction("(No schemas available)").setEnabled(False)
        except Exception as e:
            logging.error(f"Failed to update schema menu: {e}")

    def _add_recent_directory(self, directory: str):
        """Add directory to recent list."""
        recent_dirs = self.settings.value("recent_directories", [])
        if not isinstance(recent_dirs, list):
            recent_dirs = []

        # Remove if already exists
        if directory in recent_dirs:
            recent_dirs.remove(directory)

        # Add to front
        recent_dirs.insert(0, directory)

        # Keep only last 10
        recent_dirs = recent_dirs[:10]

        self.settings.setValue("recent_directories", recent_dirs)
        self._update_recent_menu()

    def _clear_recent_directories(self):
        """Clear recent directories list."""
        self.settings.remove("recent_directories")
        self._update_recent_menu()

    def _load_schema(self, schema_name: str):
        """Load a schema by name."""
        try:
            schema = self.app.schema_manager.load_schema(schema_name)
            self.schema_changed.emit(schema)
        except Exception as e:
            QMessageBox.critical(self, "Schema Error", f"Failed to load schema '{schema_name}': {e}")

    def _update_status(self, message: str):
        """Update status bar message."""
        self.status_label.setText(message)

    def _show_progress(self, message: str, progress: int = 0):
        """Show progress bar with message."""
        self.progress_bar.setValue(progress)
        self.progress_bar.setVisible(True)
        self._update_status(message)

    def _hide_progress(self):
        """Hide progress bar."""
        self.progress_bar.setVisible(False)

    def update_window_title(self, title: str = None):
        """Update window title."""
        base_title = "Scanner Extension"
        if title:
            self.setWindowTitle(f"{base_title} - {title}")
        else:
            self.setWindowTitle(base_title)

    # Event Handlers
    def closeEvent(self, event: QCloseEvent):
        """Handle application close event."""
        # Check for unsaved work
        if self.current_batch and self.current_batch.assignment_count > 0:
            reply = QMessageBox.question(
                self, "Exit Application",
                "You have unsaved assignments. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                event.ignore()
                return

        # Save window state
        self._save_window_state()

        # Signal application shutdown
        if hasattr(self.app, 'handle_shutdown'):
            self.app.handle_shutdown()

        event.accept()

    # Public Interface
    def get_current_batch(self) -> Optional[DocumentBatch]:
        """Get the currently loaded batch."""
        return self.current_batch

    def get_current_schema(self) -> Optional[IndexSchema]:
        """Get the currently selected schema."""
        return self.current_schema

    def show_message(self, title: str, message: str, message_type: str = "information"):
        """Show a message box to the user."""
        if message_type == "warning":
            QMessageBox.warning(self, title, message)
        elif message_type == "critical":
            QMessageBox.critical(self, title, message)
        else:
            QMessageBox.information(self, title, message)

    def set_current_batch(self, batch: DocumentBatch):
        """Set the current batch and update UI."""
        self.current_batch = batch
        self._update_ui_for_batch(batch)

    def set_current_schema(self, schema: IndexSchema):
        """Set the current schema and update UI."""
        self.current_schema = schema
        if self.index_panel:
            self.index_panel.load_schema(schema)