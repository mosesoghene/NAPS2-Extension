"""
Page assignment and reference models.

Handles the linking of specific PDF pages to index values and
manages the document creation assignments.
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Set, Tuple
from dataclasses import dataclass

from .schema import IndexSchema
from .enums import ValidationSeverity
from ..core.exceptions import AssignmentConflictError, SchemaValidationError


@dataclass(frozen=True)
class PageReference:
    """
    References specific pages within scanned files.

    Immutable reference to a specific page in a PDF file.
    """
    file_id: str
    page_number: int  # 1-based page numbering

    def __post_init__(self):
        if self.page_number < 1:
            raise ValueError("Page number must be 1 or greater")

    @property
    def page_id(self) -> str:
        """Get unique identifier for this page."""
        return f"{self.file_id}:{self.page_number}"

    def get_unique_id(self) -> str:
        """Generate unique identifier for this page reference."""
        return self.page_id

    def __str__(self) -> str:
        return f"Page {self.page_number} of {self.file_id[:8]}..."

    def __repr__(self) -> str:
        return f"PageReference(file_id='{self.file_id}', page_number={self.page_number})"


class DocumentPreview:
    """Preview information for document generation."""

    def __init__(self, filename: str, folder_path: str, pages: List[PageReference]):
        self.filename = filename
        self.folder_path = folder_path
        self.page_references = pages.copy()
        self.page_count = len(pages)
        self.estimated_file_size = 0
        self.conflicts: List[str] = []
        self.created_timestamp = datetime.now()

    def get_full_path(self) -> Path:
        """Get complete file path including folder and filename."""
        if self.folder_path:
            return Path(self.folder_path) / f"{self.filename}.pdf"
        return Path(f"{self.filename}.pdf")

    def calculate_estimated_size(self, avg_page_size: int = 50000) -> int:
        """
        Calculate estimated output file size.

        Args:
            avg_page_size: Average size per page in bytes

        Returns:
            Estimated file size in bytes
        """
        self.estimated_file_size = self.page_count * avg_page_size
        return self.estimated_file_size

    def validate_paths(self) -> Tuple[bool, List[str]]:
        """
        Validate folder and file paths for OS compatibility.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        from .enums import AppConstants

        errors = []

        # Validate filename
        if AppConstants.has_invalid_chars(self.filename):
            errors.append("Filename contains invalid characters")

        if AppConstants.is_reserved_name(self.filename):
            errors.append("Filename uses reserved system name")

        # Validate folder path
        if self.folder_path:
            path_parts = self.folder_path.split('/')
            for part in path_parts:
                if AppConstants.has_invalid_chars(part):
                    errors.append(f"Folder name '{part}' contains invalid characters")
                if AppConstants.is_reserved_name(part):
                    errors.append(f"Folder name '{part}' uses reserved system name")

        # Check total path length
        full_path = str(self.get_full_path())
        if len(full_path) > AppConstants.MAX_PATH_LENGTH:
            errors.append(f"Complete path is too long ({len(full_path)} > {AppConstants.MAX_PATH_LENGTH})")

        return len(errors) == 0, errors

    def __str__(self) -> str:
        return f"DocumentPreview('{self.filename}', {self.page_count} pages)"


class PageAssignment:
    """
    Links specific pages to index values for document creation.

    Represents a complete assignment of pages to a set of index values,
    which will result in a single output document.
    """

    def __init__(self, assignment_id: Optional[str] = None, schema: Optional[IndexSchema] = None):
        self.assignment_id = assignment_id or str(uuid.uuid4())
        self.page_references: List[PageReference] = []
        self.index_values: Dict[str, str] = {}
        self.schema = schema

        # Generated properties
        self.output_filename = ""
        self.output_folder_path = ""
        self.document_preview: Optional[DocumentPreview] = None

        # Validation and state
        self.is_valid = False
        self.validation_errors: List[str] = []
        self.validation_warnings: List[str] = []

        # Timestamps
        self.created_timestamp = datetime.now()
        self.modified_timestamp = datetime.now()

    def add_page(self, page_reference: PageReference):
        """Add a page to this assignment."""
        if page_reference not in self.page_references:
            self.page_references.append(page_reference)
            self.modified_timestamp = datetime.now()
            self._invalidate_preview()

    def add_pages(self, page_references: List[PageReference]):
        """Add multiple pages to this assignment."""
        for page_ref in page_references:
            if page_ref not in self.page_references:
                self.page_references.append(page_ref)

        if page_references:  # Only update timestamp if we actually added pages
            self.modified_timestamp = datetime.now()
            self._invalidate_preview()

    def remove_page(self, page_reference: PageReference) -> bool:
        """Remove a page from this assignment. Returns True if found and removed."""
        try:
            self.page_references.remove(page_reference)
            self.modified_timestamp = datetime.now()
            self._invalidate_preview()
            return True
        except ValueError:
            return False

    def clear_pages(self):
        """Remove all page assignments."""
        if self.page_references:
            self.page_references.clear()
            self.modified_timestamp = datetime.now()
            self._invalidate_preview()

    def update_index_values(self, values: Dict[str, str]):
        """Update all index values at once."""
        self.index_values.update(values)
        self.modified_timestamp = datetime.now()
        self._invalidate_preview()

    def set_index_value(self, field_name: str, value: str):
        """Set a specific field value."""
        self.index_values[field_name] = value
        self.modified_timestamp = datetime.now()
        self._invalidate_preview()

    def get_index_value(self, field_name: str) -> Optional[str]:
        """Get a specific field value."""
        return self.index_values.get(field_name)

    def get_page_count(self) -> int:
        """Get the number of pages in this assignment."""
        return len(self.page_references)

    def has_pages(self) -> bool:
        """Check if this assignment has any pages."""
        return len(self.page_references) > 0

    def get_file_ids(self) -> Set[str]:
        """Get set of unique file IDs referenced by this assignment."""
        return {ref.file_id for ref in self.page_references}

    def get_pages_from_file(self, file_id: str) -> List[PageReference]:
        """Get all page references from a specific file."""
        return [ref for ref in self.page_references if ref.file_id == file_id]

    def validate_assignment(self) -> Tuple[bool, List[str], List[str]]:
        """
        Validate the assignment completeness and consistency.

        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        errors = []
        warnings = []

        # Check if we have pages
        if not self.page_references:
            errors.append("Assignment has no pages")

        # Check if we have a schema
        if not self.schema:
            errors.append("Assignment has no schema")
            return False, errors, warnings

        # Validate against schema
        schema_valid, schema_errors = self.schema.validate_assignment_values(self.index_values)
        errors.extend(schema_errors)

        # Check for missing required fields
        for field in self.schema.get_required_fields():
            value = self.index_values.get(field.name, "").strip()
            if not value:
                errors.append(f"Required field '{field.name}' is missing")

        # Generate preview to check for path issues
        try:
            preview = self.generate_document_preview()
            path_valid, path_errors = preview.validate_paths()
            if not path_valid:
                errors.extend(path_errors)
        except Exception as e:
            errors.append(f"Cannot generate document preview: {e}")

        # Warnings for potential issues
        if self.get_page_count() > 100:
            warnings.append(f"Large document ({self.get_page_count()} pages) may be slow to process")

        if len(self.get_file_ids()) > 10:
            warnings.append(f"Pages from many files ({len(self.get_file_ids())}) may affect performance")

        # Update state
        self.is_valid = len(errors) == 0
        self.validation_errors = errors
        self.validation_warnings = warnings

        return self.is_valid, errors, warnings

    def generate_document_preview(self) -> DocumentPreview:
        """Create a preview of the resulting document."""
        if not self.schema:
            raise SchemaValidationError("Cannot generate preview without schema")

        # Generate filename and folder path
        timestamp = self.created_timestamp
        sequential = 1  # This would be calculated based on existing files

        filename = self.schema.generate_filename(self.index_values, timestamp, sequential)
        folder_path = self.schema.generate_folder_structure(self.index_values)

        # Create preview
        preview = DocumentPreview(filename, folder_path, self.page_references)
        preview.calculate_estimated_size()

        # Cache the preview
        self.document_preview = preview
        self.output_filename = filename
        self.output_folder_path = folder_path

        return preview

    def _invalidate_preview(self):
        """Mark the current preview as invalid."""
        self.document_preview = None
        self.is_valid = False

    def get_summary(self) -> Dict[str, Any]:
        """Get summary information about this assignment."""
        return {
            'assignment_id': self.assignment_id,
            'page_count': self.get_page_count(),
            'file_count': len(self.get_file_ids()),
            'field_count': len(self.index_values),
            'is_valid': self.is_valid,
            'error_count': len(self.validation_errors),
            'warning_count': len(self.validation_warnings),
            'created': self.created_timestamp,
            'modified': self.modified_timestamp,
            'schema_name': self.schema.name if self.schema else None
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize assignment to dictionary."""
        return {
            'assignment_id': self.assignment_id,
            'page_references': [
                {'file_id': ref.file_id, 'page_number': ref.page_number}
                for ref in self.page_references
            ],
            'index_values': self.index_values.copy(),
            'schema_name': self.schema.name if self.schema else None,
            'output_filename': self.output_filename,
            'output_folder_path': self.output_folder_path,
            'created_timestamp': self.created_timestamp.isoformat(),
            'modified_timestamp': self.modified_timestamp.isoformat(),
            'is_valid': self.is_valid
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], schema: Optional[IndexSchema] = None) -> 'PageAssignment':
        """Create assignment from dictionary."""
        assignment = cls(data.get('assignment_id'), schema)

        # Load page references
        for page_data in data.get('page_references', []):
            ref = PageReference(page_data['file_id'], page_data['page_number'])
            assignment.page_references.append(ref)

        # Load index values
        assignment.index_values = data.get('index_values', {}).copy()

        # Load metadata
        assignment.output_filename = data.get('output_filename', '')
        assignment.output_folder_path = data.get('output_folder_path', '')

        # Load timestamps
        if 'created_timestamp' in data:
            assignment.created_timestamp = datetime.fromisoformat(data['created_timestamp'])
        if 'modified_timestamp' in data:
            assignment.modified_timestamp = datetime.fromisoformat(data['modified_timestamp'])

        assignment.is_valid = data.get('is_valid', False)

        return assignment

    def clone(self) -> 'PageAssignment':
        """Create a copy of this assignment with a new ID."""
        new_assignment = PageAssignment(schema=self.schema)
        new_assignment.page_references = self.page_references.copy()
        new_assignment.index_values = self.index_values.copy()
        return new_assignment

    def __str__(self) -> str:
        page_count = self.get_page_count()
        file_count = len(self.get_file_ids())
        return f"PageAssignment({page_count} pages from {file_count} files)"

    def __repr__(self) -> str:
        return (f"PageAssignment(id='{self.assignment_id[:8]}...', "
                f"pages={self.get_page_count()}, valid={self.is_valid})")

    def __eq__(self, other) -> bool:
        if not isinstance(other, PageAssignment):
            return False
        return self.assignment_id == other.assignment_id

    def __hash__(self) -> int:
        return hash(self.assignment_id)


class AssignmentManager:
    """
    Manages collections of page assignments and handles conflicts.
    """

    def __init__(self):
        self.assignments: Dict[str, PageAssignment] = {}
        self._page_to_assignment: Dict[str, str] = {}  # page_id -> assignment_id

    def add_assignment(self, assignment: PageAssignment):
        """Add an assignment to the manager."""
        self.assignments[assignment.assignment_id] = assignment
        self._update_page_mapping(assignment)

    def remove_assignment(self, assignment_id: str) -> bool:
        """Remove an assignment. Returns True if found and removed."""
        if assignment_id in self.assignments:
            assignment = self.assignments[assignment_id]

            # Remove from page mapping
            for page_ref in assignment.page_references:
                self._page_to_assignment.pop(page_ref.page_id, None)

            del self.assignments[assignment_id]
            return True
        return False

    def get_assignment(self, assignment_id: str) -> Optional[PageAssignment]:
        """Get assignment by ID."""
        return self.assignments.get(assignment_id)

    def get_assignment_for_page(self, page_reference: PageReference) -> Optional[PageAssignment]:
        """Get the assignment that contains a specific page."""
        assignment_id = self._page_to_assignment.get(page_reference.page_id)
        return self.assignments.get(assignment_id) if assignment_id else None

    def check_page_conflicts(self, page_references: List[PageReference]) -> List[PageReference]:
        """Check which pages are already assigned to other assignments."""
        conflicts = []
        for page_ref in page_references:
            if page_ref.page_id in self._page_to_assignment:
                conflicts.append(page_ref)
        return conflicts

    def get_unassigned_pages(self, all_pages: List[PageReference]) -> List[PageReference]:
        """Get pages that are not assigned to any assignment."""
        return [page for page in all_pages if page.page_id not in self._page_to_assignment]

    def validate_all_assignments(self) -> Dict[str, Tuple[bool, List[str], List[str]]]:
        """
        Validate all assignments.

        Returns:
            Dict mapping assignment_id to (is_valid, errors, warnings)
        """
        results = {}
        for assignment_id, assignment in self.assignments.items():
            is_valid, errors, warnings = assignment.validate_assignment()
            results[assignment_id] = (is_valid, errors, warnings)
        return results

    def get_filename_conflicts(self) -> List[Tuple[str, str, str]]:
        """
        Check for filename conflicts between assignments.

        Returns:
            List of (assignment_id1, assignment_id2, conflicting_path) tuples
        """
        conflicts = []
        path_to_assignments = {}

        for assignment in self.assignments.values():
            if assignment.document_preview:
                full_path = str(assignment.document_preview.get_full_path())
                if full_path in path_to_assignments:
                    # Conflict found
                    existing_id = path_to_assignments[full_path]
                    conflicts.append((existing_id, assignment.assignment_id, full_path))
                else:
                    path_to_assignments[full_path] = assignment.assignment_id

        return conflicts

    def _update_page_mapping(self, assignment: PageAssignment):
        """Update the page-to-assignment mapping."""
        for page_ref in assignment.page_references:
            self._page_to_assignment[page_ref.page_id] = assignment.assignment_id

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about managed assignments."""
        total_pages = sum(len(a.page_references) for a in self.assignments.values())
        valid_assignments = sum(1 for a in self.assignments.values() if a.is_valid)

        return {
            'total_assignments': len(self.assignments),
            'valid_assignments': valid_assignments,
            'invalid_assignments': len(self.assignments) - valid_assignments,
            'total_pages': total_pages,
            'unique_files': len(set().union(*(a.get_file_ids() for a in self.assignments.values()))),
            'filename_conflicts': len(self.get_filename_conflicts())
        }

    def clear(self):
        """Remove all assignments."""
        self.assignments.clear()
        self._page_to_assignment.clear()
