"""
Thumbnail widget for displaying PDF page previews.

Provides thumbnail display with selection states, assignment indicators,
loading states, and interactive features like hover effects and tooltips.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QGraphicsDropShadowEffect, QToolTip
)
from PySide6.QtCore import Qt, Signal, QSize, QRect, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QFont, QFontMetrics, QMouseEvent, QPainterPath

from src.models.assignment import PageReference
from src.models.enums import ThumbnailSize
from src.core.signals import app_signals


class PageThumbnailWidget(QWidget):
    """Widget for displaying PDF page thumbnails with selection and assignment states."""

    # Signals
    thumbnail_clicked = Signal(object, Qt.KeyboardModifiers)  # PageReference, modifiers
    thumbnail_double_clicked = Signal(object)  # PageReference
    thumbnail_context_menu = Signal(object, object)  # PageReference, QPoint
    selection_changed = Signal(object, bool)  # PageReference, selected

    def __init__(self, page_reference: PageReference, thumbnail_size: ThumbnailSize = ThumbnailSize.MEDIUM,
                 parent=None):
        super().__init__(parent)

        self.page_reference = page_reference
        self.thumbnail_size = thumbnail_size
        self.thumbnail_pixmap: Optional[QPixmap] = None

        # States
        self.is_selected = False
        self.is_assigned = False
        self.is_loading = True
        self.is_hovered = False
        self.assignment_id: Optional[str] = None
        self.assignment_color = QColor(100, 150, 255)

        # UI settings
        self.border_width = 2
        self.selection_color = QColor(0, 120, 215)
        self.assignment_indicator_color = QColor(255, 165, 0)
        self.loading_color = QColor(200, 200, 200)
        self.hover_color = QColor(240, 240, 240)

        # Animation
        self.hover_animation = QPropertyAnimation(self, b"geometry")
        self.hover_animation.setDuration(150)
        self.hover_animation.setEasingCurve(QEasingCurve.OutQuad)

        # Setup UI
        self._setup_ui()
        self._setup_style()

        # Request thumbnail generation
        self._request_thumbnail()

        logging.debug(f"Created thumbnail widget for {page_reference}")

    def _setup_ui(self):
        """Set up the widget UI."""
        self.setFixedSize(
            self.thumbnail_size.width + 20,  # Add padding
            self.thumbnail_size.height + 40  # Add padding + label space
        )

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)

        # Set up layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        # Thumbnail display area
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setFixedSize(self.thumbnail_size.width, self.thumbnail_size.height)
        self.thumbnail_label.setStyleSheet("""
            QLabel {
                border: 2px solid #ccc;
                background-color: white;
            }
        """)
        layout.addWidget(self.thumbnail_label, 0, Qt.AlignCenter)

        # Page number label
        self.page_label = QLabel(f"Page {self.page_reference.page_number}")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setStyleSheet("font-size: 10px; color: #666;")
        layout.addWidget(self.page_label)

        # Assignment indicator (initially hidden)
        self.assignment_indicator = QLabel()
        self.assignment_indicator.setFixedHeight(3)
        self.assignment_indicator.hide()
        layout.addWidget(self.assignment_indicator)

        # Set loading state
        self._set_loading_state()

    def _setup_style(self):
        """Set up widget styling."""
        self.setStyleSheet("""
            PageThumbnailWidget {
                border-radius: 5px;
            }
        """)

        # Add subtle shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(5)
        shadow.setColor(QColor(0, 0, 0, 30))
        shadow.setOffset(1, 1)
        self.setGraphicsEffect(shadow)

    def _request_thumbnail(self):
        """Request thumbnail generation."""
        # This would typically connect to the thumbnail generator
        # For now, we'll simulate loading
        QTimer.singleShot(1000, self._simulate_thumbnail_loaded)

    def _simulate_thumbnail_loaded(self):
        """Simulate thumbnail loading completion."""
        # Create a placeholder pixmap
        pixmap = QPixmap(self.thumbnail_size.width, self.thumbnail_size.height)
        pixmap.fill(QColor(245, 245, 245))

        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor(150, 150, 150), 1))
        painter.drawRect(0, 0, pixmap.width() - 1, pixmap.height() - 1)

        # Draw page content placeholder
        painter.setPen(QColor(100, 100, 100))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, f"Page\n{self.page_reference.page_number}")
        painter.end()

        self.set_thumbnail(pixmap)

    def _set_loading_state(self):
        """Set widget to loading state."""
        self.is_loading = True

        # Create loading placeholder
        loading_pixmap = QPixmap(self.thumbnail_size.width, self.thumbnail_size.height)
        loading_pixmap.fill(self.loading_color)

        painter = QPainter(loading_pixmap)
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(loading_pixmap.rect(), Qt.AlignCenter, "Loading...")
        painter.end()

        self.thumbnail_label.setPixmap(loading_pixmap)
        self._update_visual_state()

    def set_thumbnail(self, pixmap: QPixmap):
        """Set the thumbnail pixmap."""
        if pixmap and not pixmap.isNull():
            # Scale pixmap to fit thumbnail size while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                self.thumbnail_size.size_tuple,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            self.thumbnail_pixmap = scaled_pixmap
            self.thumbnail_label.setPixmap(scaled_pixmap)
            self.is_loading = False
            self._update_visual_state()

            logging.debug(f"Set thumbnail for page {self.page_reference.page_number}")

    def set_selected(self, selected: bool):
        """Set selection state."""
        if self.is_selected != selected:
            self.is_selected = selected
            self._update_visual_state()
            self.selection_changed.emit(self.page_reference, selected)

    def set_assigned(self, assigned: bool, assignment_id: str = None):
        """Set assignment state."""
        self.is_assigned = assigned
        self.assignment_id = assignment_id

        if assigned:
            self.assignment_indicator.show()
            self.assignment_indicator.setStyleSheet(f"""
                background-color: {self.assignment_indicator_color.name()};
                border-radius: 1px;
            """)
        else:
            self.assignment_indicator.hide()
            self.assignment_id = None

        self._update_visual_state()

    def set_assignment_color(self, color: QColor):
        """Set custom assignment indicator color."""
        self.assignment_color = color
        if self.is_assigned:
            self.assignment_indicator.setStyleSheet(f"""
                background-color: {color.name()};
                border-radius: 1px;
            """)

    def _update_visual_state(self):
        """Update widget visual state based on current flags."""
        # Determine border color and width
        border_color = "#ccc"
        border_width = 2

        if self.is_selected:
            border_color = self.selection_color.name()
            border_width = 3
        elif self.is_assigned:
            border_color = self.assignment_indicator_color.name()
            border_width = 2
        elif self.is_hovered:
            border_color = self.hover_color.darker(120).name()
            border_width = 2

        # Update thumbnail label style
        style = f"""
            QLabel {{
                border: {border_width}px solid {border_color};
                background-color: white;
                border-radius: 3px;
            }}
        """
        self.thumbnail_label.setStyleSheet(style)

        # Update widget background
        bg_color = "transparent"
        if self.is_selected:
            bg_color = self.selection_color.name() + "20"  # 20% opacity
        elif self.is_hovered:
            bg_color = self.hover_color.name()

        self.setStyleSheet(f"""
            PageThumbnailWidget {{
                background-color: {bg_color};
                border-radius: 5px;
            }}
        """)

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events."""
        if event.button() == Qt.LeftButton:
            modifiers = event.modifiers()
            self.thumbnail_clicked.emit(self.page_reference, modifiers)

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double click events."""
        if event.button() == Qt.LeftButton:
            self.thumbnail_double_clicked.emit(self.page_reference)

        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        """Handle context menu events."""
        self.thumbnail_context_menu.emit(self.page_reference, event.globalPos())

    def enterEvent(self, event):
        """Handle mouse enter events."""
        self.is_hovered = True
        self._update_visual_state()

        # Show tooltip with page information
        tooltip_text = self._get_tooltip_text()
        if tooltip_text:
            QToolTip.showText(self.mapToGlobal(QRect(0, 0, 1, 1).center()), tooltip_text, self)

        super().enterEvent(event)

    def leaveEvent(self, event):
        """Handle mouse leave events."""
        self.is_hovered = False
        self._update_visual_state()
        QToolTip.hideText()

        super().leaveEvent(event)

    def _get_tooltip_text(self) -> str:
        """Generate tooltip text for the thumbnail."""
        lines = [
            f"Page {self.page_reference.page_number}",
            f"File: {self.page_reference.file_id[:8]}..."
        ]

        if self.is_assigned and self.assignment_id:
            lines.append(f"Assigned to: {self.assignment_id[:8]}...")

        return "\n".join(lines)

    def paintEvent(self, event):
        """Custom paint event for additional decorations."""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw selection overlay
        if self.is_selected:
            overlay_color = QColor(self.selection_color)
            overlay_color.setAlpha(40)
            painter.fillRect(self.rect(), QBrush(overlay_color))

        # Draw loading indicator
        if self.is_loading:
            # Draw animated loading dots or spinner
            pass

        # Draw assignment badge if assigned
        if self.is_assigned:
            self._draw_assignment_badge(painter)

        painter.end()

    def _draw_assignment_badge(self, painter: QPainter):
        """Draw assignment indicator badge."""
        badge_size = 20
        badge_rect = QRect(
            self.width() - badge_size - 5,
            5,
            badge_size,
            badge_size
        )

        # Draw badge background
        painter.setBrush(QBrush(self.assignment_color))
        painter.setPen(QPen(Qt.white, 2))
        painter.drawEllipse(badge_rect)

        # Draw checkmark or assignment indicator
        painter.setPen(QPen(Qt.white, 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

        # Simple checkmark
        check_rect = badge_rect.adjusted(4, 4, -4, -4)
        painter.drawLine(
            check_rect.left() + 2, check_rect.center().y(),
            check_rect.center().x(), check_rect.bottom() - 2
        )
        painter.drawLine(
            check_rect.center().x(), check_rect.bottom() - 2,
                                     check_rect.right() - 2, check_rect.top() + 2
        )

    def sizeHint(self) -> QSize:
        """Return preferred size."""
        return QSize(
            self.thumbnail_size.width + 20,
            self.thumbnail_size.height + 40
        )

    def get_page_reference(self) -> PageReference:
        """Get the page reference for this thumbnail."""
        return self.page_reference

    def is_thumbnail_loaded(self) -> bool:
        """Check if thumbnail is loaded."""
        return not self.is_loading and self.thumbnail_pixmap is not None

    def refresh_thumbnail(self):
        """Refresh the thumbnail from source."""
        self._set_loading_state()
        self._request_thumbnail()

    def set_thumbnail_size(self, size: ThumbnailSize):
        """Update thumbnail size."""
        if self.thumbnail_size != size:
            self.thumbnail_size = size

            # Update widget and label sizes
            self.setFixedSize(
                size.width + 20,
                size.height + 40
            )
            self.thumbnail_label.setFixedSize(size.width, size.height)

            # Refresh thumbnail with new size
            if self.thumbnail_pixmap:
                scaled_pixmap = self.thumbnail_pixmap.scaled(
                    size.size_tuple,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.thumbnail_label.setPixmap(scaled_pixmap)

    def __str__(self) -> str:
        """String representation."""
        return f"PageThumbnail({self.page_reference})"

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (f"PageThumbnailWidget(page={self.page_reference.page_number}, "
                f"file={self.page_reference.file_id[:8]}, "
                f"selected={self.is_selected}, assigned={self.is_assigned})")

