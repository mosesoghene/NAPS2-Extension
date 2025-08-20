"""
Validation display widget for showing validation results and errors.

Provides a comprehensive interface for displaying validation errors, warnings,
and suggestions with filtering, grouping, and action capabilities.
"""

import logging
from typing import Dict, List, Optional, Any
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QLabel, QComboBox, QLineEdit, QFrame, QGroupBox,
    QTextEdit, QSplitter, QTabWidget, QListWidget, QListWidgetItem,
    QHeaderView, QMessageBox, QProgressBar, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon, QColor, QFont, QPalette

from src.models.enums import ValidationSeverity, ConflictType
from src.core.signals import app_signals


class ValidationItemWidget(QWidget):
    """Widget for displaying individual validation items."""

    fix_requested = Signal(dict)  # validation_item
    ignore_requested = Signal(dict)  # validation_item

    def __init__(self, validation_item: Dict[str, Any], parent=None):
        super().__init__(parent)

        self.validation_item = validation_item
        self._setup_ui()

    def _setup_ui(self):
        """Set up the validation item UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)

        # Severity icon
        severity = self.validation_item.get('severity', 'error')
        icon_label = QLabel(self._get_severity_icon(severity))
        icon_label.setFixedSize(16, 16)
        layout.addWidget(icon_label)

        # Message
        message = self.validation_item.get('message', 'Unknown error')
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        layout.addWidget(message_label, 1)

        # Action buttons
        if self.validation_item.get('can_fix', False):
            fix_btn = QPushButton("Fix")
            fix_btn.setFixedSize(50, 20)
            fix_btn.clicked.connect(lambda: self.fix_requested.emit(self.validation_item))
            layout.addWidget(fix_btn)

        ignore_btn = QPushButton("Ignore")
        ignore_btn.setFixedSize(50, 20)
        ignore_btn.clicked.connect(lambda: self.ignore_requested.emit(self.validation_item))
        layout.addWidget(ignore_btn)

    def _get_severity_icon(self, severity: str) -> str:
        """Get icon text for severity level."""
        icons = {
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️',
            'critical': '🚫'
        }
        return icons.get(severity, '❓')


class ValidationSummaryWidget(QWidget):
    """Widget showing validation summary statistics."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.error_count = 0
        self.warning_count = 0
        self.info_count = 0

        self._setup_ui()

    def _setup_ui(self):
        """Set up the summary UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)

        # Overall status
        self.status_label = QLabel("No validation results")
        status_font = QFont()
        status_font.setBold(True)
        self.status_label.setFont(status_font)
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Counts
        self.error_label = QLabel("Errors: 0")
        self.error_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(self.error_label)

        self.warning_label = QLabel("Warnings: 0")
        self.warning_label.setStyleSheet("color: orange; font-weight: bold;")
        layout.addWidget(self.warning_label)

        self.info_label = QLabel("Info: 0")
        self.info_label.setStyleSheet("color: blue; font-weight: bold;")
        layout.addWidget(self.info_label)

    def update_summary(self, errors: int, warnings: int, info: int):
        """Update the validation summary."""
        self.error_count = errors
        self.warning_count = warnings
        self.info_count = info

        # Update labels
        self.error_label.setText(f"Errors: {errors}")
        self.warning_label.setText(f"Warnings: {warnings}")
        self.info_label.setText(f"Info: {info}")

        # Update overall status
        total_issues = errors + warnings + info
        if total_issues == 0:
            self.status_label.setText("✅ All validations passed")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        elif errors > 0:
            self.status_label.setText("❌ Validation failed")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
        else:
            self.status_label.setText("⚠️ Validation passed with warnings")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")


class ValidationFilterWidget(QWidget):
    """Widget for filtering validation results."""

    filter_changed = Signal(dict)  # filter_options

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the filter UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Severity filter
        layout.addWidget(QLabel("Severity:"))
        self.severity_combo = QComboBox()
        self.severity_combo.addItems(["All", "Critical", "Error", "Warning", "Info"])
        self.severity_combo.currentTextChanged.connect(self._emit_filter_changed)
        layout.addWidget(self.severity_combo)

        # Type filter
        layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["All", "Schema", "Assignment", "File", "Path"])
        self.type_combo.currentTextChanged.connect(self._emit_filter_changed)
        layout.addWidget(self.type_combo)

        # Search filter
        layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search messages...")
        self.search_edit.textChanged.connect(self._emit_filter_changed)
        layout.addWidget(self.search_edit)

        # Show fixed toggle
        self.show_fixed_check = QCheckBox("Show fixed")
        self.show_fixed_check.toggled.connect(self._emit_filter_changed)
        layout.addWidget(self.show_fixed_check)

        layout.addStretch()

        # Clear filters button
        clear_btn = QPushButton("Clear Filters")
        clear_btn.clicked.connect(self._clear_filters)
        layout.addWidget(clear_btn)

    def _emit_filter_changed(self):
        """Emit filter changed signal."""
        filters = {
            'severity': self.severity_combo.currentText(),
            'type': self.type_combo.currentText(),
            'search': self.search_edit.text(),
            'show_fixed': self.show_fixed_check.isChecked()
        }
        self.filter_changed.emit(filters)

    def _clear_filters(self):
        """Clear all filters."""
        self.severity_combo.setCurrentText("All")
        self.type_combo.setCurrentText("All")
        self.search_edit.clear()
        self.show_fixed_check.setChecked(False)


class ValidationDisplayWidget(QWidget):
    """Comprehensive validation results display widget."""

    # Signals
    validation_item_fixed = Signal(dict)  # validation_item
    validation_item_ignored = Signal(dict)  # validation_item
    fix_all_requested = Signal(str)  # fix_type
    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.validation_results: List[Dict[str, Any]] = []
        self.filtered_results: List[Dict[str, Any]] = []
        self.fixed_items: set = set()
        self.ignored_items: set = set()

        self._setup_ui()

    def _setup_ui(self):
        """Set up the validation display UI."""
        layout = QVBoxLayout(self)

        # Summary section
        self.summary_widget = ValidationSummaryWidget()
        layout.addWidget(self.summary_widget)

        # Filter section
        filter_frame = QFrame()
        filter_frame.setFrameStyle(QFrame.StyledPanel)
        filter_layout = QVBoxLayout(filter_frame)

        self.filter_widget = ValidationFilterWidget()
        self.filter_widget.filter_changed.connect(self._apply_filters)
        filter_layout.addWidget(self.filter_widget)

        layout.addWidget(filter_frame)

        # Main content area
        content_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(content_splitter, 1)

        # Validation tree
        tree_widget = self._create_tree_widget()
        content_splitter.addWidget(tree_widget)

        # Details panel
        details_widget = self._create_details_widget()
        content_splitter.addWidget(details_widget)

        # Set splitter sizes
        content_splitter.setSizes([400, 300])

        # Action buttons
        actions_widget = self._create_actions_widget()
        layout.addWidget(actions_widget)

    def _create_tree_widget(self) -> QWidget:
        """Create the validation tree widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header = QLabel("Validation Results")
        header.setFont(QFont("", 10, QFont.Bold))
        layout.addWidget(header)

        # Tree
        self.validation_tree = QTreeWidget()
        self.validation_tree.setHeaderLabels(["Issue", "Severity", "Type", "Status"])
        self.validation_tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.validation_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.validation_tree)

        return widget

    def _create_details_widget(self) -> QWidget:
        """Create the details panel widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Header
        header = QLabel("Details")
        header.setFont(QFont("", 10, QFont.Bold))
        layout.addWidget(header)

        # Details text
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(200)
        layout.addWidget(self.details_text)

        # Suggestions
        suggestions_label = QLabel("Suggestions")
        suggestions_label.setFont(QFont("", 9, QFont.Bold))
        layout.addWidget(suggestions_label)

        self.suggestions_list = QListWidget()
        self.suggestions_list.setMaximumHeight(100)
        layout.addWidget(self.suggestions_list)

        layout.addStretch()

        return widget

    def _create_actions_widget(self) -> QWidget:
        """Create action buttons widget."""
        widget = QFrame()
        widget.setFrameStyle(QFrame.StyledPanel)
        widget.setMaximumHeight(50)

        layout = QHBoxLayout(widget)

        # Batch actions
        self.fix_all_btn = QPushButton("Fix All Auto-Fixable")
        self.fix_all_btn.clicked.connect(lambda: self.fix_all_requested.emit("all"))
        layout.addWidget(self.fix_all_btn)

        self.ignore_all_warnings_btn = QPushButton("Ignore All Warnings")
        self.ignore_all_warnings_btn.clicked.connect(self._ignore_all_warnings)
        layout.addWidget(self.ignore_all_warnings_btn)

        layout.addStretch()

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(refresh_btn)

        # Export button
        export_btn = QPushButton("Export Report")
        export_btn.clicked.connect(self._export_report)
        layout.addWidget(export_btn)

        return widget

    def set_validation_results(self, results: List[Dict[str, Any]]):
        """Set validation results to display."""
        self.validation_results = results.copy()
        self._apply_filters()
        self._update_summary()

    def _apply_filters(self):
        """Apply current filters to validation results."""
        filters = {
            'severity': self.filter_widget.severity_combo.currentText(),
            'type': self.filter_widget.type_combo.currentText(),
            'search': self.filter_widget.search_edit.text().lower(),
            'show_fixed': self.filter_widget.show_fixed_check.isChecked()
        }

        self.filtered_results = []

        for item in self.validation_results:
            item_id = self._get_item_id(item)

            # Skip fixed/ignored items if not showing them
            if not filters['show_fixed']:
                if item_id in self.fixed_items or item_id in self.ignored_items:
                    continue

            # Apply severity filter
            if filters['severity'] != "All":
                if item.get('severity', '').title() != filters['severity']:
                    continue

            # Apply type filter
            if filters['type'] != "All":
                if filters['type'].lower() not in item.get('type', '').lower():
                    continue

            # Apply search filter
            if filters['search']:
                message = item.get('message', '').lower()
                if filters['search'] not in message:
                    continue

            self.filtered_results.append(item)

        self._populate_tree()

    def _populate_tree(self):
        """Populate the validation tree with filtered results."""
        self.validation_tree.clear()

        # Group by type
        groups = {}
        for item in self.filtered_results:
            item_type = item.get('type', 'Other')
            if item_type not in groups:
                groups[item_type] = []
            groups[item_type].append(item)

        # Create tree items
        for group_name, items in groups.items():
            group_item = QTreeWidgetItem([f"{group_name} ({len(items)})", "", "", ""])
            group_item.setFont(0, QFont("", -1, QFont.Bold))
            self.validation_tree.addTopLevelItem(group_item)

            for item in items:
                severity = item.get('severity', 'error')
                message = item.get('message', 'Unknown error')
                item_type = item.get('type', 'Other')

                # Determine status
                item_id = self._get_item_id(item)
                if item_id in self.fixed_items:
                    status = "Fixed"
                elif item_id in self.ignored_items:
                    status = "Ignored"
                else:
                    status = "Active"

                # Create tree item
                tree_item = QTreeWidgetItem([message, severity.title(), item_type, status])

                # Set colors based on severity
                color = self._get_severity_color(severity)
                tree_item.setForeground(1, color)

                # Store item data
                tree_item.setData(0, Qt.UserRole, item)

                group_item.addChild(tree_item)

        # Expand all groups
        self.validation_tree.expandAll()

    def _get_severity_color(self, severity: str) -> QColor:
        """Get color for severity level."""
        colors = {
            'critical': QColor(128, 0, 128),  # Purple
            'error': QColor(255, 0, 0),  # Red
            'warning': QColor(255, 165, 0),  # Orange
            'info': QColor(0, 0, 255)  # Blue
        }
        return colors.get(severity, QColor(0, 0, 0))

    def _get_item_id(self, item: Dict[str, Any]) -> str:
        """Generate unique ID for validation item."""
        return f"{item.get('type', '')}_{item.get('message', '')}_{item.get('field_name', '')}".replace(' ', '_')

    def _on_selection_changed(self):
        """Handle tree selection changes."""
        current_item = self.validation_tree.currentItem()

        if not current_item or not current_item.parent():
            # Group item selected or no selection
            self.details_text.clear()
            self.suggestions_list.clear()
            return

        # Get validation item data
        validation_item = current_item.data(0, Qt.UserRole)
        if not validation_item:
            return

        # Update details panel
        self._show_item_details(validation_item)

    def _show_item_details(self, item: Dict[str, Any]):
        """Show details for selected validation item."""
        # Build details text
        details = []
        details.append(f"<b>Type:</b> {item.get('type', 'Unknown')}")
        details.append(f"<b>Severity:</b> {item.get('severity', 'error').title()}")
        details.append(f"<b>Message:</b> {item.get('message', 'No message')}")

        if item.get('field_name'):
            details.append(f"<b>Field:</b> {item['field_name']}")

        if item.get('assignment_id'):
            details.append(f"<b>Assignment:</b> {item['assignment_id']}")

        if item.get('path'):
            details.append(f"<b>Path:</b> {item['path']}")

        self.details_text.setHtml("<br>".join(details))

        # Update suggestions
        self.suggestions_list.clear()
        suggestions = item.get('suggestions', [])
        for suggestion in suggestions:
            self.suggestions_list.addItem(suggestion)

    def _update_summary(self):
        """Update validation summary."""
        error_count = sum(1 for item in self.validation_results
                          if item.get('severity') == 'error')
        warning_count = sum(1 for item in self.validation_results
                            if item.get('severity') == 'warning')
        info_count = sum(1 for item in self.validation_results
                         if item.get('severity') == 'info')

        self.summary_widget.update_summary(error_count, warning_count, info_count)

        # Update action button states
        has_fixable = any(item.get('can_fix', False) for item in self.validation_results)
        self.fix_all_btn.setEnabled(has_fixable)

    def mark_item_fixed(self, item: Dict[str, Any]):
        """Mark validation item as fixed."""
        item_id = self._get_item_id(item)
        self.fixed_items.add(item_id)
        self.ignored_items.discard(item_id)  # Remove from ignored if present
        self._apply_filters()

    def mark_item_ignored(self, item: Dict[str, Any]):
        """Mark validation item as ignored."""
        item_id = self._get_item_id(item)
        self.ignored_items.add(item_id)
        self.fixed_items.discard(item_id)  # Remove from fixed if present
        self._apply_filters()

    def _ignore_all_warnings(self):
        """Ignore all warning-level validation items."""
        for item in self.validation_results:
            if item.get('severity') == 'warning':
                self.mark_item_ignored(item)

    def _export_report(self):
        """Export validation report to file."""
        try:
            from PySide6.QtWidgets import QFileDialog

            filename, _ = QFileDialog.getSaveFileName(
                self, "Export Validation Report",
                "validation_report.html",
                "HTML Files (*.html);;Text Files (*.txt)"
            )

            if filename:
                self._save_report(filename)
                QMessageBox.information(self, "Export Complete",
                                        f"Validation report saved to {filename}")

        except Exception as e:
            QMessageBox.warning(self, "Export Failed", f"Failed to export report: {e}")

    def _save_report(self, filename: str):
        """Save validation report to file."""
        is_html = filename.endswith('.html')

        with open(filename, 'w', encoding='utf-8') as f:
            if is_html:
                self._write_html_report(f)
            else:
                self._write_text_report(f)

    def _write_html_report(self, f):
        """Write HTML validation report."""
        f.write("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Validation Report</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .summary { background: #f5f5f5; padding: 15px; margin-bottom: 20px; }
                .error { color: red; }
                .warning { color: orange; }
                .info { color: blue; }
                .critical { color: purple; }
                table { width: 100%; border-collapse: collapse; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #f2f2f2; }
            </style>
        </head>
        <body>
        """)

        # Summary
        f.write(f"""
        <div class="summary">
            <h2>Validation Summary</h2>
            <p>Total Issues: {len(self.validation_results)}</p>
            <p class="error">Errors: {sum(1 for i in self.validation_results if i.get('severity') == 'error')}</p>
            <p class="warning">Warnings: {sum(1 for i in self.validation_results if i.get('severity') == 'warning')}</p>
            <p class="info">Info: {sum(1 for i in self.validation_results if i.get('severity') == 'info')}</p>
        </div>
        """)

        # Issues table
        f.write("""
        <h2>Issues</h2>
        <table>
            <tr><th>Severity</th><th>Type</th><th>Message</th><th>Details</th></tr>
        """)

        for item in self.validation_results:
            severity = item.get('severity', 'error')
            item_type = item.get('type', 'Unknown')
            message = item.get('message', 'No message')
            details = item.get('details', '')

            f.write(f"""
            <tr>
                <td class="{severity}">{severity.title()}</td>
                <td>{item_type}</td>
                <td>{message}</td>
                <td>{details}</td>
            </tr>
            """)

        f.write("</table></body></html>")

    def _write_text_report(self, f):
        """Write text validation report."""
        f.write("VALIDATION REPORT\n")
        f.write("=" * 50 + "\n\n")

        # Summary
        f.write("SUMMARY\n")
        f.write("-" * 20 + "\n")
        f.write(f"Total Issues: {len(self.validation_results)}\n")
        f.write(f"Errors: {sum(1 for i in self.validation_results if i.get('severity') == 'error')}\n")
        f.write(f"Warnings: {sum(1 for i in self.validation_results if i.get('severity') == 'warning')}\n")
        f.write(f"Info: {sum(1 for i in self.validation_results if i.get('severity') == 'info')}\n\n")

        # Issues
        f.write("ISSUES\n")
        f.write("-" * 20 + "\n")

        for i, item in enumerate(self.validation_results, 1):
            f.write(f"{i}. [{item.get('severity', 'error').upper()}] ")
            f.write(f"{item.get('type', 'Unknown')}: {item.get('message', 'No message')}\n")

            if item.get('details'):
                f.write(f"   Details: {item['details']}\n")

            f.write("\n")

    def clear_results(self):
        """Clear all validation results."""
        self.validation_results.clear()
        self.filtered_results.clear()
        self.fixed_items.clear()
        self.ignored_items.clear()

        self.validation_tree.clear()
        self.details_text.clear()
        self.suggestions_list.clear()

        self.summary_widget.update_summary(0, 0, 0)

    def get_active_issues_count(self) -> int:
        """Get count of active (unfixed, unignored) issues."""
        return len([item for item in self.validation_results
                    if self._get_item_id(item) not in self.fixed_items
                    and self._get_item_id(item) not in self.ignored_items])

    def has_critical_errors(self) -> bool:
        """Check if there are any critical or error level issues."""
        for item in self.validation_results:
            item_id = self._get_item_id(item)
            if item_id not in self.fixed_items and item_id not in self.ignored_items:
                severity = item.get('severity', 'error')
                if severity in ['critical', 'error']:
                    return True
        return False

    def get_validation_summary(self) -> Dict[str, Any]:
        """Get summary of validation state."""
        active_issues = [
            item for item in self.validation_results
            if self._get_item_id(item) not in self.fixed_items
               and self._get_item_id(item) not in self.ignored_items
        ]

        return {
            'total_issues': len(self.validation_results),
            'active_issues': len(active_issues),
            'fixed_issues': len(self.fixed_items),
            'ignored_issues': len(self.ignored_items),
            'critical_errors': sum(1 for i in active_issues if i.get('severity') == 'critical'),
            'errors': sum(1 for i in active_issues if i.get('severity') == 'error'),
            'warnings': sum(1 for i in active_issues if i.get('severity') == 'warning'),
            'info': sum(1 for i in active_issues if i.get('severity') == 'info'),
            'is_valid': not any(i.get('severity') in ['critical', 'error'] for i in active_issues)
        }