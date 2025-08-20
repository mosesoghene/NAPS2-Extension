"""
Preview panel showing the resulting folder structure and document organization.

Displays the output structure, statistics, conflicts, and validation issues
before export processing.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QSplitter, QFrame, QTextEdit, QTabWidget, QProgressBar,
    QMessageBox, QFileDialog, QMenu, QHeaderView
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread, Signal
from PySide6.QtGui import QFont, QColor, QPalette, QIcon, QPixmap

from src.models.batch import DocumentBatch
from src.models.assignment import PageAssignment
from src.models.schema import IndexSchema
from src.core.signals import app_signals


class PreviewUpdateThread(QThread):
    """Thread for updating preview data without blocking UI."""

    preview_updated = Signal(dict)  # preview_data
    update_error = Signal(str)  # error_message

    def __init__(self, batch: DocumentBatch, parent=None):
        super().__init__(parent)
        self.batch = batch

    def run(self):
        """Generate preview data in background thread."""
        try:
            preview_data = self._generate_preview_data()
            self.preview_updated.emit(preview_data)
        except Exception as e:
            logging.error(f"Preview generation failed: {e}")
            self.update_error.emit(str(e))

    def _generate_preview_data(self) -> Dict[str, Any]:
        """Generate comprehensive preview data."""
        if not self.batch:
            return {
                'folders': {},
                'files': [],
                'conflicts': [],
                'statistics': {
                    'total_assignments': 0,
                    'total_documents': 0,
                    'total_pages': 0,
                    'total_folders': 0,
                    'estimated_size': 0
                },
                'validation_issues': []
            }

        folders = {}
        files = []
        conflicts = []
        validation_issues = []
        total_size = 0

        # Process each assignment
        for assignment in self.batch.assignment_manager.assignments.values():
            try:
                # Generate document preview
                doc_preview = assignment.generate_document_preview()

                if not doc_preview:
                    continue

                folder_path = doc_preview.folder_path or "Root"

                # Initialize folder if needed
                if folder_path not in folders:
                    folders[folder_path] = {
                        'files': [],
                        'total_pages': 0,
                        'total_size': 0
                    }

                # File info
                file_info = {
                    'name': f"{doc_preview.filename}.pdf",
                    'full_path': str(doc_preview.get_full_path()),
                    'pages': doc_preview.page_count,
                    'size': doc_preview.estimated_file_size,
                    'assignment_id': assignment.assignment_id,
                    'schema_name': assignment.schema.name if assignment.schema else "Unknown"
                }

                # Add to folder
                folders[folder_path]['files'].append(file_info)
                folders[folder_path]['total_pages'] += doc_preview.page_count
                folders[folder_path]['total_size'] += doc_preview.estimated_file_size

                # Add to global file list
                files.append(file_info)
                total_size += doc_preview.estimated_file_size

                # Check for conflicts
                if doc_preview.conflicts:
                    conflicts.extend(doc_preview.conflicts)

                # Validate assignment
                if not assignment.validate_assignment():
                    validation_issues.append({
                        'assignment_id': assignment.assignment_id,
                        'issue': 'Assignment validation failed',
                        'severity': 'error'
                    })

            except Exception as e:
                validation_issues.append({
                    'assignment_id': assignment.assignment_id,
                    'issue': f'Preview generation failed: {e}',
                    'severity': 'error'
                })

        # Check for duplicate file paths
        path_counts = {}
        for file_info in files:
            path = file_info['full_path']
            if path in path_counts:
                path_counts[path] += 1
            else:
                path_counts[path] = 1

        for path, count in path_counts.items():
            if count > 1:
                conflicts.append({
                    'type': 'duplicate_path',
                    'description': f'Duplicate file path: {path}',
                    'severity': 'error',
                    'affected_files': [f for f in files if f['full_path'] == path]
                })

        return {
            'folders': folders,
            'files': files,
            'conflicts': conflicts,
            'statistics': {
                'total_assignments': len(self.batch.assignment_manager.assignments),
                'total_documents': len(files),
                'total_pages': sum(f['pages'] for f in files),
                'total_folders': len(folders),
                'estimated_size': total_size
            },
            'validation_issues': validation_issues
        }


class FolderTreeWidget(QTreeWidget):
    """Custom tree widget for folder structure display."""

    item_double_clicked = Signal(object)  # tree_item
    export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Setup tree
        self.setHeaderLabels(["Name", "Pages", "Size", "Type"])
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(True)

        # Configure columns
        header = self.header()
        header.setStretchLastSection(False)
        header.resizeSection(0, 300)  # Name column
        header.resizeSection(1, 80)  # Pages column
        header.resizeSection(2, 100)  # Size column
        header.resizeSection(3, 100)  # Type column

        # Enable context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Connect signals
        self.itemDoubleClicked.connect(self.item_double_clicked.emit)

    def _show_context_menu(self, position):
        """Show context menu for tree items."""
        item = self.itemAt(position)
        if not item:
            return

        menu = QMenu(self)

        # Item type specific actions
        item_type = item.data(3, Qt.DisplayRole)

        if item_type == "Folder":
            menu.addAction("Expand All").triggered.connect(self.expandAll)
            menu.addAction("Collapse All").triggered.connect(self.collapseAll)
        elif item_type == "File":
            menu.addAction("View Assignment Details").triggered.connect(
                lambda: self._view_assignment_details(item)
            )

        menu.addSeparator()

        # Export actions
        menu.addAction("Export All Documents").triggered.connect(
            self.export_requested.emit
        )

        menu.exec(self.mapToGlobal(position))

    def _view_assignment_details(self, item):
        """View details for assignment associated with file."""
        assignment_id = item.data(0, Qt.UserRole)
        if assignment_id:
            app_signals.assignment_details_requested.emit(assignment_id)


class ConflictListWidget(QListWidget):
    """Custom list widget for displaying conflicts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlternatingRowColors(True)

    def add_conflict(self, conflict: Dict[str, Any]):
        """Add a conflict to the list."""
        item = QListWidgetItem()

        # Set text and icon based on severity
        severity = conflict.get('severity', 'warning')
        description = conflict.get('description', 'Unknown conflict')

        item.setText(description)

        # Color coding by severity
        if severity == 'error':
            item.setForeground(QColor(200, 0, 0))
            item.setIcon(self._get_error_icon())
        elif severity == 'warning':
            item.setForeground(QColor(200, 100, 0))
            item.setIcon(self._get_warning_icon())
        else:
            item.setForeground(QColor(100, 100, 100))
            item.setIcon(self._get_info_icon())

        # Store conflict data
        item.setData(Qt.UserRole, conflict)

        self.addItem(item)

    def clear_conflicts(self):
        """Clear all conflicts."""
        self.clear()

    def _get_error_icon(self):
        """Get error icon."""
        # Would return actual icon in real implementation
        return QIcon()

    def _get_warning_icon(self):
        """Get warning icon."""
        # Would return actual icon in real implementation
        return QIcon()

    def _get_info_icon(self):
        """Get info icon."""
        # Would return actual icon in real implementation
        return QIcon()


class StatisticsWidget(QWidget):
    """Widget for displaying batch statistics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Statistics grid
        stats_frame = QFrame()
        stats_frame.setFrameStyle(QFrame.StyledPanel)
        stats_layout = QVBoxLayout(stats_frame)

        # Create statistics labels
        self.assignments_label = QLabel("Assignments: -")
        self.documents_label = QLabel("Documents: -")
        self.pages_label = QLabel("Pages: -")
        self.folders_label = QLabel("Folders: -")
        self.size_label = QLabel("Size: -")

        # Style labels
        font = QFont()
        font.setBold(True)

        for label in [self.assignments_label, self.documents_label,
                      self.pages_label, self.folders_label, self.size_label]:
            label.setFont(font)
            label.setAlignment(Qt.AlignCenter)
            stats_layout.addWidget(label)

        layout.addWidget(stats_frame)

    def update_statistics(self, stats: Dict[str, Any]):
        """Update statistics display."""
        self.assignments_label.setText(f"Assignments: {stats.get('total_assignments', 0)}")
        self.documents_label.setText(f"Documents: {stats.get('total_documents', 0)}")
        self.pages_label.setText(f"Pages: {stats.get('total_pages', 0)}")
        self.folders_label.setText(f"Folders: {stats.get('total_folders', 0)}")

        # Format size
        size_bytes = stats.get('estimated_size', 0)
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

        self.size_label.setText(f"Size: {size_str}")


class PreviewPanel(QWidget):
    """Shows the resulting folder structure and document organization."""

    # Signals
    export_requested = Signal()
    assignment_details_requested = Signal(str)  # assignment_id
    preview_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_batch = None
        self.preview_data = {}
        self.preview_thread = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Initialize the preview panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Toolbar
        toolbar_layout = QHBoxLayout()

        self.refresh_button = QPushButton("Refresh Preview")
        self.refresh_button.clicked.connect(self._refresh_preview)
        toolbar_layout.addWidget(self.refresh_button)

        toolbar_layout.addStretch()

        self.export_button = QPushButton("Export Documents")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_requested.emit)
        toolbar_layout.addWidget(self.export_button)

        layout.addLayout(toolbar_layout)

        # Main content with tabs
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Structure tab
        structure_tab = self._create_structure_tab()
        self.tab_widget.addTab(structure_tab, "Folder Structure")

        # Issues tab
        issues_tab = self._create_issues_tab()
        self.tab_widget.addTab(issues_tab, "Issues")

        # Statistics tab
        statistics_tab = self._create_statistics_tab()
        self.tab_widget.addTab(statistics_tab, "Statistics")

        # Status bar
        self.status_label = QLabel("No batch loaded")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: gray; font-style: italic; margin: 5px;")
        layout.addWidget(self.status_label)

    def _create_structure_tab(self) -> QWidget:
        """Create folder structure preview tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Controls
        controls_layout = QHBoxLayout()

        self.expand_all_button = QPushButton("Expand All")
        self.expand_all_button.clicked.connect(self._expand_all)
        controls_layout.addWidget(self.expand_all_button)

        self.collapse_all_button = QPushButton("Collapse All")
        self.collapse_all_button.clicked.connect(self._collapse_all)
        controls_layout.addWidget(self.collapse_all_button)

        controls_layout.addStretch()

        self.export_preview_button = QPushButton("Export Preview")
        self.export_preview_button.clicked.connect(self._export_preview)
        controls_layout.addWidget(self.export_preview_button)

        layout.addLayout(controls_layout)

        # Folder tree
        self.folder_tree = FolderTreeWidget()
        self.folder_tree.export_requested.connect(self.export_requested.emit)
        self.folder_tree.item_double_clicked.connect(self._on_tree_item_clicked)
        layout.addWidget(self.folder_tree)

        return widget

    def _create_issues_tab(self) -> QWidget:
        """Create issues and conflicts tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Conflicts section
        conflicts_group = QGroupBox("Conflicts")
        conflicts_layout = QVBoxLayout(conflicts_group)

        self.conflicts_list = ConflictListWidget()
        conflicts_layout.addWidget(self.conflicts_list)

        layout.addWidget(conflicts_group)

        # Validation issues section
        validation_group = QGroupBox("Validation Issues")
        validation_layout = QVBoxLayout(validation_group)

        self.validation_list = QListWidget()
        self.validation_list.setAlternatingRowColors(True)
        validation_layout.addWidget(self.validation_list)

        layout.addWidget(validation_group)

        return widget

    def _create_statistics_tab(self) -> QWidget:
        """Create statistics tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Statistics widget
        self.statistics_widget = StatisticsWidget()
        layout.addWidget(self.statistics_widget)

        # Detailed breakdown
        breakdown_group = QGroupBox("Detailed Breakdown")
        breakdown_layout = QVBoxLayout(breakdown_group)

        self.breakdown_text = QTextEdit()
        self.breakdown_text.setReadOnly(True)
        self.breakdown_text.setMaximumHeight(200)
        breakdown_layout.addWidget(self.breakdown_text)

        layout.addWidget(breakdown_group)

        layout.addStretch()
        return widget

    def _connect_signals(self):
        """Connect internal signals."""
        app_signals.batch_loaded.connect(self.update_preview)
        app_signals.assignment_created.connect(self._on_assignment_changed)
        app_signals.assignment_updated.connect(self._on_assignment_changed)
        app_signals.assignment_deleted.connect(self._on_assignment_changed)

    def update_preview(self, batch: Optional[DocumentBatch]):
        """Update preview with current batch."""
        self.current_batch = batch

        if not batch:
            self._clear_preview()
            self.status_label.setText("No batch loaded")
            self.export_button.setEnabled(False)
            return

        if len(batch.assignment_manager.assignments) == 0:
            self._clear_preview()
            self.status_label.setText("No assignments to preview")
            self.export_button.setEnabled(False)
            return

        self.status_label.setText("Generating preview...")
        self.export_button.setEnabled(False)

        # Start preview generation in background thread
        self._start_preview_generation()

    def _start_preview_generation(self):
        """Start preview generation in background thread."""
        if self.preview_thread and self.preview_thread.isRunning():
            return

        self.preview_thread = PreviewUpdateThread(self.current_batch)
        self.preview_thread.preview_updated.connect(self._on_preview_updated)
        self.preview_thread.update_error.connect(self._on_preview_error)
        self.preview_thread.start()

    def _on_preview_updated(self, preview_data: Dict[str, Any]):
        """Handle preview update completion."""
        self.preview_data = preview_data
        self._update_preview_display()

        assignments_count = preview_data['statistics']['total_assignments']
        documents_count = preview_data['statistics']['total_documents']

        if documents_count > 0:
            self.status_label.setText(f"Preview ready - {assignments_count} assignments, {documents_count} documents")
            self.export_button.setEnabled(True)
        else:
            self.status_label.setText("No valid assignments found")
            self.export_button.setEnabled(False)

        self.preview_updated.emit()

    def _on_preview_error(self, error_message: str):
        """Handle preview generation error."""
        self.status_label.setText(f"Preview error: {error_message}")
        self.export_button.setEnabled(False)

        QMessageBox.warning(
            self, "Preview Error",
            f"Failed to generate preview:\n{error_message}"
        )

    def _update_preview_display(self):
        """Update all preview display elements."""
        if not self.preview_data:
            return

        # Update folder tree
        self._update_folder_tree()

        # Update conflicts
        self._update_conflicts_display()

        # Update validation issues
        self._update_validation_display()

        # Update statistics
        self._update_statistics_display()

        # Update tab badges
        self._update_tab_badges()

    def _update_folder_tree(self):
        """Update the folder structure tree."""
        self.folder_tree.clear()

        if not self.preview_data or not self.preview_data['folders']:
            return

        # Create root items for each folder
        for folder_path, folder_info in self.preview_data['folders'].items():
            folder_item = QTreeWidgetItem([
                folder_path,
                str(folder_info['total_pages']),
                self._format_size(folder_info['total_size']),
                "Folder"
            ])

            # Style folder item
            font = folder_item.font(0)
            font.setBold(True)
            folder_item.setFont(0, font)

            # Add files to folder
            for file_info in folder_info['files']:
                file_item = QTreeWidgetItem([
                    file_info['name'],
                    str(file_info['pages']),
                    self._format_size(file_info['size']),
                    "File"
                ])

                # Store assignment ID for context menu
                file_item.setData(0, Qt.UserRole, file_info['assignment_id'])

                folder_item.addChild(file_item)

            self.folder_tree.addTopLevelItem(folder_item)

        # Expand all by default
        self.folder_tree.expandAll()

    def _update_conflicts_display(self):
        """Update conflicts display."""
        self.conflicts_list.clear_conflicts()

        if not self.preview_data:
            return

        for conflict in self.preview_data.get('conflicts', []):
            self.conflicts_list.add_conflict(conflict)

    def _update_validation_display(self):
        """Update validation issues display."""
        self.validation_list.clear()

        if not self.preview_data:
            return

        for issue in self.preview_data.get('validation_issues', []):
            item = QListWidgetItem()

            assignment_id = issue.get('assignment_id', 'Unknown')
            issue_text = issue.get('issue', 'Unknown issue')
            severity = issue.get('severity', 'warning')

            item.setText(f"Assignment {assignment_id}: {issue_text}")

            # Color by severity
            if severity == 'error':
                item.setForeground(QColor(200, 0, 0))
            elif severity == 'warning':
                item.setForeground(QColor(200, 100, 0))

            self.validation_list.addItem(item)

    def _update_statistics_display(self):
        """Update statistics display."""
        if not self.preview_data:
            return

        stats = self.preview_data['statistics']
        self.statistics_widget.update_statistics(stats)

        # Update detailed breakdown
        breakdown_text = "Detailed Breakdown:\n\n"

        for folder_path, folder_info in self.preview_data['folders'].items():
            breakdown_text += f"Folder: {folder_path}\n"
            breakdown_text += f"  Files: {len(folder_info['files'])}\n"
            breakdown_text += f"  Pages: {folder_info['total_pages']}\n"
            breakdown_text += f"  Size: {self._format_size(folder_info['total_size'])}\n\n"

        self.breakdown_text.setPlainText(breakdown_text)

    def _update_tab_badges(self):
        """Update tab badges with counts."""
        # Update issues tab with conflict/validation count
        conflicts_count = len(self.preview_data.get('conflicts', []))
        validation_count = len(self.preview_data.get('validation_issues', []))
        total_issues = conflicts_count + validation_count

        if total_issues > 0:
            self.tab_widget.setTabText(1, f"Issues ({total_issues})")
        else:
            self.tab_widget.setTabText(1, "Issues")

    def _clear_preview(self):
        """Clear all preview displays."""
        self.folder_tree.clear()
        self.conflicts_list.clear_conflicts()
        self.validation_list.clear()
        self.statistics_widget.update_statistics({})
        self.breakdown_text.clear()
        self.tab_widget.setTabText(1, "Issues")
        self.preview_data = {}

    def _format_size(self, size_bytes: int) -> str:
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _refresh_preview(self):
        """Refresh the preview display."""
        self.update_preview(self.current_batch)

    def _expand_all(self):
        """Expand all tree items."""
        self.folder_tree.expandAll()

    def _collapse_all(self):
        """Collapse all tree items."""
        self.folder_tree.collapseAll()

    def _export_preview(self):
        """Export preview to text file."""
        if not self.preview_data:
            QMessageBox.information(
                self, "No Preview Data",
                "No preview data available to export."
            )
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Preview",
            "document_preview.txt",
            "Text Files (*.txt);;All Files (*)"
        )

        if filename:
            try:
                self._write_preview_to_file(Path(filename))
                QMessageBox.information(
                    self, "Export Complete",
                    f"Preview exported to {filename}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Export Error",
                    f"Failed to export preview: {e}"
                )

    def _write_preview_to_file(self, file_path: Path):
        """Write preview data to text file."""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("Document Preview Report\n")
            f.write("=" * 50 + "\n\n")

            # Statistics
            stats = self.preview_data['statistics']
            f.write("Statistics:\n")
            f.write(f"  Assignments: {stats['total_assignments']}\n")
            f.write(f"  Documents: {stats['total_documents']}\n")
            f.write(f"  Pages: {stats['total_pages']}\n")
            f.write(f"  Folders: {stats['total_folders']}\n")
            f.write(f"  Estimated Size: {self._format_size(stats['estimated_size'])}\n\n")

            # Folder structure
            f.write("Folder Structure:\n")
            f.write("-" * 20 + "\n")

            for folder_path, folder_info in self.preview_data['folders'].items():
                f.write(f"\n{folder_path}/\n")
                for file_info in folder_info['files']:
                    f.write(
                        f"  - {file_info['name']} ({file_info['pages']} pages, {self._format_size(file_info['size'])})\n")

            # Conflicts
            if self.preview_data['conflicts']:
                f.write("\nConflicts:\n")
                f.write("-" * 20 + "\n")
                for conflict in self.preview_data['conflicts']:
                    f.write(f"  [{conflict['severity'].upper()}] {conflict['description']}\n")

            # Validation issues
            if self.preview_data['validation_issues']:
                f.write("\nValidation Issues:\n")
                f.write("-" * 20 + "\n")
                for issue in self.preview_data['validation_issues']:
                    f.write(f"  [{issue['severity'].upper()}] Assignment {issue['assignment_id']}: {issue['issue']}\n")

    def _on_tree_item_clicked(self, item):
        """Handle tree item double-click."""
        item_type = item.data(3, Qt.DisplayRole)

        if item_type == "File":
            assignment_id = item.data(0, Qt.UserRole)
            if assignment_id:
                self.assignment_details_requested.emit(assignment_id)

    def _on_assignment_changed(self, assignment):
        """Handle assignment changes."""
        # Refresh preview when assignments change
        QTimer.singleShot(100, self._refresh_preview)

    # Public interface
    def get_preview_data(self) -> Dict[str, Any]:
        """Get current preview data."""
        return self.preview_data.copy()

    def has_conflicts(self) -> bool:
        """Check if there are any conflicts."""
        return len(self.preview_data.get('conflicts', [])) > 0

    def has_validation_issues(self) -> bool:
        """Check if there are validation issues."""
        return len(self.preview_data.get('validation_issues', [])) > 0

    def get_conflicts(self) -> List[Dict[str, Any]]:
        """Get list of conflicts."""
        return self.preview_data.get('conflicts', [])

    def get_validation_issues(self) -> List[Dict[str, Any]]:
        """Get list of validation issues."""
        return self.preview_data.get('validation_issues', [])