"""
Schema management and index value assignment interface.

Provides interface for selecting schemas, editing field values,
and applying assignments to selected pages.
"""

import logging
from typing import Dict, List, Optional, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QSpinBox,
    QDoubleSpinBox, QDateEdit, QCheckBox, QScrollArea, QFrame,
    QMessageBox, QMenu, QToolButton, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QFont, QPalette, QIcon, QAction

from src.core.exceptions import SchemaValidationError
from src.models.batch import DocumentBatch
from src.models.schema import IndexSchema, IndexField
from src.models.assignment import PageReference, PageAssignment
from src.models.enums import FieldType, FieldRole
from src.ui.widgets.index_field_editor import FieldEditor
from src.ui.widgets.validation_display import ValidationDisplayWidget
from src.core.signals import app_signals


class SchemaSelector(QWidget):
    """Widget for selecting and managing schemas."""

    schema_selected = Signal(object)  # IndexSchema
    schema_creation_requested = Signal()
    schema_edit_requested = Signal(object)  # IndexSchema

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_schema = None
        self.available_schemas = {}  # {name: schema}
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Schema selection combo
        self.schema_combo = QComboBox()
        self.schema_combo.setMinimumWidth(200)
        self.schema_combo.addItem("(No schema selected)")
        layout.addWidget(self.schema_combo)

        # Schema management buttons
        self.manage_button = QToolButton()
        self.manage_button.setText("Manage")
        self.manage_button.setPopupMode(QToolButton.InstantPopup)

        # Create management menu
        manage_menu = QMenu(self)

        new_action = QAction("New Schema...", self)
        new_action.triggered.connect(self.schema_creation_requested.emit)
        manage_menu.addAction(new_action)

        edit_action = QAction("Edit Current Schema...", self)
        edit_action.triggered.connect(self._edit_current_schema)
        manage_menu.addAction(edit_action)

        manage_menu.addSeparator()

        refresh_action = QAction("Refresh Schema List", self)
        refresh_action.triggered.connect(self._refresh_schema_list)
        manage_menu.addAction(refresh_action)

        self.manage_button.setMenu(manage_menu)
        layout.addWidget(self.manage_button)

    def _connect_signals(self):
        """Connect signals."""
        self.schema_combo.currentTextChanged.connect(self._on_schema_selection_changed)

    def load_available_schemas(self, schemas: Dict[str, IndexSchema]):
        """Load available schemas into selector."""
        self.available_schemas = schemas
        self._refresh_combo()

    def _refresh_combo(self):
        """Refresh the schema combo box."""
        current_text = self.schema_combo.currentText()

        self.schema_combo.clear()
        self.schema_combo.addItem("(No schema selected)")

        for name in sorted(self.available_schemas.keys()):
            self.schema_combo.addItem(name)

        # Restore selection if possible
        index = self.schema_combo.findText(current_text)
        if index >= 0:
            self.schema_combo.setCurrentIndex(index)

    def _on_schema_selection_changed(self, schema_name: str):
        """Handle schema selection changes."""
        if schema_name == "(No schema selected)":
            self.current_schema = None
            self.schema_selected.emit(None)
        else:
            schema = self.available_schemas.get(schema_name)
            if schema:
                self.current_schema = schema
                self.schema_selected.emit(schema)

    def _edit_current_schema(self):
        """Request editing of current schema."""
        if self.current_schema:
            self.schema_edit_requested.emit(self.current_schema)

    def _refresh_schema_list(self):
        """Request refresh of schema list."""
        app_signals.schema_list_refresh_requested.emit()

    def set_current_schema(self, schema: Optional[IndexSchema]):
        """Set the currently selected schema."""
        if schema:
            index = self.schema_combo.findText(schema.name)
            if index >= 0:
                self.schema_combo.setCurrentIndex(index)
        else:
            self.schema_combo.setCurrentIndex(0)


class FieldValueEditor(QWidget):
    """Widget for editing field values with validation."""

    values_changed = Signal()
    validation_changed = Signal(bool)  # is_valid

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_schema = None
        self.field_widgets = {}  # {field_name: IndexFieldWidget}
        self.field_values = {}   # {field_name: value}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Scroll area for fields
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Fields container
        self.fields_widget = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_widget)
        self.fields_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.fields_widget)
        layout.addWidget(self.scroll_area)

        # No schema message
        self.no_schema_label = QLabel("No schema selected. Please select or create a schema.")
        self.no_schema_label.setAlignment(Qt.AlignCenter)
        self.no_schema_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.no_schema_label)

        # Initially show no schema message
        self.scroll_area.hide()

    def load_schema(self, schema: Optional[IndexSchema]):
        """Load schema and create field widgets."""
        self.current_schema = schema
        self._clear_field_widgets()

        if not schema:
            self.scroll_area.hide()
            self.no_schema_label.show()
            return

        self.no_schema_label.hide()
        self.scroll_area.show()

        # Create field widgets
        for field in schema.fields:
            widget = FieldEditor(field, self)
            widget.value_changed.connect(self._on_field_value_changed)
            widget.validation_changed.connect(self._on_field_validation_changed)

            self.field_widgets[field.name] = widget
            self.fields_layout.addWidget(widget)

        self.fields_layout.addStretch()
        self._validate_all_fields()

    def _clear_field_widgets(self):
        """Clear all field widgets."""
        for widget in self.field_widgets.values():
            self.fields_layout.removeWidget(widget)
            widget.deleteLater()

        self.field_widgets.clear()
        self.field_values.clear()

    def _on_field_value_changed(self, field_name: str, value: Any):
        """Handle field value changes."""
        self.field_values[field_name] = value
        self.values_changed.emit()
        self._validate_all_fields()

    def _on_field_validation_changed(self, field_name: str, is_valid: bool):
        """Handle field validation changes."""
        self._validate_all_fields()

    def _validate_all_fields(self):
        """Validate all fields and emit validation status."""
        all_valid = True

        for field_name, widget in self.field_widgets.items():
            if not widget.is_valid():
                all_valid = False
                break

        # Check required fields
        if self.current_schema and all_valid:
            for field in self.current_schema.fields:
                if field.required and field.name not in self.field_values:
                    all_valid = False
                    break

        self.validation_changed.emit(all_valid)

    def get_field_values(self) -> Dict[str, Any]:
        """Get current field values."""
        return self.field_values.copy()

    def set_field_values(self, values: Dict[str, Any]):
        """Set field values."""
        for field_name, value in values.items():
            if field_name in self.field_widgets:
                self.field_widgets[field_name].set_value(value)

    def clear_values(self):
        """Clear all field values."""
        for widget in self.field_widgets.values():
            widget.clear_value()
        self.field_values.clear()
        self.values_changed.emit()

    def is_valid(self) -> bool:
        """Check if all fields are valid."""
        for widget in self.field_widgets.values():
            if not widget.is_valid():
                return False

        # Check required fields
        if self.current_schema:
            for field in self.current_schema.fields:
                if field.required and not self.field_values.get(field.name):
                    return False

        return True


class PresetManager(QWidget):
    """Widget for managing field value presets."""

    preset_loaded = Signal(dict)  # field_values

    def __init__(self, parent=None):
        super().__init__(parent)
        self.presets = {}  # {name: field_values}
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Presets:"))

        self.preset_combo = QComboBox()
        self.preset_combo.addItem("(No preset)")
        self.preset_combo.currentTextChanged.connect(self._on_preset_selected)
        layout.addWidget(self.preset_combo)

        self.save_preset_button = QPushButton("Save")
        self.save_preset_button.setMaximumWidth(60)
        self.save_preset_button.clicked.connect(self._save_current_preset)
        layout.addWidget(self.save_preset_button)

        self.delete_preset_button = QPushButton("Delete")
        self.delete_preset_button.setMaximumWidth(60)
        self.delete_preset_button.clicked.connect(self._delete_current_preset)
        layout.addWidget(self.delete_preset_button)

    def _on_preset_selected(self, preset_name: str):
        """Handle preset selection."""
        if preset_name != "(No preset)" and preset_name in self.presets:
            self.preset_loaded.emit(self.presets[preset_name])

    def _save_current_preset(self):
        """Save current values as preset."""
        # This would need access to current field values
        pass

    def _delete_current_preset(self):
        """Delete current preset."""
        current = self.preset_combo.currentText()
        if current != "(No preset)" and current in self.presets:
            reply = QMessageBox.question(
                self, "Delete Preset",
                f"Delete preset '{current}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                del self.presets[current]
                self._refresh_preset_combo()

    def _refresh_preset_combo(self):
        """Refresh preset combo box."""
        current = self.preset_combo.currentText()
        self.preset_combo.clear()
        self.preset_combo.addItem("(No preset)")

        for name in sorted(self.presets.keys()):
            self.preset_combo.addItem(name)

        # Restore selection
        index = self.preset_combo.findText(current)
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)


class IndexPanel(QWidget):
    """Schema management and index value assignment interface."""

    # Signals
    schema_changed = Signal(object)      # IndexSchema
    assignment_applied = Signal(object)  # PageAssignment
    values_changed = Signal(dict)        # field_values

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_batch = None
        self.current_schema = None
        self.selected_pages = []  # List[PageReference]

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Initialize the index panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Schema selection section
        schema_group = QGroupBox("Schema Selection")
        schema_layout = QVBoxLayout(schema_group)

        self.schema_selector = SchemaSelector()
        schema_layout.addWidget(self.schema_selector)

        layout.addWidget(schema_group)

        # Field editing section
        fields_group = QGroupBox("Field Values")
        fields_layout = QVBoxLayout(fields_group)

        # Preset manager
        self.preset_manager = PresetManager()
        fields_layout.addWidget(self.preset_manager)

        # Field editor
        self.field_editor = FieldValueEditor()
        fields_layout.addWidget(self.field_editor)

        layout.addWidget(fields_group)

        # Validation display
        validation_group = QGroupBox("Validation")
        validation_layout = QVBoxLayout(validation_group)

        self.validation_display = ValidationDisplayWidget()
        self.validation_display.setMaximumHeight(100)
        validation_layout.addWidget(self.validation_display)

        layout.addWidget(validation_group)

        # Action buttons
        button_layout = QHBoxLayout()

        self.clear_button = QPushButton("Clear Values")
        self.clear_button.clicked.connect(self._clear_values)
        button_layout.addWidget(self.clear_button)

        button_layout.addStretch()

        self.apply_button = QPushButton("Apply to Selected Pages")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_assignment)
        button_layout.addWidget(self.apply_button)

        layout.addLayout(button_layout)

        # Selection info
        self.selection_label = QLabel("No pages selected")
        self.selection_label.setAlignment(Qt.AlignCenter)
        self.selection_label.setStyleSheet("color: gray; font-style: italic; margin: 5px;")
        layout.addWidget(self.selection_label)

    def _connect_signals(self):
        """Connect internal signals."""
        # Schema selector
        self.schema_selector.schema_selected.connect(self._on_schema_selected)
        self.schema_selector.schema_creation_requested.connect(self._request_schema_creation)
        self.schema_selector.schema_edit_requested.connect(self._request_schema_edit)

        # Field editor
        self.field_editor.values_changed.connect(self._on_values_changed)
        self.field_editor.validation_changed.connect(self._on_validation_changed)

        # Preset manager
        self.preset_manager.preset_loaded.connect(self._load_preset_values)

        # Application signals
        app_signals.pages_selected.connect(self._on_pages_selected)
        app_signals.schema_list_updated.connect(self._on_schema_list_updated)

    def _on_schema_selected(self, schema: Optional[IndexSchema]):
        """Handle schema selection."""
        self.current_schema = schema
        self.field_editor.load_schema(schema)
        self.schema_changed.emit(schema)
        self._update_apply_button_state()

    def _on_values_changed(self):
        """Handle field value changes."""
        values = self.field_editor.get_field_values()
        self.values_changed.emit(values)
        self._update_apply_button_state()

    def _on_validation_changed(self, is_valid: bool):
        """Handle validation changes."""
        self._update_validation_display()
        self._update_apply_button_state()

    def _on_pages_selected(self, selected_pages: List[PageReference]):
        """Handle page selection changes."""
        self.selected_pages = selected_pages
        count = len(selected_pages)

        if count == 0:
            self.selection_label.setText("No pages selected")
        elif count == 1:
            self.selection_label.setText("1 page selected")
        else:
            self.selection_label.setText(f"{count} pages selected")

        self._update_apply_button_state()

    def _on_schema_list_updated(self, schemas: Dict[str, IndexSchema]):
        """Handle schema list updates."""
        self.schema_selector.load_available_schemas(schemas)

    def _load_preset_values(self, values: Dict[str, Any]):
        """Load preset values into field editor."""
        self.field_editor.set_field_values(values)

    def _update_apply_button_state(self):
        """Update the apply button enabled state."""
        has_schema = self.current_schema is not None
        has_pages = len(self.selected_pages) > 0
        is_valid = self.field_editor.is_valid()

        self.apply_button.setEnabled(has_schema and has_pages and is_valid)

    def _update_validation_display(self):
        """Update the validation display."""
        self.validation_display.clear_messages()

        if not self.current_schema:
            return

        # Validate each field
        field_values = self.field_editor.get_field_values()

        for field in self.current_schema.fields:
            try:
                value = field_values.get(field.name, "")
                field.validate_value(value)
            except SchemaValidationError as e:
                self.validation_display.add_error(field.name, str(e))
            except Exception as e:
                self.validation_display.add_warning(field.name, f"Validation issue: {e}")

    def _clear_values(self):
        """Clear all field values."""
        self.field_editor.clear_values()
        self.validation_display.clear_messages()

    def _apply_assignment(self):
        """Apply current values as assignment to selected pages."""
        if not self.current_schema or not self.selected_pages:
            return

        if not self.field_editor.is_valid():
            QMessageBox.warning(
                self, "Invalid Values",
                "Please fix validation errors before applying assignment."
            )
            return

        try:
            # Create assignment
            field_values = self.field_editor.get_field_values()

            # Generate assignment ID
            import uuid
            assignment_id = str(uuid.uuid4())

            # Create assignment object
            assignment = PageAssignment(assignment_id, self.current_schema)

            # Add selected pages
            for page_ref in self.selected_pages:
                assignment.add_page(page_ref)

            # Set field values
            assignment.update_index_values(field_values)

            # Validate assignment
            if assignment.validate_assignment():
                # Add to batch
                if self.current_batch:
                    self.current_batch.assignment_manager.add_assignment(assignment)

                # Emit signal
                self.assignment_applied.emit(assignment)

                # Show success message
                page_count = len(self.selected_pages)
                QMessageBox.information(
                    self, "Assignment Applied",
                    f"Successfully applied assignment to {page_count} pages."
                )

                # Clear values for next assignment
                self._clear_values()

            else:
                QMessageBox.warning(
                    self, "Invalid Assignment",
                    "Assignment validation failed. Please check field values."
                )

        except Exception as e:
            QMessageBox.critical(
                self, "Assignment Error",
                f"Failed to apply assignment: {e}"
            )
            logging.error(f"Assignment application failed: {e}")

    def _request_schema_creation(self):
        """Request new schema creation."""
        app_signals.schema_creation_requested.emit()

    def _request_schema_edit(self, schema: IndexSchema):
        """Request schema editing."""
        app_signals.schema_edit_requested.emit(schema)

    # Public interface
    def load_schema(self, schema: IndexSchema):
        """Load a schema for editing."""
        self.current_schema = schema
        self.field_editor.load_schema(schema)
        self.schema_selector.set_current_schema(schema)

    def set_batch(self, batch: Optional[DocumentBatch]):
        """Set the current document batch."""
        self.current_batch = batch

    def get_current_values(self) -> Dict[str, Any]:
        """Get current field values."""
        return self.field_editor.get_field_values()

    def set_field_values(self, values: Dict[str, Any]):
        """Set field values."""
        self.field_editor.set_field_values(values)

    def clear_selection(self):
        """Clear page selection."""
        self.selected_pages = []
        self.selection_label.setText("No pages selected")
        self._update_apply_button_state()