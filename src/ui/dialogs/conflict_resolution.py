"""
Conflict resolution dialog for handling naming and assignment conflicts.

Provides interface for resolving various types of conflicts that can occur
during document processing and export operations.
"""

import logging
from typing import Dict, List, Optional, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QTextEdit,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QSplitter, QWidget, QScrollArea, QButtonGroup,
    QRadioButton, QMessageBox, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QIcon, QPalette

from src.models.enums import ConflictType, ConflictResolution
from src.core.exceptions import ConflictError


class ConflictInfo:
    """Information about a specific conflict."""

    def __init__(self, conflict_id: str, conflict_type: ConflictType,
                 description: str, affected_files: List[str] = None,
                 severity: str = "medium"):
        self.conflict_id = conflict_id
        self.conflict_type = conflict_type
        self.description = description
        self.affected_files = affected_files or []
        self.severity = severity
        self.suggested_resolutions = self._get_suggested_resolutions()
        self.resolution = None
        self.custom_value = None

    def _get_suggested_resolutions(self) -> List[ConflictResolution]:
        """Get suggested resolutions based on conflict type."""
        if self.conflict_type == ConflictType.DUPLICATE_FILENAME:
            return [
                ConflictResolution.AUTO_RENAME,
                ConflictResolution.PROMPT_USER,
                ConflictResolution.OVERWRITE
            ]
        elif self.conflict_type == ConflictType.INVALID_PATH:
            return [
                ConflictResolution.AUTO_FIX,
                ConflictResolution.PROMPT_USER,
                ConflictResolution.SKIP_DUPLICATE
            ]
        elif self.conflict_type == ConflictType.MISSING_REQUIRED_FIELD:
            return [
                ConflictResolution.PROMPT_USER,
                ConflictResolution.USE_DEFAULT,
                ConflictResolution.SKIP_DUPLICATE
            ]
        else:
            return [ConflictResolution.PROMPT_USER]


class ConflictItemWidget(QWidget):
    """Widget for displaying and resolving individual conflicts."""

    resolution_changed = Signal(str, object)  # conflict_id, resolution

    def __init__(self, conflict_info: ConflictInfo, parent=None):
        super().__init__(parent)
        self.conflict_info = conflict_info
        self.resolution_group = None
        self.custom_input = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Conflict header
        header_layout = QHBoxLayout()

        # Severity indicator
        severity_label = QLabel(f"[{self.conflict_info.severity.upper()}]")
        if self.conflict_info.severity == "high":
            severity_label.setStyleSheet("color: red; font-weight: bold;")
        elif self.conflict_info.severity == "medium":
            severity_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            severity_label.setStyleSheet("color: blue;")
        header_layout.addWidget(severity_label)

        # Conflict type
        type_label = QLabel(self.conflict_info.conflict_type.get_display_name())
        type_label.setFont(QFont("", -1, QFont.Bold))
        header_layout.addWidget(type_label)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Description
        desc_label = QLabel(self.conflict_info.description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: gray; margin: 5px 0px;")
        layout.addWidget(desc_label)

        # Affected files
        if self.conflict_info.affected_files:
            files_label = QLabel("Affected files:")
            files_label.setFont(QFont("", -1, QFont.Bold))
            layout.addWidget(files_label)

            for file_path in self.conflict_info.affected_files:
                file_label = QLabel(f"  • {file_path}")
                file_label.setStyleSheet("font-family: monospace; color: gray;")
                layout.addWidget(file_label)

        # Resolution options
        resolution_group = QGroupBox("Resolution:")
        resolution_layout = QVBoxLayout(resolution_group)

        self.resolution_group = QButtonGroup()

        for resolution in self.conflict_info.suggested_resolutions:
            radio = QRadioButton(resolution.get_display_name())
            radio.setProperty("resolution", resolution)
            self.resolution_group.addButton(radio)
            resolution_layout.addWidget(radio)

            # Set first option as default
            if self.resolution_group.buttons().index(radio) == 0:
                radio.setChecked(True)
                self.conflict_info.resolution = resolution

        # Custom input for certain resolutions
        if ConflictResolution.PROMPT_USER in self.conflict_info.suggested_resolutions:
            self.custom_input = QLineEdit()
            self.custom_input.setPlaceholderText("Enter custom value...")
            self.custom_input.setEnabled(False)
            resolution_layout.addWidget(self.custom_input)

        layout.addWidget(resolution_group)

        # Connect signals
        self.resolution_group.buttonClicked.connect(self._on_resolution_changed)
        if self.custom_input:
            self.custom_input.textChanged.connect(self._on_custom_value_changed)

    def _on_resolution_changed(self, button):
        resolution = button.property("resolution")
        self.conflict_info.resolution = resolution

        # Enable custom input for PROMPT_USER
        if self.custom_input:
            enable_custom = (resolution == ConflictResolution.PROMPT_USER)
            self.custom_input.setEnabled(enable_custom)
            if not enable_custom:
                self.custom_input.clear()

        self.resolution_changed.emit(self.conflict_info.conflict_id, resolution)

    def _on_custom_value_changed(self, text):
        self.conflict_info.custom_value = text

    def get_resolution(self) -> tuple:
        """Get the selected resolution and any custom value."""
        return self.conflict_info.resolution, self.conflict_info.custom_value


class ConflictResolutionDialog(QDialog):
    """Dialog for resolving naming and assignment conflicts."""

    # Signals
    conflicts_resolved = Signal(dict)  # {conflict_id: (resolution, custom_value)}

    def __init__(self, conflicts: List[ConflictInfo], parent=None):
        super().__init__(parent)

        self.conflicts = conflicts
        self.conflict_widgets = {}
        self.resolution_results = {}
        self.auto_apply_similar = False

        self._setup_ui()
        self._populate_conflicts()

    def _setup_ui(self):
        """Set up the conflict resolution dialog UI."""
        self.setWindowTitle(f"Resolve Conflicts ({len(self.conflicts)} found)")
        self.setModal(True)
        self.resize(700, 600)

        layout = QVBoxLayout(self)

        # Header section
        header_layout = QVBoxLayout()

        title_label = QLabel("The following conflicts need to be resolved:")
        title_label.setFont(QFont("", -1, QFont.Bold))
        header_layout.addWidget(title_label)

        info_label = QLabel(
            "Review each conflict and select the appropriate resolution method. "
            "Some conflicts may be resolved automatically based on your selection."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; margin: 5px 0px;")
        header_layout.addWidget(info_label)

        layout.addLayout(header_layout)

        # Conflict list section
        conflicts_group = QGroupBox("Conflicts:")
        conflicts_layout = QVBoxLayout(conflicts_group)

        # Scroll area for conflicts
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.conflicts_widget = QWidget()
        self.conflicts_layout = QVBoxLayout(self.conflicts_widget)

        scroll_area.setWidget(self.conflicts_widget)
        conflicts_layout.addWidget(scroll_area)

        layout.addWidget(conflicts_group)

        # Global options
        options_group = QGroupBox("Global Options:")
        options_layout = QVBoxLayout(options_group)

        self.auto_similar_check = QCheckBox("Apply similar resolutions to similar conflicts")
        self.auto_similar_check.setToolTip(
            "When enabled, the same resolution will be applied to conflicts of the same type"
        )
        options_layout.addWidget(self.auto_similar_check)

        # Quick resolution buttons
        quick_layout = QHBoxLayout()

        self.auto_rename_all_button = QPushButton("Auto-rename All")
        self.auto_rename_all_button.clicked.connect(
            lambda: self._apply_resolution_to_all(ConflictResolution.AUTO_RENAME)
        )
        quick_layout.addWidget(self.auto_rename_all_button)

        self.skip_all_button = QPushButton("Skip All")
        self.skip_all_button.clicked.connect(
            lambda: self._apply_resolution_to_all(ConflictResolution.SKIP_DUPLICATE)
        )
        quick_layout.addWidget(self.skip_all_button)

        quick_layout.addStretch()
        options_layout.addLayout(quick_layout)

        layout.addWidget(options_group)

        # Progress section (initially hidden)
        self.progress_widget = QGroupBox("Processing Conflicts:")
        progress_layout = QVBoxLayout(self.progress_widget)

        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("Ready to process conflicts...")
        progress_layout.addWidget(self.progress_label)

        layout.addWidget(self.progress_widget)
        self.progress_widget.hide()

        # Button section
        button_layout = QHBoxLayout()

        self.preview_button = QPushButton("Preview Results")
        self.preview_button.clicked.connect(self._preview_resolutions)
        button_layout.addWidget(self.preview_button)

        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.resolve_button = QPushButton("Apply Resolutions")
        self.resolve_button.setDefault(True)
        self.resolve_button.clicked.connect(self._apply_resolutions)
        button_layout.addWidget(self.resolve_button)

        layout.addLayout(button_layout)

    def _populate_conflicts(self):
        """Populate the conflicts list with widgets."""
        for conflict in self.conflicts:
            widget = ConflictItemWidget(conflict)
            widget.resolution_changed.connect(self._on_resolution_changed)

            self.conflict_widgets[conflict.conflict_id] = widget
            self.conflicts_layout.addWidget(widget)

        self.conflicts_layout.addStretch()

    def _on_resolution_changed(self, conflict_id: str, resolution: ConflictResolution):
        """Handle resolution changes."""
        # If auto-apply is enabled, apply to similar conflicts
        if self.auto_similar_check.isChecked():
            current_conflict = next(c for c in self.conflicts if c.conflict_id == conflict_id)
            self._apply_to_similar_conflicts(current_conflict.conflict_type, resolution)

    def _apply_to_similar_conflicts(self, conflict_type: ConflictType, resolution: ConflictResolution):
        """Apply resolution to conflicts of the same type."""
        for conflict in self.conflicts:
            if conflict.conflict_type == conflict_type and resolution in conflict.suggested_resolutions:
                widget = self.conflict_widgets[conflict.conflict_id]
                # Find and click the appropriate radio button
                for button in widget.resolution_group.buttons():
                    if button.property("resolution") == resolution:
                        button.setChecked(True)
                        break

    def _apply_resolution_to_all(self, resolution: ConflictResolution):
        """Apply the same resolution to all compatible conflicts."""
        for conflict in self.conflicts:
            if resolution in conflict.suggested_resolutions:
                widget = self.conflict_widgets[conflict.conflict_id]
                # Find and click the appropriate radio button
                for button in widget.resolution_group.buttons():
                    if button.property("resolution") == resolution:
                        button.setChecked(True)
                        break

    def _preview_resolutions(self):
        """Preview the effects of current resolutions."""
        results = self._collect_resolutions()

        # Create preview dialog
        preview_dialog = QDialog(self)
        preview_dialog.setWindowTitle("Resolution Preview")
        preview_dialog.resize(500, 400)

        layout = QVBoxLayout(preview_dialog)

        preview_text = QTextEdit()
        preview_text.setReadOnly(True)

        preview_content = "Resolution Preview:\n\n"

        for conflict in self.conflicts:
            resolution, custom_value = results.get(conflict.conflict_id, (None, None))

            preview_content += f"Conflict: {conflict.description}\n"
            preview_content += f"Resolution: {resolution.get_display_name() if resolution else 'None'}\n"

            if custom_value:
                preview_content += f"Custom Value: {custom_value}\n"

            # Show preview of result
            if resolution == ConflictResolution.AUTO_RENAME:
                preview_content += "Result: File will be automatically renamed\n"
            elif resolution == ConflictResolution.OVERWRITE:
                preview_content += "Result: Existing file will be overwritten\n"
            elif resolution == ConflictResolution.SKIP_DUPLICATE:
                preview_content += "Result: Conflicting item will be skipped\n"
            elif resolution == ConflictResolution.PROMPT_USER and custom_value:
                preview_content += f"Result: Will use custom value '{custom_value}'\n"

            preview_content += "\n" + "-" * 50 + "\n\n"

        preview_text.setPlainText(preview_content)
        layout.addWidget(preview_text)

        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(preview_dialog.accept)
        layout.addWidget(close_button)

        preview_dialog.exec()

    def _collect_resolutions(self) -> Dict[str, tuple]:
        """Collect resolutions from all conflict widgets."""
        results = {}

        for conflict_id, widget in self.conflict_widgets.items():
            resolution, custom_value = widget.get_resolution()
            results[conflict_id] = (resolution, custom_value)

        return results

    def _validate_resolutions(self) -> List[str]:
        """Validate all resolutions and return any errors."""
        errors = []

        results = self._collect_resolutions()

        for conflict in self.conflicts:
            resolution, custom_value = results.get(conflict.conflict_id, (None, None))

            if not resolution:
                errors.append(f"No resolution selected for: {conflict.description}")

            # Validate custom values where required
            if resolution == ConflictResolution.PROMPT_USER:
                if not custom_value or not custom_value.strip():
                    errors.append(f"Custom value required for: {conflict.description}")

        return errors

    def _apply_resolutions(self):
        """Apply all selected resolutions."""
        # Validate resolutions
        errors = self._validate_resolutions()
        if errors:
            QMessageBox.warning(
                self, "Invalid Resolutions",
                "Please fix the following issues:\n\n" + "\n".join(errors)
            )
            return

        # Show progress
        self.progress_widget.show()
        self.progress_bar.setMaximum(len(self.conflicts))
        self.progress_bar.setValue(0)

        # Disable UI
        self.resolve_button.setEnabled(False)
        self.preview_button.setEnabled(False)

        # Collect and emit results
        self.resolution_results = self._collect_resolutions()

        # Simulate processing (in real implementation, this would be done by the processor)
        timer = QTimer()
        current_index = 0

        def process_next():
            nonlocal current_index
            if current_index < len(self.conflicts):
                conflict = self.conflicts[current_index]
                self.progress_bar.setValue(current_index + 1)
                self.progress_label.setText(f"Processing: {conflict.description[:50]}...")
                current_index += 1
            else:
                timer.stop()
                self._finish_resolution()

        timer.timeout.connect(process_next)
        timer.start(100)  # Process every 100ms

    def _finish_resolution(self):
        """Finish the resolution process."""
        self.progress_bar.setValue(len(self.conflicts))
        self.progress_label.setText("All conflicts resolved!")

        self.conflicts_resolved.emit(self.resolution_results)

        QMessageBox.information(
            self, "Conflicts Resolved",
            f"Successfully resolved {len(self.conflicts)} conflicts."
        )

        self.accept()

    def get_resolution_results(self) -> Dict[str, tuple]:
        """Get the resolution results."""
        return self.resolution_results

    def closeEvent(self, event):
        """Handle dialog close event."""
        if not self.resolution_results:
            reply = QMessageBox.question(
                self, "Cancel Resolution",
                "Are you sure you want to cancel conflict resolution?\n\n"
                "Unresolved conflicts may prevent successful export.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                event.ignore()
                return

        event.accept()

