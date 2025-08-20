"""
Manages complex page selection operations.

Handles single-click, multi-select, range selection, and drag selection
with proper modifier key support and selection state management.
"""

import logging
from typing import Set, List, Optional, Tuple
from enum import Enum

from PySide6.QtCore import QObject, pyqtSignal, Qt
from PySide6.QtGui import QKeySequence

from ..models.enums import SelectionMode
from ..core.signals import app_signals


class PageSelectionManager(QObject):
    """Manages complex page selection operations."""

    # Signals
    selection_changed = pyqtSignal(list)  # List[str] - page IDs
    selection_cleared = pyqtSignal()
    selection_range_changed = pyqtSignal(str, str)  # start_page_id, end_page_id

    def __init__(self, parent=None):
        """Initialize selection manager."""
        super().__init__(parent)

        # Selection state
        self.selected_pages: Set[str] = set()
        self.last_selected_page: Optional[str] = None
        self.range_start_page: Optional[str] = None

        # Available pages (maintained by external code)
        self.available_pages: List[str] = []
        self.page_positions: dict = {}  # page_id -> index position

        # Configuration
        self.selection_mode = SelectionMode.MULTIPLE
        self.allow_empty_selection = True
        self.max_selection_size: Optional[int] = None

        # State tracking
        self.is_dragging = False
        self.drag_start_page: Optional[str] = None

        logging.debug("PageSelectionManager initialized")

    def set_available_pages(self, page_list: List[str]):
        """
        Set the list of available pages for selection.

        Args:
            page_list: List of page IDs in display order
        """
        try:
            # Clear selections that are no longer available
            old_selection = self.selected_pages.copy()
            self.available_pages = page_list.copy()

            # Build position mapping
            self.page_positions = {page_id: idx for idx, page_id in enumerate(page_list)}

            # Filter out invalid selections
            valid_selections = {page_id for page_id in self.selected_pages if page_id in self.page_positions}

            if valid_selections != self.selected_pages:
                self.selected_pages = valid_selections
                if self.last_selected_page not in self.page_positions:
                    self.last_selected_page = None
                self._emit_selection_changed()

            logging.debug(f"Updated available pages: {len(page_list)} pages")

        except Exception as e:
            logging.error(f"Error setting available pages: {e}")

    def handle_single_click(self, page_id: str, modifiers: Qt.KeyboardModifier = Qt.NoModifier) -> bool:
        """
        Handle single page click with modifier keys.

        Args:
            page_id: ID of clicked page
            modifiers: Keyboard modifier flags

        Returns:
            bool: True if selection changed
        """
        try:
            if page_id not in self.page_positions:
                logging.warning(f"Clicked page not in available pages: {page_id}")
                return False

            old_selection = self.selected_pages.copy()

            # Handle different modifier combinations
            if modifiers & Qt.ControlModifier:
                # Ctrl+Click: Toggle selection
                self._toggle_page_selection(page_id)

            elif modifiers & Qt.ShiftModifier:
                # Shift+Click: Range selection
                self._handle_range_selection(page_id)

            else:
                # Normal click: Select only this page
                if self.selection_mode == SelectionMode.SINGLE:
                    self.selected_pages = {page_id}
                else:
                    self.selected_pages = {page_id}

            self.last_selected_page = page_id

            # Check if selection changed
            if old_selection != self.selected_pages:
                self._emit_selection_changed()
                return True

            return False

        except Exception as e:
            logging.error(f"Error handling single click on {page_id}: {e}")
            return False

    def handle_range_selection(self, start_page_id: str, end_page_id: str) -> bool:
        """
        Handle range selection between two pages.

        Args:
            start_page_id: Start of range
            end_page_id: End of range

        Returns:
            bool: True if selection changed
        """
        try:
            if start_page_id not in self.page_positions or end_page_id not in self.page_positions:
                logging.warning(f"Range selection with invalid pages: {start_page_id} to {end_page_id}")
                return False

            old_selection = self.selected_pages.copy()

            # Get positions for range calculation
            start_pos = self.page_positions[start_page_id]
            end_pos = self.page_positions[end_page_id]

            # Ensure start comes before end
            if start_pos > end_pos:
                start_pos, end_pos = end_pos, start_pos
                start_page_id, end_page_id = end_page_id, start_page_id

            # Select all pages in range
            range_pages = {
                page_id for page_id, pos in self.page_positions.items()
                if start_pos <= pos <= end_pos
            }

            self.selected_pages = range_pages
            self.last_selected_page = end_page_id
            self.selection_range_changed.emit(start_page_id, end_page_id)

            # Check if selection changed
            if old_selection != self.selected_pages:
                self._emit_selection_changed()
                return True

            return False

        except Exception as e:
            logging.error(f"Error handling range selection: {e}")
            return False

    def _handle_range_selection(self, end_page_id: str):
        """Handle range selection from last selected to current page."""
        if not self.last_selected_page:
            # No previous selection, just select this page
            self.selected_pages = {end_page_id}
            return

        start_page_id = self.last_selected_page
        self.handle_range_selection(start_page_id, end_page_id)

    def handle_drag_selection(self, page_ids: List[str]) -> bool:
        """
        Handle drag selection of multiple pages.

        Args:
            page_ids: List of page IDs being drag-selected

        Returns:
            bool: True if selection changed
        """
        try:
            if not page_ids:
                return False

            old_selection = self.selected_pages.copy()

            # Filter valid page IDs
            valid_page_ids = [page_id for page_id in page_ids if page_id in self.page_positions]

            if not valid_page_ids:
                return False

            # Set selection to dragged pages
            self.selected_pages = set(valid_page_ids)
            self.last_selected_page = valid_page_ids[-1] if valid_page_ids else None

            # Check if selection changed
            if old_selection != self.selected_pages:
                self._emit_selection_changed()
                return True

            return False

        except Exception as e:
            logging.error(f"Error handling drag selection: {e}")
            return False

    def _toggle_page_selection(self, page_id: str):
        """Toggle selection state of a single page."""
        if page_id in self.selected_pages:
            if len(self.selected_pages) > 1 or self.allow_empty_selection:
                self.selected_pages.remove(page_id)
        else:
            if not self.max_selection_size or len(self.selected_pages) < self.max_selection_size:
                self.selected_pages.add(page_id)

    def select_all(self) -> bool:
        """
        Select all available pages.

        Returns:
            bool: True if selection changed
        """
        try:
            if self.selection_mode == SelectionMode.SINGLE:
                return False

            old_selection = self.selected_pages.copy()

            # Apply selection size limit
            if self.max_selection_size:
                pages_to_select = self.available_pages[:self.max_selection_size]
            else:
                pages_to_select = self.available_pages

            self.selected_pages = set(pages_to_select)

            if pages_to_select:
                self.last_selected_page = pages_to_select[-1]

            # Check if selection changed
            if old_selection != self.selected_pages:
                self._emit_selection_changed()
                return True

            return False

        except Exception as e:
            logging.error(f"Error selecting all pages: {e}")
            return False

    def clear_selection(self) -> bool:
        """
        Clear all selections.

        Returns:
            bool: True if selection changed
        """
        try:
            if not self.selected_pages:
                return False

            if not self.allow_empty_selection and len(self.available_pages) > 0:
                return False

            self.selected_pages.clear()
            self.last_selected_page = None

            self.selection_cleared.emit()
            self._emit_selection_changed()
            return True

        except Exception as e:
            logging.error(f"Error clearing selection: {e}")
            return False

    def invert_selection(self) -> bool:
        """
        Invert current selection.

        Returns:
            bool: True if selection changed
        """
        try:
            if self.selection_mode == SelectionMode.SINGLE:
                return False

            old_selection = self.selected_pages.copy()

            # Calculate inverted selection
            all_pages = set(self.available_pages)
            inverted_pages = all_pages - self.selected_pages

            # Apply selection size limit
            if self.max_selection_size and len(inverted_pages) > self.max_selection_size:
                # Keep first N pages in display order
                sorted_inverted = [page_id for page_id in self.available_pages if page_id in inverted_pages]
                inverted_pages = set(sorted_inverted[:self.max_selection_size])

            self.selected_pages = inverted_pages

            if inverted_pages:
                # Set last selected to the last page in display order
                for page_id in reversed(self.available_pages):
                    if page_id in inverted_pages:
                        self.last_selected_page = page_id
                        break
            else:
                self.last_selected_page = None

            # Check if selection changed
            if old_selection != self.selected_pages:
                self._emit_selection_changed()
                return True

            return False

        except Exception as e:
            logging.error(f"Error inverting selection: {e}")
            return False

    def add_to_selection(self, page_ids: List[str]) -> bool:
        """
        Add pages to current selection.

        Args:
            page_ids: List of page IDs to add

        Returns:
            bool: True if selection changed
        """
        try:
            if self.selection_mode == SelectionMode.SINGLE:
                return False

            old_selection = self.selected_pages.copy()

            # Filter valid page IDs and check limits
            valid_pages = [page_id for page_id in page_ids if page_id in self.page_positions]

            if self.max_selection_size:
                available_slots = self.max_selection_size - len(self.selected_pages)
                valid_pages = valid_pages[:available_slots]

            # Add pages
            self.selected_pages.update(valid_pages)

            if valid_pages:
                self.last_selected_page = valid_pages[-1]

            # Check if selection changed
            if old_selection != self.selected_pages:
                self._emit_selection_changed()
                return True

            return False

        except Exception as e:
            logging.error(f"Error adding to selection: {e}")
            return False

    def remove_from_selection(self, page_ids: List[str]) -> bool:
        """
        Remove pages from current selection.

        Args:
            page_ids: List of page IDs to remove

        Returns:
            bool: True if selection changed
        """
        try:
            old_selection = self.selected_pages.copy()

            # Remove pages
            pages_to_remove = set(page_ids) & self.selected_pages

            if not pages_to_remove:
                return False

            # Check if removal would create empty selection when not allowed
            if not self.allow_empty_selection:
                if len(self.selected_pages) - len(pages_to_remove) == 0:
                    return False

            self.selected_pages -= pages_to_remove

            # Update last selected if it was removed
            if self.last_selected_page in pages_to_remove:
                if self.selected_pages:
                    # Find the last selected page in display order
                    for page_id in reversed(self.available_pages):
                        if page_id in self.selected_pages:
                            self.last_selected_page = page_id
                            break
                else:
                    self.last_selected_page = None

            # Check if selection changed
            if old_selection != self.selected_pages:
                self._emit_selection_changed()
                return True

            return False

        except Exception as e:
            logging.error(f"Error removing from selection: {e}")
            return False

    def select_range_by_position(self, start_index: int, end_index: int) -> bool:
        """
        Select range of pages by their position indices.

        Args:
            start_index: Start position (inclusive)
            end_index: End position (inclusive)

        Returns:
            bool: True if selection changed
        """
        try:
            if start_index < 0 or end_index >= len(self.available_pages):
                return False

            if start_index > end_index:
                start_index, end_index = end_index, start_index

            # Get page IDs in range
            range_pages = self.available_pages[start_index:end_index + 1]

            return self.handle_drag_selection(range_pages)

        except Exception as e:
            logging.error(f"Error selecting range by position: {e}")
            return False

    def get_selected_pages(self) -> List[str]:
        """
        Return selected pages in display order.

        Returns:
            List of selected page IDs in display order
        """
        try:
            # Return pages in their display order
            return [page_id for page_id in self.available_pages if page_id in self.selected_pages]
        except Exception as e:
            logging.error(f"Error getting selected pages: {e}")
            return []

    def get_selected_pages_set(self) -> Set[str]:
        """Return selected pages as a set."""
        return self.selected_pages.copy()

    def is_page_selected(self, page_id: str) -> bool:
        """Check if a page is selected."""
        return page_id in self.selected_pages

    def get_selection_count(self) -> int:
        """Return number of selected pages."""
        return len(self.selected_pages)

    def get_last_selected_page(self) -> Optional[str]:
        """Return the last selected page ID."""
        return self.last_selected_page

    def get_selection_bounds(self) -> Tuple[Optional[int], Optional[int]]:
        """
        Get the bounds of current selection.

        Returns:
            Tuple of (start_index, end_index) or (None, None) if no selection
        """
        try:
            if not self.selected_pages:
                return None, None

            selected_positions = [self.page_positions[page_id] for page_id in self.selected_pages]
            return min(selected_positions), max(selected_positions)

        except Exception as e:
            logging.error(f"Error getting selection bounds: {e}")
            return None, None

    def _emit_selection_changed(self):
        """Emit selection changed signal."""
        try:
            selected_list = self.get_selected_pages()
            self.selection_changed.emit(selected_list)
            app_signals.page_selection_changed.emit(selected_list)

            if not selected_list:
                app_signals.page_selection_cleared.emit()

        except Exception as e:
            logging.error(f"Error emitting selection changed signal: {e}")

    # Configuration methods
    def set_selection_mode(self, mode: SelectionMode):
        """Set selection mode."""
        old_mode = self.selection_mode
        self.selection_mode = mode

        # Adjust current selection if needed
        if mode == SelectionMode.SINGLE and len(self.selected_pages) > 1:
            # Keep only the last selected page
            if self.last_selected_page:
                self.selected_pages = {self.last_selected_page}
            else:
                # Keep first page in display order
                first_selected = next(
                    (page_id for page_id in self.available_pages if page_id in self.selected_pages),
                    None
                )
                self.selected_pages = {first_selected} if first_selected else set()
            self._emit_selection_changed()

    def set_allow_empty_selection(self, allow: bool):
        """Set whether empty selection is allowed."""
        self.allow_empty_selection = allow

        # If empty selection not allowed and currently empty, select first page
        if not allow and not self.selected_pages and self.available_pages:
            self.selected_pages = {self.available_pages[0]}
            self.last_selected_page = self.available_pages[0]
            self._emit_selection_changed()

    def set_max_selection_size(self, max_size: Optional[int]):
        """Set maximum selection size."""
        self.max_selection_size = max_size

        # Trim current selection if needed
        if max_size and len(self.selected_pages) > max_size:
            # Keep the most recently selected pages
            selected_in_order = self.get_selected_pages()
            pages_to_keep = set(selected_in_order[-max_size:])
            self.selected_pages = pages_to_keep
            self._emit_selection_changed()

    def get_selection_info(self) -> dict:
        """Get comprehensive selection information."""
        bounds = self.get_selection_bounds()

        return {
            'selected_count': len(self.selected_pages),
            'total_pages': len(self.available_pages),
            'selection_mode': self.selection_mode.value,
            'allow_empty': self.allow_empty_selection,
            'max_size': self.max_selection_size,
            'last_selected': self.last_selected_page,
            'selection_bounds': bounds,
            'has_selection': len(self.selected_pages) > 0,
            'is_full_selection': len(self.selected_pages) == len(self.available_pages),
        }