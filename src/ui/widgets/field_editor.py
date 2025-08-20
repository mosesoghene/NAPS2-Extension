"""
Schema field editor widget for creating and editing index fields.

Provides a comprehensive interface for configuring field properties,
validation rules, and field-specific options like dropdown choices.
"""

import logging
from typing import Dict, List, Optional, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLineEdit, QComboBox, QSpinBox, QCheckBox, QTextEdit, QPushButton,
    QLabel, QGroupBox, QScrollArea, QListWidget, QListWidgetItem,
    QDialog, QDialogButtonBox, QMessageBox, QFrame, QSplitter
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QPalette, QIcon

from src.models.schema import IndexField
from src.models.enums import FieldType, FieldRole
from src.core.signals import app_signals


class DropdownOptionsEditor(QDialog):
    """Dialog for editing dropdown field options."""

    def __init__(self, options: List[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Dropdown Options")
        self.setModal(True)
        self.resize(400, 300)

        self.options = options.copy() if options else []

        self._setup_ui()
        self._load_options()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel("Enter dropdown options, one per line:")
        layout.addWidget(instructions)

        # Options text editor
        self.options_editor = QTextEdit()
        self.options_editor.setPlaceholderText("Option 1\nOption 2\nOption 3...")
        layout.addWidget(self.options_editor)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_options(self):
        """Load options into editor."""
        if self.options:
            self.options_editor.setPlainText('\n'.join(self.options))

    def get_options(self) -> List[str]:
        """Get edited options list."""
        text = self.options_editor.toPlainText().strip()
        if not text:
            return []

        options = [line.strip() for line in text.split('\n')]
        return [opt for opt in options if opt]  # Filter empty lines


class ValidationRulesEditor(QWidget):
    """Widget for editing field validation rules."""

    rules_changed = Signal(dict)

    def __init__(self, field_type: FieldType, parent=None):
        super().__init__(parent)
        self.field_type = field_type
        self.validation_rules = {}

        self._setup_ui()

    def _setup_ui(self):
        """Set up validation rules UI based on field type."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Common rules
        common_group = QGroupBox("Common Validation")
        common_layout = QFormLayout(common_group)

        self.required_check = QCheckBox("Required Field")
        self.required_check.toggled.connect(self._emit_rules_changed)
        common_layout.addRow(self.required_check)

        layout.addWidget(common_group)

        # Field-specific rules
        if self.field_type == FieldType.TEXT:
            self._setup_text_rules(layout)
        elif self.field_type == FieldType.NUMBER:
            self._setup_number_rules(layout)
        elif self.field_type == FieldType.DATE:
            self._setup_date_rules(layout)

    def _setup_text_rules(self, layout: QVBoxLayout):
        """Set up text field validation rules."""
        text_group = QGroupBox("Text Validation")
        text_layout = QFormLayout(text_group)

        self.min_length_spin = QSpinBox()
        self.min_length_spin.setMinimum(0)
        self.min_length_spin.setMaximum(1000)
        self.min_length_spin.valueChanged.connect(self._emit_rules_changed)
        text_layout.addRow("Minimum Length:", self.min_length_spin)

        self.max_length_spin = QSpinBox()
        self.max_length_spin.setMinimum(1)
        self.max_length_spin.setMaximum(1000)
        self.max_length_spin.setValue(255)
        self.max_length_spin.valueChanged.connect(self._emit_rules_changed)
        text_layout.addRow("Maximum Length:", self.max_length_spin)

        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText("Regular expression pattern")
        self.pattern_edit.textChanged.connect(self._emit_rules_changed)
        text_layout.addRow("Pattern:", self.pattern_edit)

        self.pattern_desc_edit = QLineEdit()
        self.pattern_desc_edit.setPlaceholderText("Pattern description for users")
        self.pattern_desc_edit.textChanged.connect(self._emit_rules_changed)
        text_layout.addRow("Pattern Description:", self.pattern_desc_edit)

        layout.addWidget(text_group)

    def _setup_number_rules(self, layout: QVBoxLayout):
        """Set up number field validation rules."""
        number_group = QGroupBox("Number Validation")
        number_layout = QFormLayout(number_group)

        self.integer_only_check = QCheckBox("Integer Only")
        self.integer_only_check.toggled.connect(self._emit_rules_changed)
        number_layout.addRow(self.integer_only_check)

        self.min_value_spin = QSpinBox()
        self.min_value_spin.setMinimum(-999999)
        self.min_value_spin.setMaximum(999999)
        self.min_value_spin.valueChanged.connect(self._emit_rules_changed)
        number_layout.addRow("Minimum Value:", self.min_value_spin)

        self.max_value_spin = QSpinBox()
        self.max_value_spin.setMinimum(-999999)
        self.max_value_spin.setMaximum(999999)
        self.max_value_spin.setValue(999999)
        self.max_value_spin.valueChanged.connect(self._emit_rules_changed)
        number_layout.addRow("Maximum Value:", self.max_value_spin)

        layout.addWidget(number_group)

    def _setup_date_rules(self, layout: QVBoxLayout):
        """Set up date field validation rules."""
        date_group = QGroupBox("Date Validation")
        date_layout = QFormLayout(date_group)

        # For now, just add a placeholder
        info_label = QLabel("Date validation rules can be added here")
        info_label.setStyleSheet("color: gray; font-style: italic;")
        date_layout.addWidget(info_label)

        layout.addWidget(date_group)

    def _emit_rules_changed(self):
        """Emit rules changed signal with current rules."""
        self.validation_rules = self._get_current_rules()
        self.rules_changed.emit(self.validation_rules)

    def _get_current_rules(self) -> Dict[str, Any]:
        """Get current validation rules."""
        rules = {}

        if hasattr(self, 'required_check'):
            rules['required'] = self.required_check.isChecked()

        if self.field_type == FieldType.TEXT:
            if hasattr(self, 'min_length_spin') and self.min_length_spin.value() > 0:
                rules['min_length'] = self.min_length_spin.value()
            if hasattr(self, 'max_length_spin'):
                rules['max_length'] = self.max_length_spin.value()
            if hasattr(self, 'pattern_edit') and self.pattern_edit.text().strip():
                rules['pattern'] = self.pattern_edit.text().strip()
                if hasattr(self, 'pattern_desc_edit') and self.pattern_desc_edit.text().strip():
                    rules['pattern_description'] = self.pattern_desc_edit.text().strip()

        elif self.field_type == FieldType.NUMBER:
            if hasattr(self, 'integer_only_check'):
                rules['integer_only'] = self.integer_only_check.isChecked()
            if hasattr(self, 'min_value_spin'):
                rules['min_value'] = self.min_value_spin.value()
            if hasattr(self, 'max_value_spin'):
                rules['max_value'] = self.max_value_spin.value()

        return rules

    def set_validation_rules(self, rules: Dict[str, Any]):
        """Set validation rules in UI."""
        self.validation_rules = rules.copy()

        if 'required' in rules and hasattr(self, 'required_check'):
            self.required_check.setChecked(rules['required'])

        if self.field_type == FieldType.TEXT:
            if 'min_length' in rules and hasattr(self, 'min_length_spin'):
                self.min_length_spin.setValue(rules['min_length'])
            if 'max_length' in rules and hasattr(self, 'max_length_spin'):
                self.max_length_spin.setValue(rules['max_length'])
            if 'pattern' in rules and hasattr(self, 'pattern_edit'):
                self.pattern_edit.setText(rules['pattern'])
            if 'pattern_description' in rules and hasattr(self, 'pattern_desc_edit'):
                self.pattern_desc_edit.setText(rules['pattern_description'])

        elif self.field_type == FieldType.NUMBER:
            if 'integer_only' in rules and hasattr(self, 'integer_only_check'):
                self.integer_only_check.setChecked(rules['integer_only'])
            if 'min_value' in rules and hasattr(self, 'min_value_spin'):
                self.min_value_spin.setValue(rules['min_value'])
            if 'max_value' in rules and hasattr(self, 'max_value_spin'):
                self.max_value_spin.setValue(rules['max_value'])


class FieldEditor(QWidget):
    """Comprehensive field editor widget."""

    field_changed = Signal(object)  # IndexField
    field_valid = Signal(bool)

    def __init__(self, field: IndexField = None, parent=None):
        super().__init__(parent)

        self.current_field = field
        self.validation_timer = QTimer()
        self.validation_timer.setSingleShot(True)
        self.validation_timer.timeout.connect(self._validate_field)

        self._setup_ui()
        
        if field:
            self.load_field(field)

        # Connect change signals
        self._connect_change_signals()

    def _setup_ui(self):
        """Set up the field editor UI."""
        layout = QVBoxLayout(self)

        # Create splitter for main areas
        splitter = QSplitter(Qt.Vertical)
        layout.addWidget(splitter)

        # Basic properties section
        basic_widget = self._create_basic_properties_widget()
        splitter.addWidget(basic_widget)

        # Validation rules section
        validation_widget = self._create_validation_widget()
        splitter.addWidget(validation_widget)

        # Set splitter sizes
        splitter.setSizes([300, 200])

    def _create_basic_properties_widget(self) -> QWidget:
        """Create basic field properties widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Title
        title = QLabel("Field Properties")
        title_font = QFont()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Form layout for basic properties
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)

        # Field name
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter field name...")
        form_layout.addRow("Field Name:", self.name_edit)

        # Field type
        self.type_combo = QComboBox()
        for field_type in FieldType:
            self.type_combo.addItem(field_type.get_display_name(), field_type)
        form_layout.addRow("Field Type:", self.type_combo)

        # Field role
        self.role_combo = QComboBox()
        for field_role in FieldRole:
            self.role_combo.addItem(field_role.get_display_name(), field_role)
        form_layout.addRow("Field Role:", self.role_combo)

        # Required checkbox
        self.required_check = QCheckBox("Required Field")
        form_layout.addRow(self.required_check)

        # Default value
        self.default_value_edit = QLineEdit()
        self.default_value_edit.setPlaceholderText("Default value (optional)")
        form_layout.addRow("Default Value:", self.default_value_edit)

        # Description
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(60)
        self.description_edit.setPlaceholderText("Field description for users...")
        form_layout.addRow("Description:", self.description_edit)

        # Placeholder text
        self.placeholder_edit = QLineEdit()
        self.placeholder_edit.setPlaceholderText("Placeholder text for input...")
        form_layout.addRow("Placeholder:", self.placeholder_edit)

        layout.addWidget(form_widget)

        # Dropdown options (shown only for dropdown fields)
        self.dropdown_group = QGroupBox("Dropdown Options")
        dropdown_layout = QVBoxLayout(self.dropdown_group)

        self.options_list = QListWidget()
        self.options_list.setMaximumHeight(100)
        dropdown_layout.addWidget(self.options_list)

        options_buttons = QHBoxLayout()
        self.edit_options_btn = QPushButton("Edit Options...")
        self.edit_options_btn.clicked.connect(self._edit_dropdown_options)
        options_buttons.addWidget(self.edit_options_btn)
        options_buttons.addStretch()

        dropdown_layout.addLayout(options_buttons)
        layout.addWidget(self.dropdown_group)

        # Initially hide dropdown options
        self.dropdown_group.setVisible(False)

        return widget

    def _create_validation_widget(self) -> QWidget:
        """Create validation rules widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Title
        title = QLabel("Validation Rules")
        title_font = QFont()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Scroll area for validation rules
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        # Validation rules editor (will be recreated when field type changes)
        self.validation_editor = None
        self.validation_widget = QWidget()
        self.validation_layout = QVBoxLayout(self.validation_widget)

        scroll_area.setWidget(self.validation_widget)
        layout.addWidget(scroll_area)

        return widget

    def _connect_change_signals(self):
        """Connect all change detection signals."""
        self.name_edit.textChanged.connect(self._on_field_changed)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.role_combo.currentIndexChanged.connect(self._on_field_changed)
        self.required_check.toggled.connect(self._on_field_changed)
        self.default_value_edit.textChanged.connect(self._on_field_changed)
        self.description_edit.textChanged.connect(self._on_field_changed)
        self.placeholder_edit.textChanged.connect(self._on_field_changed)

    def _on_field_changed(self):
        """Handle field property changes."""
        # Debounce validation
        self.validation_timer.start(300)

    def _on_type_changed(self):
        """Handle field type changes."""
        field_type = self.type_combo.currentData()
        
        # Show/hide dropdown options
        self.dropdown_group.setVisible(field_type == FieldType.DROPDOWN)

        # Recreate validation editor for new field type
        self._recreate_validation_editor(field_type)

        self._on_field_changed()

    def _recreate_validation_editor(self, field_type: FieldType):
        """Recreate validation editor for field type."""
        # Remove existing validation editor
        if self.validation_editor:
            self.validation_layout.removeWidget(self.validation_editor)
            self.validation_editor.deleteLater()

        # Create new validation editor
        self.validation_editor = ValidationRulesEditor(field_type)
        self.validation_editor.rules_changed.connect(self._on_field_changed)
        self.validation_layout.addWidget(self.validation_editor)

    def _edit_dropdown_options(self):
        """Open dropdown options editor."""
        current_options = []
        for i in range(self.options_list.count()):
            current_options.append(self.options_list.item(i).text())

        dialog = DropdownOptionsEditor(current_options, self)
        if dialog.exec() == QDialog.Accepted:
            new_options = dialog.get_options()
            self._update_options_list(new_options)
            self._on_field_changed()

    def _update_options_list(self, options: List[str]):
        """Update the options list widget."""
        self.options_list.clear()
        for option in options:
            self.options_list.addItem(option)

    def _validate_field(self):
        """Validate current field configuration."""
        try:
            field = self._create_field_from_ui()
            is_valid = field is not None and self._is_field_valid(field)
            
            self.field_valid.emit(is_valid)
            
            if is_valid:
                self.current_field = field
                self.field_changed.emit(field)

        except Exception as e:
            logging.debug(f"Field validation error: {e}")
            self.field_valid.emit(False)

    def _create_field_from_ui(self) -> Optional[IndexField]:
        """Create IndexField object from current UI state."""
        try:
            name = self.name_edit.text().strip()
            if not name:
                return None

            field_type = self.type_combo.currentData()
            field_role = self.role_combo.currentData()
            required = self.required_check.isChecked()

            field = IndexField(name, field_type, field_role, required)

            # Set additional properties
            default_value = self.default_value_edit.text().strip()
            if default_value:
                field.default_value = default_value

            description = self.description_edit.toPlainText().strip()
            if description:
                field.description = description

            placeholder = self.placeholder_edit.text().strip()
            if placeholder:
                field.placeholder_text = placeholder

            # Set dropdown options
            if field_type == FieldType.DROPDOWN:
                options = []
                for i in range(self.options_list.count()):
                    options.append(self.options_list.item(i).text())
                field.dropdown_options = options

            # Set validation rules
            if self.validation_editor:
                field.validation_rules = self.validation_editor.validation_rules

            return field

        except Exception as e:
            logging.error(f"Error creating field from UI: {e}")
            return None

    def _is_field_valid(self, field: IndexField) -> bool:
        """Check if field configuration is valid."""
        # Field name is required
        if not field.name or not field.name.strip():
            return False

        # Dropdown fields must have options
        if field.field_type == FieldType.DROPDOWN:
            if not field.dropdown_options or len(field.dropdown_options) == 0:
                return False

        # Default value should be valid if set
        if field.default_value:
            is_valid, _ = field.validate_value(field.default_value)
            if not is_valid:
                return False

        return True

    def load_field(self, field: IndexField):
        """Load field into the editor."""
        try:
            self.current_field = field

            # Block signals during loading
            self.name_edit.blockSignals(True)
            self.type_combo.blockSignals(True)
            self.role_combo.blockSignals(True)
            self.required_check.blockSignals(True)
            self.default_value_edit.blockSignals(True)
            self.description_edit.blockSignals(True)
            self.placeholder_edit.blockSignals(True)

            # Load basic properties
            self.name_edit.setText(field.name)

            # Set field type
            for i in range(self.type_combo.count()):
                if self.type_combo.itemData(i) == field.field_type:
                    self.type_combo.setCurrentIndex(i)
                    break

            # Set field role
            for i in range(self.role_combo.count()):
                if self.role_combo.itemData(i) == field.role:
                    self.role_combo.setCurrentIndex(i)
                    break

            self.required_check.setChecked(field.required)

            if field.default_value:
                self.default_value_edit.setText(field.default_value)

            if field.description:
                self.description_edit.setPlainText(field.description)

            if field.placeholder_text:
                self.placeholder_edit.setText(field.placeholder_text)

            # Load dropdown options
            if field.field_type == FieldType.DROPDOWN and field.dropdown_options:
                self._update_options_list(field.dropdown_options)

            # Show/hide dropdown group
            self.dropdown_group.setVisible(field.field_type == FieldType.DROPDOWN)

            # Recreate validation editor for field type
            self._recreate_validation_editor(field.field_type)

            # Load validation rules
            if self.validation_editor and hasattr(field, 'validation_rules'):
                self.validation_editor.set_validation_rules(field.validation_rules)

            # Restore signals
            self.name_edit.blockSignals(False)
            self.type_combo.blockSignals(False)
            self.role_combo.blockSignals(False)
            self.required_check.blockSignals(False)
            self.default_value_edit.blockSignals(False)
            self.description_edit.blockSignals(False)
            self.placeholder_edit.blockSignals(False)

            logging.debug(f"Loaded field: {field.name}")

        except Exception as e:
            logging.error(f"Error loading field: {e}")

    def get_field(self) -> Optional[IndexField]:
        """Get current field from editor."""
        return self.current_field

    def clear(self):
        """Clear the editor."""
        self.current_field = None

        self.name_edit.clear()
        self.type_combo.setCurrentIndex(0)
        self.role_combo.setCurrentIndex(0)
        self.required_check.setChecked(False)
        self.default_value_edit.clear()
        self.description_edit.clear()
        self.placeholder_edit.clear()
        self.options_list.clear()

        # Reset validation editor
        if self.validation_editor:
            field_type = self.type_combo.currentData()
            self._recreate_validation_editor(field_type)

    def set_enabled(self, enabled: bool):
        """Enable or disable the editor."""
        self.name_edit.setEnabled(enabled)
        self.type_combo.setEnabled(enabled)
        self.role_combo.setEnabled(enabled)
        self.required_check.setEnabled(enabled)
        self.default_value_edit.setEnabled(enabled)
        self.description_edit.setEnabled(enabled)
        self.placeholder_edit.setEnabled(enabled)
        self.edit_options_btn.setEnabled(enabled)

        if self.validation_editor:
            self.validation_editor.setEnabled(enabled)

    def set_field_name_readonly(self, readonly: bool):
        """Set field name as readonly (useful when editing existing fields)."""
        self.name_edit.setReadOnly(readonly)