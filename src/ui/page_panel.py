"""
Page panel for displaying scanned pages as thumbnails with selection capabilities.

Provides thumbnail grid view with multi-selection, drag selection, assignment indicators,
and page management functionality.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QPushButton, QComboBox, QSlider, QGroupBox, QMenu,
    QMessageBox, QProgressBar, QToolBar, QSizePolicy,
    QFrame, QApplication
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QThread, QMutex, QMutexLocker, QPoint, QRect,
    QPropertyAnimation, QEasingCurve, Signal
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPixmap, QMouseEvent, QPaintEvent,
    QResizeEvent, QContextMenuEvent, QDragEnterEvent, QDropEvent
)

from src.models.batch import DocumentBatch
from src.models.assignment import PageReference, PageAssignment
from src.ui.widgets.page_thumbnail import PageThumbnailWidget
from src.utils.selection_manager import PageSelectionManager
from src.core.signals import app_signals


class ThumbnailGridWidget(QWidget):
    """Custom widget for thumbnail grid with drag selection support."""

    selection_changed = Signal(list)  # List[PageReference]
    drag_selection_started = Signal(QPoint)
    drag_selection_updated = Signal(QRect)
    drag_selection_finished = Signal(QRect)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.thumbnails = {}  # {page_id: PageThumbnailWidget}
        self.grid_columns = 6
        self.thumbnail_size = 150
        self.spacing = 10
        self.selection_manager = PageSelectionManager()

        # Drag selection state
        self.drag_selecting = False
        self.drag_start_point = QPoint()
        self.drag_current_rect = QRect()

        # Layout
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(self.spacing)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        # Enable mouse tracking for drag selection
        self.setMouseTracking(True)

        # Connect selection manager signals
        self.selection_manager.selection_changed.connect(self.selection_changed.emit)
        self.selection_manager.selection_changed.connect(self._update_thumbnail_selection)

    def add_thumbnail(self, page_ref: PageReference, thumbnail_widget: PageThumbnailWidget):
        """Add a thumbnail widget to the grid."""
        page_id = page_ref.get_unique_id()
        self.thumbnails[page_id] = thumbnail_widget

        # Calculate grid position
        index = len(self.thumbnails) - 1
        row = index // self.grid_columns
        col = index % self.grid_columns

        # Add to layout
        self.grid_layout.addWidget(thumbnail_widget, row, col)

        # Connect thumbnail signals
        thumbnail_widget.clicked.connect(
            lambda: self._handle_thumbnail_click(page_ref, QApplication.keyboardModifiers())
        )
        thumbnail_widget.right_clicked.connect(
            lambda pos: self._handle_thumbnail_context_menu(page_ref, pos)
        )

    def remove_thumbnail(self, page_id: str):
        """Remove a thumbnail from the grid."""
        if page_id in self.thumbnails:
            widget = self.thumbnails[page_id]
            self.grid_layout.removeWidget(widget)
            widget.deleteLater()
            del self.thumbnails[page_id]
            self._relayout_thumbnails()

    def clear_thumbnails(self):
        """Remove all thumbnails."""
        for widget in self.thumbnails.values():
            self.grid_layout.removeWidget(widget)
            widget.deleteLater()
        self.thumbnails.clear()
        self.selection_manager.clear_selection()

    def set_thumbnail_size(self, size: int):
        """Update thumbnail size and relayout."""
        self.thumbnail_size = size
        for widget in self.thumbnails.values():
            widget.set_thumbnail_size(size)
        self._relayout_thumbnails()

    def set_columns(self, columns: int):
        """Update number of columns and relayout."""
        self.grid_columns = max(1, columns)
        self._relayout_thumbnails()

    def _relayout_thumbnails(self):
        """Relayout all thumbnails after changes."""
        # Remove all widgets from layout
        for widget in self.thumbnails.values():
            self.grid_layout.removeWidget(widget)

        # Re-add in new layout
        for i, (page_id, widget) in enumerate(self.thumbnails.items()):
            row = i // self.grid_columns
            col = i % self.grid_columns
            self.grid_layout.addWidget(widget, row, col)

    def _handle_thumbnail_click(self, page_ref: PageReference, modifiers):
        """Handle thumbnail click with modifier support."""
        page_id = page_ref.get_unique_id()

        if modifiers & Qt.ControlModifier:
            # Toggle selection
            self.selection_manager.toggle_page_selection(page_id)
        elif modifiers & Qt.ShiftModifier:
            # Range selection
            self.selection_manager.select_range_to(page_id)
        else:
            # Single selection
            self.selection_manager.select_single_page(page_id)

    def _handle_thumbnail_context_menu(self, page_ref: PageReference, pos: QPoint):
        """Handle thumbnail context menu."""
        page_id = page_ref.get_unique_id()

        # Ensure the right-clicked thumbnail is selected
        if not self.selection_manager.is_page_selected(page_id):
            self.selection_manager.select_single_page(page_id)

        # Create context menu
        menu = QMenu(self)

        # Rotate actions
        rotate_menu = menu.addMenu("Rotate")
        rotate_menu.addAction("Rotate 90° CW").triggered.connect(
            lambda: self._rotate_selected_pages(90)
        )
        rotate_menu.addAction("Rotate 90° CCW").triggered.connect(
            lambda: self._rotate_selected_pages(-90)
        )
        rotate_menu.addAction("Rotate 180°").triggered.connect(
            lambda: self._rotate_selected_pages(180)
        )

        menu.addSeparator()

        # Assignment actions
        selected_count = self.selection_manager.get_selection_count()
        if selected_count > 0:
            menu.addAction(f"Create Assignment ({selected_count} pages)").triggered.connect(
                self._create_assignment_from_selection
            )

        # Delete action
        menu.addSeparator()
        menu.addAction("Delete Selected Pages").triggered.connect(
            self._delete_selected_pages
        )

        # Show menu
        menu.exec(self.mapToGlobal(pos))

    def _rotate_selected_pages(self, degrees: int):
        """Rotate selected page thumbnails."""
        selected_pages = self.selection_manager.get_selected_pages()
        for page_id in selected_pages:
            if page_id in self.thumbnails:
                self.thumbnails[page_id].rotate_thumbnail(degrees)

    def _create_assignment_from_selection(self):
        """Create assignment from selected pages."""
        selected_pages = self.selection_manager.get_selected_pages()
        if selected_pages:
            app_signals.assignment_creation_requested.emit(selected_pages)

    def _delete_selected_pages(self):
        """Delete selected pages after confirmation."""
        selected_count = self.selection_manager.get_selection_count()
        if selected_count == 0:
            return

        reply = QMessageBox.question(
            self, "Delete Pages",
            f"Are you sure you want to delete {selected_count} selected pages?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            selected_pages = self.selection_manager.get_selected_pages()
            app_signals.pages_deletion_requested.emit(selected_pages)

    def _update_thumbnail_selection(self, selected_pages: List[str]):
        """Update visual selection state of thumbnails."""
        for page_id, widget in self.thumbnails.items():
            is_selected = page_id in selected_pages
            widget.set_selected(is_selected)

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for drag selection."""
        if event.button() == Qt.LeftButton:
            self.drag_selecting = True
            self.drag_start_point = event.pos()
            self.drag_current_rect = QRect(self.drag_start_point, self.drag_start_point)
            self.drag_selection_started.emit(self.drag_start_point)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for drag selection."""
        if self.drag_selecting and event.buttons() & Qt.LeftButton:
            self.drag_current_rect = QRect(self.drag_start_point, event.pos()).normalized()
            self.drag_selection_updated.emit(self.drag_current_rect)
            self.update()  # Trigger repaint for selection rectangle

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release for drag selection."""
        if self.drag_selecting and event.button() == Qt.LeftButton:
            self.drag_selecting = False

            # Find thumbnails intersecting with drag rectangle
            intersecting_pages = []
            for page_id, widget in self.thumbnails.items():
                widget_rect = widget.geometry()
                if self.drag_current_rect.intersects(widget_rect):
                    intersecting_pages.append(page_id)

            # Update selection
            if intersecting_pages:
                modifiers = QApplication.keyboardModifiers()
                if modifiers & Qt.ControlModifier:
                    # Add to selection
                    self.selection_manager.add_to_selection(intersecting_pages)
                elif modifiers & Qt.ShiftModifier:
                    # Toggle selection
                    for page_id in intersecting_pages:
                        self.selection_manager.toggle_page_selection(page_id)
                else:
                    # Replace selection
                    self.selection_manager.set_selected_pages(intersecting_pages)

            self.drag_selection_finished.emit(self.drag_current_rect)
            self.drag_current_rect = QRect()
            self.update()

        super().mouseReleaseEvent(event)

    def paintEvent(self, event: QPaintEvent):
        """Paint drag selection rectangle."""
        super().paintEvent(event)

        if self.drag_selecting and not self.drag_current_rect.isEmpty():
            painter = QPainter(self)
            painter.setPen(QPen(QColor(0, 120, 215), 2))
            painter.setBrush(QBrush(QColor(0, 120, 215, 50)))
            painter.drawRect(self.drag_current_rect)

    def select_all(self):
        """Select all thumbnails."""
        all_page_ids = list(self.thumbnails.keys())
        self.selection_manager.set_selected_pages(all_page_ids)

    def clear_selection(self):
        """Clear all selections."""
        self.selection_manager.clear_selection()

    def get_selected_page_references(self) -> List[PageReference]:
        """Get PageReference objects for selected pages."""
        # This would need to be implemented with access to the batch
        # For now, return empty list
        return []


class PagePanel(QWidget):
    """Panel for displaying scanned pages as thumbnails with selection capabilities."""

    # Signals
    pages_selected = Signal(list)  # List[PageReference]
    page_assignment_requested = Signal(list)  # List[PageReference]

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_batch = None
        self.thumbnail_widgets = {}  # {page_id: PageThumbnailWidget}
        self.assignment_indicators = {}  # {assignment_id: color}

        # UI state
        self.zoom_level = 1.0
        self.base_thumbnail_size = 150
        self.columns_per_row = 6

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Initialize the page panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Toolbar
        self.toolbar = self._create_toolbar()
        layout.addWidget(self.toolbar)

        # Main content area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Thumbnail grid widget
        self.thumbnail_grid = ThumbnailGridWidget()
        self.scroll_area.setWidget(self.thumbnail_grid)

        layout.addWidget(self.scroll_area)

        # Status bar
        self.status_bar = self._create_status_bar()
        layout.addWidget(self.status_bar)

    def _create_toolbar(self) -> QToolBar:
        """Create the page panel toolbar."""
        toolbar = QToolBar()
        toolbar.setMovable(False)

        # View options
        toolbar.addWidget(QLabel("View:"))

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(50, 300)  # 50% to 300%
        self.zoom_slider.setValue(100)
        self.zoom_slider.setMaximumWidth(100)
        self.zoom_slider.setToolTip("Zoom level")
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        toolbar.addWidget(self.zoom_slider)

        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(40)
        toolbar.addWidget(self.zoom_label)

        toolbar.addSeparator()

        # Columns selector
        toolbar.addWidget(QLabel("Columns:"))
        self.columns_combo = QComboBox()
        self.columns_combo.addItems(["2", "3", "4", "5", "6", "8", "10"])
        self.columns_combo.setCurrentText("6")
        self.columns_combo.currentTextChanged.connect(self._on_columns_changed)
        toolbar.addWidget(self.columns_combo)

        toolbar.addSeparator()

        # Selection tools
        select_all_action = QAction("Select All", self)
        select_all_action.setShortcut("Ctrl+A")
        select_all_action.triggered.connect(self.select_all_pages)
        toolbar.addAction(select_all_action)

        clear_selection_action = QAction("Clear Selection", self)
        clear_selection_action.setShortcut("Escape")
        clear_selection_action.triggered.connect(self.clear_selection)
        toolbar.addAction(clear_selection_action)

        toolbar.addSeparator()

        # Assignment indicator toggle
        self.show_indicators_action = QAction("Show Assignments", self)
        self.show_indicators_action.setCheckable(True)
        self.show_indicators_action.setChecked(True)
        self.show_indicators_action.triggered.connect(self._toggle_assignment_indicators)
        toolbar.addAction(self.show_indicators_action)

        return toolbar

    def _create_status_bar(self) -> QWidget:
        """Create the status bar widget."""
        status_widget = QFrame()
        status_widget.setFrameStyle(QFrame.StyledPanel)
        status_widget.setMaximumHeight(30)

        layout = QHBoxLayout(status_widget)
        layout.setContentsMargins(5, 2, 5, 2)

        # Page count
        self.page_count_label = QLabel("No pages loaded")
        layout.addWidget(self.page_count_label)

        layout.addStretch()

        # Selection info
        self.selection_label = QLabel("No selection")
        layout.addWidget(self.selection_label)

        layout.addStretch()

        # Processing progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(150)
        layout.addWidget(self.progress_bar)

        return status_widget

    def _connect_signals(self):
        """Connect internal signals."""
        self.thumbnail_grid.selection_changed.connect(self._on_selection_changed)

        # Application signals
        app_signals.batch_loaded.connect(self.load_batch)
        app_signals.assignment_created.connect(self._on_assignment_created)
        app_signals.assignment_updated.connect(self._on_assignment_updated)
        app_signals.thumbnail_generated.connect(self._on_thumbnail_generated)

    def load_batch(self, batch: DocumentBatch):
        """Load a document batch and display thumbnails."""
        self.current_batch = batch
        self._clear_thumbnails()

        if not batch:
            self.page_count_label.setText("No pages loaded")
            return

        # Update page count
        total_pages = batch.total_pages
        file_count = len(batch.scanned_files)
        self.page_count_label.setText(f"{total_pages} pages in {file_count} files")

        # Generate thumbnails for all pages
        self._generate_thumbnails()

    def _clear_thumbnails(self):
        """Clear all thumbnails from display."""
        self.thumbnail_grid.clear_thumbnails()
        self.thumbnail_widgets.clear()
        self.assignment_indicators.clear()
        self.selection_label.setText("No selection")

    def _generate_thumbnails(self):
        """Generate thumbnails for all pages in current batch."""
        if not self.current_batch:
            return

        total_pages = self.current_batch.total_pages
        if total_pages == 0:
            return

        # Show progress
        self.progress_bar.setMaximum(total_pages)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        # Generate thumbnails for each page
        page_index = 0
        for scanned_file in self.current_batch.scanned_files:
            for page_number in range(1, scanned_file.page_count + 1):
                page_ref = PageReference(scanned_file.file_id, page_number)
                self._create_thumbnail_widget(page_ref, scanned_file.file_path, page_number)
                page_index += 1
                self.progress_bar.setValue(page_index)

        # Hide progress
        QTimer.singleShot(500, lambda: self.progress_bar.setVisible(False))

    def _create_thumbnail_widget(self, page_ref: PageReference, file_path: Path, page_number: int):
        """Create a thumbnail widget for a page."""
        try:
            # Create thumbnail widget
            thumbnail_widget = PageThumbnailWidget(page_ref, self)

            # Set thumbnail size
            current_size = int(self.base_thumbnail_size * self.zoom_level)
            thumbnail_widget.set_thumbnail_size(current_size)

            # Load thumbnail (this might be async)
            thumbnail_widget.load_thumbnail(file_path, page_number)

            # Add to grid
            self.thumbnail_grid.add_thumbnail(page_ref, thumbnail_widget)

            # Store reference
            page_id = page_ref.get_unique_id()
            self.thumbnail_widgets[page_id] = thumbnail_widget

        except Exception as e:
            logging.error(f"Failed to create thumbnail for {file_path} page {page_number}: {e}")

    def _on_thumbnail_generated(self, page_id: str, thumbnail_path: Path):
        """Handle thumbnail generation completion."""
        if page_id in self.thumbnail_widgets:
            widget = self.thumbnail_widgets[page_id]
            widget.update_thumbnail_image(thumbnail_path)

    def _on_selection_changed(self, selected_page_ids: List[str]):
        """Handle selection changes."""
        count = len(selected_page_ids)

        if count == 0:
            self.selection_label.setText("No selection")
        elif count == 1:
            self.selection_label.setText("1 page selected")
        else:
            self.selection_label.setText(f"{count} pages selected")

        # Convert to PageReference objects and emit
        selected_refs = []
        for page_id in selected_page_ids:
            # Parse page_id back to PageReference
            # This assumes page_id format is "file_id-page_number"
            if '-' in page_id:
                file_id, page_num = page_id.rsplit('-', 1)
                try:
                    page_ref = PageReference(file_id, int(page_num))
                    selected_refs.append(page_ref)
                except ValueError:
                    logging.warning(f"Invalid page ID format: {page_id}")

        self.pages_selected.emit(selected_refs)

    def _on_assignment_created(self, assignment: PageAssignment):
        """Handle new assignment creation."""
        self._update_assignment_indicators()

    def _on_assignment_updated(self, assignment: PageAssignment):
        """Handle assignment updates."""
        self._update_assignment_indicators()

    def _update_assignment_indicators(self):
        """Update assignment indicators on thumbnails."""
        if not self.current_batch or not self.show_indicators_action.isChecked():
            return

        # Clear existing indicators
        for widget in self.thumbnail_widgets.values():
            widget.clear_assignment_indicator()

        # Add indicators for current assignments
        assignment_colors = [
            QColor(255, 0, 0),  # Red
            QColor(0, 255, 0),  # Green
            QColor(0, 0, 255),  # Blue
            QColor(255, 255, 0),  # Yellow
            QColor(255, 0, 255),  # Magenta
            QColor(0, 255, 255),  # Cyan
        ]

        color_index = 0
        for assignment in self.current_batch.assignment_manager.assignments.values():
            color = assignment_colors[color_index % len(assignment_colors)]

            for page_ref in assignment.page_references:
                page_id = page_ref.get_unique_id()
                if page_id in self.thumbnail_widgets:
                    widget = self.thumbnail_widgets[page_id]
                    widget.set_assignment_indicator(assignment.assignment_id, color)

            color_index += 1

    def _toggle_assignment_indicators(self, show: bool):
        """Toggle assignment indicator visibility."""
        if show:
            self._update_assignment_indicators()
        else:
            for widget in self.thumbnail_widgets.values():
                widget.clear_assignment_indicator()

    def _on_zoom_changed(self, value: int):
        """Handle zoom slider changes."""
        self.zoom_level = value / 100.0
        self.zoom_label.setText(f"{value}%")

        # Update thumbnail sizes
        new_size = int(self.base_thumbnail_size * self.zoom_level)
        self.thumbnail_grid.set_thumbnail_size(new_size)

    def _on_columns_changed(self, columns_text: str):
        """Handle column count changes."""
        try:
            columns = int(columns_text)
            self.columns_per_row = columns
            self.thumbnail_grid.set_columns(columns)
        except ValueError:
            logging.warning(f"Invalid column count: {columns_text}")

    # Public interface methods
    def zoom_in(self):
        """Increase zoom level."""
        current_value = self.zoom_slider.value()
        new_value = min(current_value + 25, self.zoom_slider.maximum())
        self.zoom_slider.setValue(new_value)

    def zoom_out(self):
        """Decrease zoom level."""
        current_value = self.zoom_slider.value()
        new_value = max(current_value - 25, self.zoom_slider.minimum())
        self.zoom_slider.setValue(new_value)

    def reset_zoom(self):
        """Reset zoom to 100%."""
        self.zoom_slider.setValue(100)

    def select_all_pages(self):
        """Select all page thumbnails."""
        self.thumbnail_grid.select_all()

    def clear_selection(self):
        """Clear page selection."""
        self.thumbnail_grid.clear_selection()

    def get_selected_pages(self) -> List[PageReference]:
        """Get currently selected page references."""
        return self.thumbnail_grid.get_selected_page_references()

    def show_assignment_indicators(self):
        """Show assignment indicators."""
        self.show_indicators_action.setChecked(True)
        self._update_assignment_indicators()

    def hide_assignment_indicators(self):
        """Hide assignment indicators."""
        self.show_indicators_action.setChecked(False)
        self._toggle_assignment_indicators(False)

    def rotate_selected_pages(self, degrees: int):
        """Rotate selected pages."""
        # This would trigger rotation in the actual file processing
        selected_refs = self.get_selected_pages()
        if selected_refs:
            app_signals.page_rotation_requested.emit(selected_refs, degrees)

    def delete_selected_pages(self):
        """Delete selected pages."""
        selected_refs = self.get_selected_pages()
        if selected_refs:
            reply = QMessageBox.question(
                self, "Delete Pages",
                f"Are you sure you want to delete {len(selected_refs)} selected pages?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                app_signals.pages_deletion_requested.emit(selected_refs)