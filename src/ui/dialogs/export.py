"""
Export dialog for configuring document batch export options.

Provides comprehensive interface for setting export parameters including
output directory, naming strategy, quality settings, and conflict resolution.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QGroupBox, QTreeWidget, QTreeWidgetItem, QProgressBar, QTextEdit,
    QFileDialog, QMessageBox, QTabWidget, QWidget, QSplitter,
    QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread, QMutex, QMutexLocker
from PySide6.QtGui import QFont, QIcon, QPalette

from src.models.batch import DocumentBatch
from src.models.enums import ConflictResolution, PDFQuality, NamingStrategy
from src.core.signals import app_signals
from src.core.exceptions import ExportError


class ExportPreviewThread(QThread):
    """Thread for generating export preview data."""

    preview_ready = Signal(dict)
    preview_error = Signal(str)

    def __init__(self, batch, output_directory):
        super().__init__()
        self.batch = batch
        self.output_directory = output_directory

    def run(self):
        try:
            # Generate preview structure
            preview_data = self._generate_preview_data()
            self.preview_ready.emit(preview_data)
        except Exception as e:
            self.preview_error.emit(str(e))

    def _generate_preview_data(self):
        """Generate export preview data."""
        preview = {
            'folders': {},
            'files': [],
            'conflicts': [],
            'statistics': {
                'total_documents': 0,
                'total_pages': 0,
                'estimated_size': 0
            }
        }

        for assignment in self.batch.assignment_manager.assignments.values():
            try:
                doc_preview = assignment.generate_document_preview()

                folder_path = doc_preview.folder_path or "Root"
                if folder_path not in preview['folders']:
                    preview['folders'][folder_path] = []

                file_info = {
                    'filename': f"{doc_preview.filename}.pdf",
                    'pages': doc_preview.page_count,
                    'size': doc_preview.estimated_file_size,
                    'assignment_id': assignment.assignment_id
                }

                preview['folders'][folder_path].append(file_info)
                preview['files'].append({
                    'path': str(doc_preview.get_full_path()),
                    'pages': doc_preview.page_count,
                    'size': doc_preview.estimated_file_size
                })

                preview['statistics']['total_documents'] += 1
                preview['statistics']['total_pages'] += doc_preview.page_count
                preview['statistics']['estimated_size'] += doc_preview.estimated_file_size

            except Exception as e:
                logging.warning(f"Could not preview assignment {assignment.assignment_id}: {e}")

        return preview


class ExportDialog(QDialog):
    """Configure document export options and preview results."""

    # Signals
    export_started = Signal(dict)  # export_settings
    export_cancelled = Signal()

    def __init__(self, batch: DocumentBatch, parent=None):
        super().__init__(parent)

        self.batch = batch
        self.export_settings = {}
        self.preview_data = {}
        self.preview_thread = None

        # UI state
        self.is_previewing = False
        self.is_exporting = False

        self._setup_ui()
        self._connect_signals()
        self._load_default_settings()
        self._start_preview_generation()

    def _setup_ui(self):
        """Set up the export dialog UI."""
        self.setWindowTitle("Export Documents")
        self.setModal(True)
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        # Create tab widget for different configuration sections
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Export settings tab
        settings_tab = self._create_settings_tab()
        self.tab_widget.addTab(settings_tab, "Export Settings")

        # Preview tab
        preview_tab = self._create_preview_tab()
        self.tab_widget.addTab(preview_tab, "Preview")

        # Advanced options tab
        advanced_tab = self._create_advanced_tab()
        self.tab_widget.addTab(advanced_tab, "Advanced")

        # Progress section (initially hidden)
        self.progress_widget = self._create_progress_widget()
        layout.addWidget(self.progress_widget)
        self.progress_widget.hide()

        # Button section
        button_layout = QHBoxLayout()

        self.preview_button = QPushButton("Refresh Preview")
        self.preview_button.clicked.connect(self._start_preview_generation)
        button_layout.addWidget(self.preview_button)

        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.export_button = QPushButton("Start Export")
        self.export_button.setDefault(True)
        self.export_button.clicked.connect(self._start_export)
        button_layout.addWidget(self.export_button)

        layout.addLayout(button_layout)

    def _create_settings_tab(self) -> QWidget:
        """Create the main export settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Output directory section
        output_group = QGroupBox("Output Location")
        output_layout = QFormLayout(output_group)

        # Directory selection
        dir_layout = QHBoxLayout()
        self.output_directory_edit = QLineEdit()
        self.output_directory_edit.setReadOnly(True)
        dir_layout.addWidget(self.output_directory_edit)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._browse_output_directory)
        dir_layout.addWidget(self.browse_button)

        output_layout.addRow("Output Directory:", dir_layout)
        layout.addWidget(output_group)

        # Export options section
        options_group = QGroupBox("Export Options")
        options_layout = QFormLayout(options_group)

        # PDF Quality
        self.quality_combo = QComboBox()
        for quality in PDFQuality:
            self.quality_combo.addItem(quality.get_display_name(), quality)
        options_layout.addRow("PDF Quality:", self.quality_combo)

        # Naming strategy
        self.naming_combo = QComboBox()
        for strategy in NamingStrategy:
            self.naming_combo.addItem(strategy.get_display_name(), strategy)
        options_layout.addRow("Naming Strategy:", self.naming_combo)

        # Conflict resolution
        self.conflict_combo = QComboBox()
        for resolution in ConflictResolution:
            self.conflict_combo.addItem(resolution.get_display_name(), resolution)
        options_layout.addRow("Conflict Resolution:", self.conflict_combo)

        layout.addWidget(options_group)

        # Additional options
        extras_group = QGroupBox("Additional Options")
        extras_layout = QVBoxLayout(extras_group)

        self.create_index_check = QCheckBox("Create document index file")
        extras_layout.addWidget(self.create_index_check)

        self.preserve_timestamps_check = QCheckBox("Preserve original timestamps")
        extras_layout.addWidget(self.preserve_timestamps_check)

        self.create_thumbnails_check = QCheckBox("Generate thumbnail images")
        extras_layout.addWidget(self.create_thumbnails_check)

        self.compress_output_check = QCheckBox("Compress output files")
        extras_layout.addWidget(self.compress_output_check)

        layout.addWidget(extras_group)

        layout.addStretch()
        return widget

    def _create_preview_tab(self) -> QWidget:
        """Create the export preview tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Statistics section
        stats_group = QGroupBox("Export Statistics")
        stats_layout = QGridLayout(stats_group)

        self.documents_label = QLabel("Documents: -")
        stats_layout.addWidget(self.documents_label, 0, 0)

        self.pages_label = QLabel("Total Pages: -")
        stats_layout.addWidget(self.pages_label, 0, 1)

        self.size_label = QLabel("Estimated Size: -")
        stats_layout.addWidget(self.size_label, 1, 0)

        self.folders_label = QLabel("Folders: -")
        stats_layout.addWidget(self.folders_label, 1, 1)

        layout.addWidget(stats_group)

        # Preview tree
        preview_group = QGroupBox("Folder Structure Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_tree = QTreeWidget()
        self.preview_tree.setHeaderLabels(["Name", "Pages", "Size"])
        self.preview_tree.header().setStretchLastSection(False)
        self.preview_tree.header().resizeSection(0, 300)
        preview_layout.addWidget(self.preview_tree)

        layout.addWidget(preview_group)

        # Conflicts section
        conflicts_group = QGroupBox("Potential Issues")
        conflicts_layout = QVBoxLayout(conflicts_group)

        self.conflicts_list = QListWidget()
        self.conflicts_list.setMaximumHeight(100)
        conflicts_layout.addWidget(self.conflicts_list)

        layout.addWidget(conflicts_group)

        return widget

    def _create_advanced_tab(self) -> QWidget:
        """Create the advanced options tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Processing options
        processing_group = QGroupBox("Processing Options")
        processing_layout = QFormLayout(processing_group)

        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, 8)
        self.max_workers_spin.setValue(4)
        processing_layout.addRow("Parallel Workers:", self.max_workers_spin)

        self.memory_limit_spin = QSpinBox()
        self.memory_limit_spin.setRange(100, 2000)
        self.memory_limit_spin.setValue(500)
        self.memory_limit_spin.setSuffix(" MB")
        processing_layout.addRow("Memory Limit:", self.memory_limit_spin)

        layout.addWidget(processing_group)

        # Validation options
        validation_group = QGroupBox("Validation Options")
        validation_layout = QVBoxLayout(validation_group)

        self.strict_validation_check = QCheckBox("Strict validation")
        self.strict_validation_check.setChecked(True)
        validation_layout.addWidget(self.strict_validation_check)

        self.stop_on_error_check = QCheckBox("Stop on first error")
        validation_layout.addWidget(self.stop_on_error_check)

        self.validate_pdfs_check = QCheckBox("Validate output PDFs")
        self.validate_pdfs_check.setChecked(True)
        validation_layout.addWidget(self.validate_pdfs_check)

        layout.addWidget(validation_group)

        # Metadata options
        metadata_group = QGroupBox("Metadata Options")
        metadata_layout = QVBoxLayout(metadata_group)

        self.embed_metadata_check = QCheckBox("Embed index data as PDF metadata")
        self.embed_metadata_check.setChecked(True)
        metadata_layout.addWidget(self.embed_metadata_check)

        self.create_sidecar_check = QCheckBox("Create sidecar files (.xml)")
        metadata_layout.addWidget(self.create_sidecar_check)

        layout.addWidget(metadata_group)

        # Custom script section
        script_group = QGroupBox("Post-Processing Script")
        script_layout = QVBoxLayout(script_group)

        self.enable_script_check = QCheckBox("Run custom script after export")
        script_layout.addWidget(self.enable_script_check)

        script_file_layout = QHBoxLayout()
        self.script_path_edit = QLineEdit()
        self.script_path_edit.setEnabled(False)
        script_file_layout.addWidget(self.script_path_edit)

        self.script_browse_button = QPushButton("Browse...")
        self.script_browse_button.setEnabled(False)
        self.script_browse_button.clicked.connect(self._browse_script_file)
        script_file_layout.addWidget(self.script_browse_button)

        script_layout.addLayout(script_file_layout)

        # Connect enable checkbox
        self.enable_script_check.toggled.connect(self.script_path_edit.setEnabled)
        self.enable_script_check.toggled.connect(self.script_browse_button.setEnabled)

        layout.addWidget(script_group)

        layout.addStretch()
        return widget

    def _create_progress_widget(self) -> QWidget:
        """Create the progress display widget."""
        widget = QGroupBox("Export Progress")
        layout = QVBoxLayout(widget)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("Ready to export...")
        layout.addWidget(self.progress_label)

        self.progress_details = QTextEdit()
        self.progress_details.setMaximumHeight(100)
        self.progress_details.setReadOnly(True)
        layout.addWidget(self.progress_details)

        return widget

    def _connect_signals(self):
        """Connect UI signals to handlers."""
        # Settings change triggers
        self.output_directory_edit.textChanged.connect(self._on_settings_changed)
        self.quality_combo.currentIndexChanged.connect(self._on_settings_changed)
        self.naming_combo.currentIndexChanged.connect(self._on_settings_changed)
        self.conflict_combo.currentIndexChanged.connect(self._on_settings_changed)

        # Preview tree interaction
        self.preview_tree.itemClicked.connect(self._on_preview_item_clicked)

        # Tab change updates preview
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _load_default_settings(self):
        """Load default export settings."""
        # Set default output directory
        default_output = Path.home() / "Documents" / "Scanned Documents"
        self.output_directory_edit.setText(str(default_output))

        # Set default quality
        self.quality_combo.setCurrentIndex(1)  # Medium quality

        # Set default naming strategy
        self.naming_combo.setCurrentIndex(3)  # Schema-based naming

        # Set default conflict resolution
        self.conflict_combo.setCurrentIndex(0)  # Auto-rename

        # Check default options
        self.create_index_check.setChecked(True)
        self.preserve_timestamps_check.setChecked(True)

    def _browse_output_directory(self):
        """Browse for output directory."""
        current_dir = self.output_directory_edit.text()
        if not current_dir:
            current_dir = str(Path.home())

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Export Directory",
            current_dir
        )

        if directory:
            self.output_directory_edit.setText(directory)

    def _browse_script_file(self):
        """Browse for post-processing script."""
        script_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select Post-Processing Script",
            "",
            "Executable Files (*.exe *.bat *.sh *.py);;All Files (*)"
        )

        if script_file:
            self.script_path_edit.setText(script_file)

    def _start_preview_generation(self):
        """Start generating export preview."""
        if self.is_previewing:
            return

        self.is_previewing = True
        self.preview_button.setEnabled(False)
        self.preview_button.setText("Generating Preview...")

        # Clear current preview
        self.preview_tree.clear()
        self.conflicts_list.clear()

        # Start preview thread
        output_dir = Path(self.output_directory_edit.text())
        self.preview_thread = ExportPreviewThread(self.batch, output_dir)
        self.preview_thread.preview_ready.connect(self._on_preview_ready)
        self.preview_thread.preview_error.connect(self._on_preview_error)
        self.preview_thread.start()

    def _on_preview_ready(self, preview_data):
        """Handle preview generation completion."""
        self.preview_data = preview_data
        self._update_preview_display()

        self.is_previewing = False
        self.preview_button.setEnabled(True)
        self.preview_button.setText("Refresh Preview")

    def _on_preview_error(self, error_message):
        """Handle preview generation error."""
        QMessageBox.warning(self, "Preview Error", f"Failed to generate preview:\n{error_message}")

        self.is_previewing = False
        self.preview_button.setEnabled(True)
        self.preview_button.setText("Refresh Preview")

    def _update_preview_display(self):
        """Update preview tab with generated data."""
        if not self.preview_data:
            return

        stats = self.preview_data['statistics']

        # Update statistics
        self.documents_label.setText(f"Documents: {stats['total_documents']}")
        self.pages_label.setText(f"Total Pages: {stats['total_pages']}")
        self.size_label.setText(f"Estimated Size: {self._format_size(stats['estimated_size'])}")
        self.folders_label.setText(f"Folders: {len(self.preview_data['folders'])}")

        # Populate preview tree
        self.preview_tree.clear()

        for folder_path, files in self.preview_data['folders'].items():
            folder_item = QTreeWidgetItem([folder_path, "", ""])
            folder_item.setFont(0, QFont("", -1, QFont.Bold))
            self.preview_tree.addTopLevelItem(folder_item)

            for file_info in files:
                file_item = QTreeWidgetItem([
                    file_info['filename'],
                    str(file_info['pages']),
                    self._format_size(file_info['size'])
                ])
                folder_item.addChild(file_item)

        self.preview_tree.expandAll()

        # Update conflicts list
        self.conflicts_list.clear()
        for conflict in self.preview_data.get('conflicts', []):
            self.conflicts_list.addItem(conflict)

    def _format_size(self, size_bytes):
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _on_settings_changed(self):
        """Handle settings changes."""
        # Enable export button only if output directory is set
        has_output = bool(self.output_directory_edit.text().strip())
        self.export_button.setEnabled(has_output and not self.is_exporting)

    def _on_preview_item_clicked(self, item, column):
        """Handle preview tree item clicks."""
        # Could show additional details in a tooltip or details panel
        pass

    def _on_tab_changed(self, index):
        """Handle tab changes."""
        # Refresh preview when switching to preview tab
        if index == 1 and not self.is_previewing:  # Preview tab
            self._start_preview_generation()

    def _collect_export_settings(self) -> Dict[str, Any]:
        """Collect all export settings into a dictionary."""
        settings = {
            # Basic settings
            'output_directory': Path(self.output_directory_edit.text()),
            'pdf_quality': self.quality_combo.currentData(),
            'naming_strategy': self.naming_combo.currentData(),
            'conflict_resolution': self.conflict_combo.currentData(),

            # Additional options
            'create_index_file': self.create_index_check.isChecked(),
            'preserve_timestamps': self.preserve_timestamps_check.isChecked(),
            'create_thumbnails': self.create_thumbnails_check.isChecked(),
            'compress_output': self.compress_output_check.isChecked(),

            # Advanced options
            'max_workers': self.max_workers_spin.value(),
            'memory_limit_mb': self.memory_limit_spin.value(),
            'strict_validation': self.strict_validation_check.isChecked(),
            'stop_on_error': self.stop_on_error_check.isChecked(),
            'validate_pdfs': self.validate_pdfs_check.isChecked(),

            # Metadata options
            'embed_metadata': self.embed_metadata_check.isChecked(),
            'create_sidecar_files': self.create_sidecar_check.isChecked(),

            # Script options
            'run_post_script': self.enable_script_check.isChecked(),
            'script_path': self.script_path_edit.text(),
        }

        return settings

    def _validate_export_settings(self) -> List[str]:
        """Validate export settings and return any errors."""
        errors = []

        # Check output directory
        output_dir = self.output_directory_edit.text().strip()
        if not output_dir:
            errors.append("Output directory is required")
        else:
            output_path = Path(output_dir)
            if not output_path.parent.exists():
                errors.append("Output directory parent does not exist")

        # Check script file if enabled
        if self.enable_script_check.isChecked():
            script_path = self.script_path_edit.text().strip()
            if not script_path:
                errors.append("Script path is required when post-processing is enabled")
            elif not Path(script_path).exists():
                errors.append("Script file does not exist")

        # Check batch has assignments
        if not self.batch.assignment_manager.assignments:
            errors.append("No assignments to export")

        return errors

    def _start_export(self):
        """Start the export process."""
        # Validate settings
        errors = self._validate_export_settings()
        if errors:
            QMessageBox.warning(self, "Export Settings Invalid",
                                "Please fix the following issues:\n\n" + "\n".join(errors))
            return

        # Collect settings
        self.export_settings = self._collect_export_settings()

        # Show progress
        self.progress_widget.show()
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting export...")

        # Disable UI
        self.is_exporting = True
        self.export_button.setEnabled(False)
        self.cancel_button.setText("Cancel Export")

        # Emit export started signal
        self.export_started.emit(self.export_settings)

        # Connect to progress signals
        app_signals.export_progress.connect(self._on_export_progress)
        app_signals.export_completed.connect(self._on_export_completed)
        app_signals.export_error.connect(self._on_export_error)

    def _on_export_progress(self, progress: int, message: str):
        """Handle export progress updates."""
        self.progress_bar.setValue(progress)
        self.progress_label.setText(message)

        # Add to details log
        self.progress_details.append(f"{progress}%: {message}")

    def _on_export_completed(self, results: Dict[str, Any]):
        """Handle export completion."""
        self.progress_bar.setValue(100)
        self.progress_label.setText("Export completed successfully!")

        # Show completion dialog
        message = f"Export completed successfully!\n\n"
        message += f"Documents exported: {results.get('documents_exported', 0)}\n"
        message += f"Total pages: {results.get('pages_exported', 0)}\n"
        message += f"Output directory: {self.export_settings['output_directory']}"

        QMessageBox.information(self, "Export Complete", message)

        # Close dialog
        self.accept()

    def _on_export_error(self, error_message: str):
        """Handle export error."""
        self.progress_label.setText("Export failed!")

        QMessageBox.critical(self, "Export Failed", f"Export failed:\n\n{error_message}")

        # Re-enable UI
        self.is_exporting = False
        self.export_button.setEnabled(True)
        self.cancel_button.setText("Cancel")
        self.progress_widget.hide()

    def reject(self):
        """Handle dialog rejection/cancellation."""
        if self.is_exporting:
            # Cancel export
            app_signals.processing_cancelled.emit()
            self.export_cancelled.emit()

        super().reject()

    def get_export_settings(self) -> Dict[str, Any]:
        """Get the configured export settings."""
        return self.export_settings

    def closeEvent(self, event):
        """Handle dialog close event."""
        if self.preview_thread and self.preview_thread.isRunning():
            self.preview_thread.terminate()
            self.preview_thread.wait()

        event.accept()
        