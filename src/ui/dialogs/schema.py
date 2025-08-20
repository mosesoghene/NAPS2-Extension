"""
Schema dialog for creating and editing indexing schemas.

Provides comprehensive interface for schema creation with field management,
validation, and preview capabilities.
"""

import logging
from typing import Dict, List, Optional, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QTextEdit,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QSplitter, QTabWidget, QWidget, QScrollArea,
    QMessageBox, QInputDialog, QMenu, QHeaderView
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QAction, QIcon, QDrag, QPixmap

from src.models.schema import IndexSchema, IndexField, SchemaBuilder
from src.models.enums import FieldType, FieldRole
from src.ui.widgets.index_field_editor import FieldEditor
from src.core.signals import app_signals


class SchemaFieldListWidget(QListWidget):
    """Custom list widget for schema fields with drag and drop support."""

    fields_reordered = Signal(list)  # List[str] - field names in new order

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)

    def dropEvent(self, event):
        super().dropEvent(event)
        # Emit field order after drop
        field_names = []
        for i in range(self.count()):
            item = self.item(i)
            field_names.append(item.data(Qt.UserRole).name)
        self.fields_reordered.emit(field_names)


class SchemaPreviewWidget(QWidget):
    """Widget for previewing schema folder structure."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Preview tree
        self.preview_tree = QTreeWidget()
        self.preview_tree.setHeaderLabels(["Folder Structure", "Field", "Role"])
        self.preview_tree.header().setStretchLastSection(False)
        self.preview_tree.header().resizeSection(0, 200)
        layout.addWidget(self.preview_tree)

        # Sample data section
        sample_group = QGroupBox("Sample Data")
        sample_layout = QVBoxLayout(sample_group)

        self.sample_data_edit = QTextEdit()
        self.sample_data_edit.setMaximumHeight(100)
        self.sample_data_edit.setPlainText(
            "Document Type: Invoice\n"
            "Date: 2024-01-15\n"
            "Client: ABC Company\n"
            "Amount: 1250.00"
        )
        sample_layout.addWidget(self.sample_data_edit)

        update_button = QPushButton("Update Preview")
        update_button.clicked.connect(self.update_preview)
        sample_layout.addWidget(update_button)

        layout.addWidget(sample_group)

        self.current_schema = None

    def set_schema(self, schema: IndexSchema):
        """Set schema to preview."""
        self.current_schema = schema
        self.update_preview()

    def update_preview(self):
        """Update the preview with current schema and sample data."""
        if not self.current_schema:
            return

        self.preview_tree.clear()

        try:
            # Parse sample data
            sample_values = {}
            for line in self.sample_data_edit.toPlainText().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    sample_values[key.strip().lower().replace(' ', '_')] = value.strip()

            # Generate folder structure
            folder_structure = self.current_schema.generate_folder_structure(sample_values)
            filename = self.current_schema.generate_filename(sample_values)

            # Build preview tree
            if folder_structure:
                folder_parts = folder_structure.split('/')
                current_parent = None

                for i, part in enumerate(folder_parts):
                    item = QTreeWidgetItem([part, "", "Folder"])
                    if current_parent:
                        current_parent.addChild(item)
                    else:
                        self.preview_tree.addTopLevelItem(item)
                    current_parent = item

                # Add filename to last folder
                if current_parent:
                    file_item = QTreeWidgetItem([f"{filename}.pdf", "", "File"])
                    current_parent.addChild(file_item)
            else:
                # No folder structure, just filename
                file_item = QTreeWidgetItem([f"{filename}.pdf", "", "File"])
                self.preview_tree.addTopLevelItem(file_item)

            # Show field mappings
            for field in self.current_schema.fields:
                field_item = QTreeWidgetItem([
                    field.name,
                    sample_values.get(field.name.lower().replace(' ', '_'), ''),
                    field.role.get_display_name()
                ])
                self.preview_tree.addTopLevelItem(field_item)

            self.preview_tree.expandAll()

        except Exception as e:
            logging.warning(f"Error updating schema preview: {e}")


class SchemaDialog(QDialog):
    """Dialog for creating and editing indexing schemas."""

    # Signals
    schema_created = Signal(object)  # IndexSchema
    schema_updated = Signal(object)  # IndexSchema
    schema_deleted = Signal(str)     # schema_name

    def __init__(self, schema: IndexSchema = None, parent=None):
        super().__init__(parent)

        self.current_schema = schema
        self.is_editing = schema is not None
        self.has_changes = False
        self.field_editor = None

        # Field management
        self.editing_field_index = -1

        self._setup_ui()
        self._connect_signals()

        if schema:
            self._load_schema(schema)
        else:
            self._create_new_schema()

    def _setup_ui(self):
        """Set up the schema dialog UI."""
        title = "Edit Schema" if self.is_editing else "Create New Schema"
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(900, 700)

        layout = QVBoxLayout(self)

        # Create main splitter
        main_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(main_splitter)

        # Left panel - schema details and fields
        left_panel = self._create_left_panel()
        main_splitter.addWidget(left_panel)

        # Right panel - field editor and preview
        right_panel = self._create_right_panel()
        main_splitter.addWidget(right_panel)

        # Set splitter sizes
        main_splitter.setSizes([400, 500])

        # Button layout
        button_layout = QHBoxLayout()

        if self.is_editing:
            self.delete_button = QPushButton("Delete Schema")
            self.delete_button.clicked.connect(self._delete_schema)
            button_layout.addWidget(self.delete_button)

        button_layout.addStretch()

        self.test_button = QPushButton("Test Schema")
        self.test_button.clicked.connect(self._test_schema)
        button_layout.addWidget(self.test_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.save_button = QPushButton("Save Schema")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save_schema)
        button_layout.addWidget(self.save_button)

        layout.addLayout(button_layout)

    def _create_left_panel(self) -> QWidget:
        """Create left panel with schema details and field list."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Schema details section
        details_group = QGroupBox("Schema Details")
        details_layout = QFormLayout(details_group)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter schema name...")
        details_layout.addRow("Name:", self.name_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(60)
        self.description_edit.setPlaceholderText("Enter schema description...")
        details_layout.addRow("Description:", self.description_edit)

        layout.addWidget(details_group)

        # Fields section
        fields_group = QGroupBox("Schema Fields")
        fields_layout = QVBoxLayout(fields_group)

        # Field list toolbar
        field_toolbar = QHBoxLayout()

        self.add_field_button = QPushButton("Add Field")
        self.add_field_button.clicked.connect(self._add_field)
        field_toolbar.addWidget(self.add_field_button)

        self.remove_field_button = QPushButton("Remove Field")
        self.remove_field_button.setEnabled(False)
        self.remove_field_button.clicked.connect(self._remove_field)
        field_toolbar.addWidget(self.remove_field_button)

        field_toolbar.addStretch()

        self.move_up_button = QPushButton("↑")
        self.move_up_button.setMaximumWidth(30)
        self.move_up_button.setEnabled(False)
        self.move_up_button.clicked.connect(self._move_field_up)
        field_toolbar.addWidget(self.move_up_button)

        self.move_down_button = QPushButton("↓")
        self.move_down_button.setMaximumWidth(30)
        self.move_down_button.setEnabled(False)
        self.move_down_button.clicked.connect(self._move_field_down)
        field_toolbar.addWidget(self.move_down_button)

        fields_layout.addLayout(field_toolbar)

        # Fields list
        self.fields_list = SchemaFieldListWidget()
        self.fields_list.itemSelectionChanged.connect(self._on_field_selection_changed)
        self.fields_list.itemDoubleClicked.connect(self._edit_field)
        self.fields_list.fields_reordered.connect(self._on_fields_reordered)
        fields_layout.addWidget(self.fields_list)

        layout.addWidget(fields_group)

        return widget

    def _create_right_panel(self) -> QWidget:
        """Create right panel with field editor and preview."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Create tab widget
        tab_widget = QTabWidget()
        layout.addWidget(tab_widget)

        # Field editor tab
        editor_tab = QWidget()
        editor_layout = QVBoxLayout(editor_tab)

        self.field_editor = FieldEditor()
        self.field_editor.field_changed.connect(self._on_field_edited)
        self.field_editor.field_valid.connect(self._on_field_validation_changed)
        editor_layout.addWidget(self.field_editor)

        # Field editor buttons
        editor_buttons = QHBoxLayout()

        self.clear_field_button = QPushButton("Clear")
        self.clear_field_button.clicked.connect(self._clear_field_editor)
        editor_buttons.addWidget(self.clear_field_button)

        editor_buttons.addStretch()

        self.apply_field_button = QPushButton("Apply Changes")
        self.apply_field_button.setEnabled(False)
        self.apply_field_button.clicked.connect(self._apply_field_changes)
        editor_buttons.addWidget(self.apply_field_button)

        editor_layout.addLayout(editor_buttons)

        tab_widget.addTab(editor_tab, "Field Editor")

        # Preview tab
        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)

        self.preview_widget = SchemaPreviewWidget()
        preview_layout.addWidget(self.preview_widget)

        tab_widget.addTab(preview_tab, "Preview")

        return widget

    def _connect_signals(self):
        """Connect UI signals to handlers."""
        self.name_edit.textChanged.connect(self._mark_changed)
        self.description_edit.textChanged.connect(self._mark_changed)

    def _create_new_schema(self):
        """Initialize for creating a new schema."""
        self.current_schema = IndexSchema("", "")
        self.name_edit.setFocus()

    def _load_schema(self, schema: IndexSchema):
        """Load existing schema into the dialog."""
        self.current_schema = schema.clone()

        # Load basic details
        self.name_edit.setText(schema.name)
        self.description_edit.setPlainText(schema.description)

        # Load fields
        self._update_fields_list()

        # Update preview
        self.preview_widget.set_schema(self.current_schema)

    def _update_fields_list(self):
        """Update the fields list widget."""
        self.fields_list.clear()

        for field in self.current_schema.fields:
            item = QListWidgetItem()
            item.setText(f"{field.name} ({field.field_type.get_display_name()})")
            item.setData(Qt.UserRole, field)

            # Add role indicator
            if field.required:
                item.setText(item.text() + " *")

            # Add role color coding
            if field.role == FieldRole.FOLDER:
                item.setBackground(Qt.lightGray)
            elif field.role == FieldRole.FILENAME:
                item.setBackground(Qt.cyan)

            self.fields_list.addItem(item)

    def _mark_changed(self):
        """Mark that schema has been changed."""
        self.has_changes = True
        self.save_button.setEnabled(True)

    def _on_field_selection_changed(self):
        """Handle field selection changes."""
        selected_items = self.fields_list.selectedItems()
        has_selection = len(selected_items) > 0

        self.remove_field_button.setEnabled(has_selection)
        self.move_up_button.setEnabled(has_selection)
        self.move_down_button.setEnabled(has_selection)

        if selected_items:
            field = selected_items[0].data(Qt.UserRole)
            self.field_editor.load_field(field)
            self.editing_field_index = self.fields_list.row(selected_items[0])
        else:
            self.field_editor.clear()
            self.editing_field_index = -1

    def _on_field_edited(self, field: IndexField):
        """Handle field being edited."""
        self.apply_field_button.setEnabled(True)

    def _on_field_validation_changed(self, is_valid: bool):
        """Handle field validation changes."""
        self.apply_field_button.setEnabled(is_valid)

    def _add_field(self):
        """Add a new field to the schema."""
        # Get field name from user
        name, ok = QInputDialog.getText(
            self, "New Field", "Enter field name:",
            text="New Field"
        )

        if not ok or not name.strip():
            return

        # Check for duplicate names
        existing_names = [f.name.lower() for f in self.current_schema.fields]
        if name.lower() in existing_names:
            QMessageBox.warning(self, "Duplicate Field",
                                f"A field named '{name}' already exists.")
            return

        # Create new field with defaults
        field = IndexField(name.strip(), FieldType.TEXT, FieldRole.METADATA)

        try:
            self.current_schema.add_field(field)
            self._update_fields_list()

            # Select the new field
            self.fields_list.setCurrentRow(self.fields_list.count() - 1)

            self._mark_changed()

        except Exception as e:
            QMessageBox.warning(self, "Add Field Error", f"Failed to add field: {e}")

    def _remove_field(self):
        """Remove selected field from schema."""
        current_item = self.fields_list.currentItem()
        if not current_item:
            return

        field = current_item.data(Qt.UserRole)

        reply = QMessageBox.question(
            self, "Remove Field",
            f"Are you sure you want to remove the field '{field.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                self.current_schema.remove_field(field.name)
                self._update_fields_list()
                self.field_editor.clear()
                self._mark_changed()

            except Exception as e:
                QMessageBox.warning(self, "Remove Field Error", f"Failed to remove field: {e}")

    def _move_field_up(self):
        """Move selected field up in the list."""
        current_row = self.fields_list.currentRow()
        if current_row <= 0:
            return

        # Swap fields in schema
        fields = self.current_schema.fields
        fields[current_row], fields[current_row - 1] = fields[current_row - 1], fields[current_row]

        # Update display order
        for i, field in enumerate(fields):
            field.display_order = i + 1

        self._update_fields_list()
        self.fields_list.setCurrentRow(current_row - 1)
        self._mark_changed()

    def _move_field_down(self):
        """Move selected field down in the list."""
        current_row = self.fields_list.currentRow()
        if current_row >= self.fields_list.count() - 1:
            return

        # Swap fields in schema
        fields = self.current_schema.fields
        fields[current_row], fields[current_row + 1] = fields[current_row + 1], fields[current_row]

        # Update display order
        for i, field in enumerate(fields):
            field.display_order = i + 1

        self._update_fields_list()
        self.fields_list.setCurrentRow(current_row + 1)
        self._mark_changed()

    def _on_fields_reordered(self, field_names: List[str]):
        """Handle fields being reordered by drag and drop."""
        try:
            self.current_schema.reorder_fields(field_names)
            self._mark_changed()
        except Exception as e:
            QMessageBox.warning(self, "Reorder Error", f"Failed to reorder fields: {e}")
            self._update_fields_list()  # Restore original order

    def _edit_field(self, item: QListWidgetItem):
        """Handle double-click to edit field."""
        field = item.data(Qt.UserRole)
        self.field_editor.load_field(field)

    def _clear_field_editor(self):
        """Clear the field editor."""
        self.field_editor.clear()
        self.apply_field_button.setEnabled(False)

    def _apply_field_changes(self):
        """Apply changes from field editor to selected field."""
        if self.editing_field_index < 0:
            return

        edited_field = self.field_editor.get_field()
        if not edited_field:
            return

        try:
            # Update field in schema
            self.current_schema.fields[self.editing_field_index] = edited_field
            self._update_fields_list()

            # Maintain selection
            self.fields_list.setCurrentRow(self.editing_field_index)

            self.apply_field_button.setEnabled(False)
            self._mark_changed()

        except Exception as e:
            QMessageBox.warning(self, "Apply Changes Error", f"Failed to apply changes: {e}")

    def _test_schema(self):
        """Test schema with sample data."""
        if not self._validate_schema():
            return

        # Update current schema from UI
        self._update_schema_from_ui()

        # Update preview
        self.preview_widget.set_schema(self.current_schema)

        # Show success message
        QMessageBox.information(self, "Schema Test",
                                "Schema test completed successfully!\n\n"
                                "Check the Preview tab to see the generated folder structure.")

    def _update_schema_from_ui(self):
        """Update current schema from UI inputs."""
        self.current_schema.name = self.name_edit.text().strip()
        self.current_schema.description = self.description_edit.toPlainText().strip()

    def _validate_schema(self) -> bool:
        """Validate current schema."""
        # Update schema from UI first
        self._update_schema_from_ui()

        if not self.current_schema.name:
            QMessageBox.warning(self, "Validation Error", "Schema name is required.")
            self.name_edit.setFocus()
            return False

        if not self.current_schema.fields:
            QMessageBox.warning(self, "Validation Error",
                                "Schema must have at least one field.")
            return False

        # Validate schema structure
        is_valid, errors = self.current_schema.validate_schema()
        if not is_valid:
            QMessageBox.warning(self, "Schema Validation Failed",
                                "Schema validation failed:\n\n" + "\n".join(errors))
            return False

        return True

    def _save_schema(self):
        """Save the current schema."""
        if not self._validate_schema():
            return

        try:
            if self.is_editing:
                self.schema_updated.emit(self.current_schema)
                QMessageBox.information(self, "Schema Saved",
                                        f"Schema '{self.current_schema.name}' updated successfully.")
            else:
                self.schema_created.emit(self.current_schema)
                QMessageBox.information(self, "Schema Created",
                                        f"Schema '{self.current_schema.name}' created successfully.")

            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save schema: {e}")

    def _delete_schema(self):
        """Delete the current schema."""
        if not self.is_editing:
            return

        reply = QMessageBox.question(
            self, "Delete Schema",
            f"Are you sure you want to delete the schema '{self.current_schema.name}'?\n\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                self.schema_deleted.emit(self.current_schema.name)
                QMessageBox.information(self, "Schema Deleted",
                                        f"Schema '{self.current_schema.name}' deleted successfully.")
                self.accept()

            except Exception as e:
                QMessageBox.critical(self, "Delete Error", f"Failed to delete schema: {e}")

    def reject(self):
        """Handle dialog rejection."""
        if self.has_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to discard them?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                return

        super().reject()

    def get_schema(self) -> Optional[IndexSchema]:
        """Get the current schema."""
        return self.current_schema

    def closeEvent(self, event):
        """Handle dialog close event."""
        if self.has_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to save them before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )

            if reply == QMessageBox.Save:
                self._save_schema()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return

        event.accept()

