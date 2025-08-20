"""
Assignment editor widget for creating and editing page assignments.

Provides a comprehensive interface for assigning pages to index values,
editing field values with validation, and managing assignment properties.
"""

import logging
from typing import Dict, List, Optional, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QTextEdit, QDateEdit, QPushButton, QLabel, QGroupBox, QFrame,
    QMessageBox, QSizePolicy, QCompleter
)
from PySide6.QtCore import Qt, Signal, QDate, QTimer
from PySide6.QtGui import QFont, QPalette, QValidator, QRegularExpressionValidator

from src.models.assignment import PageAssignment, PageReference
from src.models.schema import IndexSchema, IndexField
from src.models.enums import FieldType, ValidationSeverity
from src.core.signals import app_signals


class FieldValueWidget(QWidget):
    """Widget for editing a single field value with validation."""

    value_changed = Signal(str, str)  # field_name, new_value
    validation_changed = Signal(str, bool, str)  # field_name, is_valid, error_message

    def __init__(self, field: IndexField, parent=None):
        super().__init__(parent)

        self.field = field
        self.current_value = ""
        self.is_valid = True
        self.error_message = ""

        # Validation timer for debounced validation
        self.validation_timer = QTimer()
        self.validation_timer.setSingleShot(True)
        self.validation_timer.timeout.connect(self._validate_value)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the field value widget UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create input widget based on field type
        self.input_widget = self._create_input_widget()
        layout.addWidget(self.input_widget, 1)

        # Validation indicator
        self.validation_label = QLabel()
        self.validation_label.setFixedSize(20, 20)
        layout.addWidget(self.validation_label)

        # Set initial state
        self._update_validation_indicator()

    def _create_input_widget(self) -> QWidget:
        """Create appropriate input widget for field type."""
        if self.field.field_type == FieldType.TEXT:
            widget = QLineEdit()
            widget.setPlaceholderText(self.field.placeholder_text or f"Enter {self.field.name.lower()}...")

            # Set up validation
            if hasattr(self.field, 'validation_rules') and self.field.validation_rules:
                rules = self.field.validation_rules
                if 'pattern' in rules:
                    validator = QRegularExpressionValidator()
                    validator.setRegularExpression(rules['pattern'])
                    widget.setValidator(validator)

                if 'max_length' in rules:
                    widget.setMaxLength(rules['max_length'])

            return widget

        elif self.field.field_type == FieldType.NUMBER:
            # Determine if integer or float
            rules = getattr(self.field, 'validation_rules', {})
            if rules.get('integer_only', False):
                widget = QSpinBox()
                widget.setMinimum(rules.get('min_value', -999999))
                widget.setMaximum(rules.get('max_value', 999999))
            else:
                widget = QDoubleSpinBox()
                widget.setMinimum(rules.get('min_value', -999999.0))
                widget.setMaximum(rules.get('max_value', 999999.0))
                widget.setDecimals(2)

            return widget

        elif self.field.field_type == FieldType.DATE:
            widget = QDateEdit()
            widget.setDate(QDate.currentDate())
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
            return widget

        elif self.field.field_type == FieldType.DROPDOWN:
            widget = QComboBox()
            widget.setEditable(False)

            if self.field.dropdown_options:
                widget.addItems(self.field.dropdown_options)

            return widget

        elif self.field.field_type == FieldType.BOOLEAN:
            widget = QCheckBox()
            return widget

        else:
            # Fallback to text input
            return QLineEdit()

    def _connect_signals(self):
        """Connect input widget signals."""
        if isinstance(self.input_widget, QLineEdit):
            self.input_widget.textChanged.connect(self._on_value_changed)
        elif isinstance(self.input_widget, (QSpinBox, QDoubleSpinBox)):
            self.input_widget.valueChanged.connect(self._on_value_changed)
        elif isinstance(self.input_widget, QDateEdit):
            self.input_widget.dateChanged.connect(self._on_value_changed)
        elif isinstance(self.input_widget, QComboBox):
            self.input_widget.currentTextChanged.connect(self._on_value_changed)
        elif isinstance(self.input_widget, QCheckBox):
            self.input_widget.toggled.connect(self._on_value_changed)

    def _on_value_changed(self):
        """Handle value changes in input widget."""
        new_value = self.get_value()
        if new_value != self.current_value:
            self.current_value = new_value
            self.value_changed.emit(self.field.name, new_value)

            # Start validation timer
            self.validation_timer.start(300)  # 300ms debounce

    def _validate_value(self):
        """Validate current field value."""
        value = self.get_value()
        is_valid, error_message = self.field.validate_value(value)

        self.is_valid = is_valid
        self.error_message = error_message or ""

        self._update_validation_indicator()
        self.validation_changed.emit(self.field.name, is_valid, self.error_message)

    def _update_validation_indicator(self):
        """Update validation visual indicator."""
        if self.is_valid:
            self.validation_label.setText("✓")
            self.validation_label.setStyleSheet("color: green; font-weight: bold;")
            self.validation_label.setToolTip("Valid")
        else:
            self.validation_label.setText("✗")
            self.validation_label.setStyleSheet("color: red; font-weight: bold;")
            self.validation_label.setToolTip(self.error_message)

        # Update input widget styling
        if hasattr(self.input_widget, 'setStyleSheet'):
            if self.is_valid:
                self.input_widget.setStyleSheet("")
            else:
                self.input_widget.setStyleSheet("border: 1px solid red;")

    def get_value(self) -> str:
        """Get current field value as string."""
        if isinstance(self.input_widget, QLineEdit):
            return self.input_widget.text()
        elif isinstance(self.input_widget, (QSpinBox, QDoubleSpinBox)):
            return str(self.input_widget.value())
        elif isinstance(self.input_widget, QDateEdit):
            return self.input_widget.date().toString("yyyy-MM-dd")
        elif isinstance(self.input_widget, QComboBox):
            return self.input_widget.currentText()
        elif isinstance(self.input_widget, QCheckBox):
            return "true" if self.input_widget.isChecked() else "false"
        else:
            return ""

    def set_value(self, value: str):
        """Set field value from string."""
        if not value:
            self._set_default_value()
            return

        try:
            if isinstance(self.input_widget, QLineEdit):
                self.input_widget.setText(value)
            elif isinstance(self.input_widget, QSpinBox):
                self.input_widget.setValue(int(float(value)))
            elif isinstance(self.input_widget, QDoubleSpinBox):
                self.input_widget.setValue(float(value))
            elif isinstance(self.input_widget, QDateEdit):
                date = QDate.fromString(value, "yyyy-MM-dd")
                if date.isValid():
                    self.input_widget.setDate(date)
            elif isinstance(self.input_widget, QComboBox):
                index = self.input_widget.findText(value)
                if index >= 0:
                    self.input_widget.setCurrentIndex(index)
            elif isinstance(self.input_widget, QCheckBox):
                self.input_widget.setChecked(value.lower() in ['true', '1', 'yes'])

            self.current_value = value

        except (ValueError, AttributeError) as e:
            logging.warning(f"Failed to set field value for {self.field.name}: {e}")
            self._set_default_value()

    def _set_default_value(self):
        """Set default value for field."""
        default_value = self.field.get_default_value()
        if default_value:
            self.set_value(default_value)

    def set_enabled(self, enabled: bool):
        """Enable or disable the input widget."""
        self.input_widget.setEnabled(enabled)

    def is_field_valid(self) -> bool:
        """Check if current field value is valid."""
        return self.is_valid

    def get_validation_error(self) -> str:
        """Get current validation error message."""
        return self.error_message


class AssignmentEditor(QWidget):
    """Comprehensive assignment editor widget."""

    # Signals
    assignment_changed = Signal(object)  # PageAssignment
    assignment_valid = Signal(bool)
    field_value_changed = Signal(str, str)  # field_name, value
    pages_assignment_requested = Signal(list, dict)  # page_references, index_values

    def __init__(self, schema: IndexSchema = None, parent=None):
        super().__init__(parent)

        self.schema = schema
        self.current_assignment: Optional[PageAssignment] = None
        self.field_widgets: Dict[str, FieldValueWidget] = {}
        self.page_references: List[PageReference] = []

        # Validation state
        self.field_validation_states: Dict[str, bool] = {}
        self.overall_valid = False

        self._setup_ui()

        if schema:
            self.set_schema(schema)

    def _setup_ui(self):
        """Set up the assignment editor UI."""
        layout = QVBoxLayout(self)

        # Header section
        header = self._create_header()
        layout.addWidget(header)

        # Scroll area for field editors
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        self.fields_widget = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_widget)
        self.fields_layout.addStretch()  # Push content to top

        scroll_area.setWidget(self.fields_widget)
        layout.addWidget(scroll_area, 1)

        # Footer with actions
        footer = self._create_footer()
        layout.addWidget(footer)

    def _create_header(self) -> QWidget:
        """Create header widget with assignment info."""
        header = QFrame()
        header.setFrameStyle(QFrame.StyledPanel)
        header.setMaximumHeight(80)

        layout = QVBoxLayout(header)

        # Title
        self.title_label = QLabel("Assignment Editor")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        layout.addWidget(self.title_label)

        # Info line
        info_layout = QHBoxLayout()

        self.schema_label = QLabel("No schema selected")
        self.schema_label.setStyleSheet("color: gray; font-style: italic;")
        info_layout.addWidget(self.schema_label)

        info_layout.addStretch()

        self.pages_label = QLabel("0 pages")
        self.pages_label.setStyleSheet("color: #666;")
        info_layout.addWidget(self.pages_label)

        layout.addLayout(info_layout)

        return header

    def _create_footer(self) -> QWidget:
        """Create footer with action buttons."""
        footer = QFrame()
        footer.setFrameStyle(QFrame.StyledPanel)
        footer.setMaximumHeight(60)

        layout = QHBoxLayout(footer)

        # Validation status
        self.validation_label = QLabel()
        self.validation_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.validation_label)

        layout.addStretch()

        # Action buttons
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_assignment)
        layout.addWidget(self.clear_btn)

        self.create_assignment_btn = QPushButton("Create Assignment")
        self.create_assignment_btn.setDefault(True)
        self.create_assignment_btn.clicked.connect(self._create_assignment)
        layout.addWidget(self.create_assignment_btn)

        # Update validation status
        self._update_validation_status()

        return footer

    def set_schema(self, schema: IndexSchema):
        """Set the indexing schema."""
        self.schema = schema
        self.schema_label.setText(f"Schema: {schema.name}")

        self._rebuild_field_widgets()
        self._update_validation_status()

    def set_page_references(self, page_references: List[PageReference]):
        """Set the page references for this assignment."""
        self.page_references = page_references.copy()
        self.pages_label.setText(f"{len(page_references)} pages")
        self._update_validation_status()

    def _rebuild_field_widgets(self):
        """Rebuild field widgets based on current schema."""
        # Clear existing widgets
        for widget in self.field_widgets.values():
            widget.setParent(None)
        self.field_widgets.clear()
        self.field_validation_states.clear()

        if not self.schema:
            return

        # Create widgets for each field
        for field in sorted(self.schema.fields, key=lambda f: f.display_order):
            field_widget = self._create_field_widget(field)
            self.field_widgets[field.name] = field_widget
            self.field_validation_states[field.name] = not field.required  # Optional fields start valid

    def _create_field_widget(self, field: IndexField) -> QWidget:
        """Create widget for a single field."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)

        # Field label
        label_layout = QHBoxLayout()

        field_label = QLabel(field.name)
        field_font = QFont()
        field_font.setBold(True)
        field_label.setFont(field_font)
        label_layout.addWidget(field_label)

        # Required indicator
        if field.required:
            required_label = QLabel("*")
            required_label.setStyleSheet("color: red; font-weight: bold;")
            required_label.setToolTip("Required field")
            label_layout.addWidget(required_label)

        # Role indicator
        role_label = QLabel(f"({field.role.get_display_name()})")
        role_label.setStyleSheet("color: #666; font-size: 10px;")
        label_layout.addWidget(role_label)

        label_layout.addStretch()
        layout.addLayout(label_layout)

        # Description
        if field.description:
            desc_label = QLabel(field.description)
            desc_label.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        # Field value widget
        value_widget = FieldValueWidget(field)
        value_widget.value_changed.connect(self._on_field_value_changed)
        value_widget.validation_changed.connect(self._on_field_validation_changed)
        layout.addWidget(value_widget)

        # Add to layout
        self.fields_layout.insertWidget(self.fields_layout.count() - 1, container)  # Before stretch

        return value_widget

    def _on_field_value_changed(self, field_name: str, value: str):
        """Handle field value changes."""
        self.field_value_changed.emit(field_name, value)
        self._update_validation_status()

        # Emit assignment changed if we have a current assignment
        if self.current_assignment:
            self.current_assignment.set_index_value(field_name, value)
            self.assignment_changed.emit(self.current_assignment)

    def _on_field_validation_changed(self, field_name: str, is_valid: bool, error_message: str):
        """Handle field validation state changes."""
        self.field_validation_states[field_name] = is_valid
        self._update_validation_status()

    def _update_validation_status(self):
        """Update overall validation status."""
        # Check if all required fields are valid
        all_valid = True
        error_count = 0

        for field_name, is_valid in self.field_validation_states.items():
            if not is_valid:
                all_valid = False
                error_count += 1

        # Check if we have pages
        has_pages = len(self.page_references) > 0

        # Overall validity
        self.overall_valid = all_valid and has_pages and self.schema is not None

        # Update UI
        if self.overall_valid:
            self.validation_label.setText("✓ Assignment is valid")
            self.validation_label.setStyleSheet("color: green; font-weight: bold;")
            self.create_assignment_btn.setEnabled(True)
        else:
            issues = []
            if not has_pages:
                issues.append("no pages selected")
            if error_count > 0:
                issues.append(f"{error_count} field errors")
            if not self.schema:
                issues.append("no schema")

            self.validation_label.setText(f"✗ Issues: {', '.join(issues)}")
            self.validation_label.setStyleSheet("color: red; font-weight: bold;")
            self.create_assignment_btn.setEnabled(False)

        # Emit validation signal
        self.assignment_valid.emit(self.overall_valid)

    def _create_assignment(self):
        """Create assignment from current state."""
        if not self.overall_valid:
            QMessageBox.warning(self, "Invalid Assignment",
                                "Please fix validation errors before creating assignment.")
            return

        # Collect field values
        index_values = {}
        for field_name, field_widget in self.field_widgets.items():
            index_values[field_name] = field_widget.get_value()

        # Emit signal to request assignment creation
        self.pages_assignment_requested.emit(self.page_references, index_values)

    def load_assignment(self, assignment: PageAssignment):
        """Load an existing assignment for editing."""
        self.current_assignment = assignment

        # Set schema if different
        if assignment.schema != self.schema:
            self.set_schema(assignment.schema)

        # Set page references
        self.set_page_references(assignment.page_references)

        # Load field values
        for field_name, value in assignment.index_values.items():
            if field_name in self.field_widgets:
                self.field_widgets[field_name].set_value(value)

        # Update title
        self.title_label.setText(f"Editing Assignment: {assignment.assignment_id[:8]}...")

    def clear_assignment(self):
        """Clear the current assignment."""
        self.current_assignment = None
        self.page_references.clear()

        # Clear field values
        for field_widget in self.field_widgets.values():
            field_widget.set_value("")

        # Reset UI
        self.title_label.setText("Assignment Editor")
        self.pages_label.setText("0 pages")
        self._update_validation_status()

    def get_field_values(self) -> Dict[str, str]:
        """Get current field values."""
        values = {}
        for field_name, field_widget in self.field_widgets.items():
            values[field_name] = field_widget.get_value()
        return values

    def set_field_values(self, values: Dict[str, str]):
        """Set field values."""
        for field_name, value in values.items():
            if field_name in self.field_widgets:
                self.field_widgets[field_name].set_value(value)

    def validate_all_fields(self) -> bool:
        """Validate all fields and return overall validity."""
        for field_widget in self.field_widgets.values():
            field_widget._validate_value()  # Force validation

        self._update_validation_status()
        return self.overall_valid

    def set_enabled(self, enabled: bool):
        """Enable or disable the entire editor."""
        for field_widget in self.field_widgets.values():
            field_widget.set_enabled(enabled)

        self.clear_btn.setEnabled(enabled)
        self.create_assignment_btn.setEnabled(enabled and self.overall_valid)

    def get_assignment_preview(self) -> Optional[Dict[str, Any]]:
        """Get preview of assignment that would be created."""
        if not self.overall_valid:
            return None

        return {
            'schema_name': self.schema.name,
            'page_count': len(self.page_references),
            'field_values': self.get_field_values(),
            'is_valid': self.overall_valid
        }

