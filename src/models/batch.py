"""
Document batch management and organization.

Handles collections of scanned files and their page assignments,
providing batch-level operations and validation.
"""

import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set, Any, Tuple
from collections import defaultdict

from .scanned_file import ScannedFile, ScannedFileFactory
from .assignment import PageAssignment, PageReference, AssignmentManager
from .schema import IndexSchema
from .enums import ProcessingState, ValidationSeverity
from ..core.exceptions import FileProcessingError, AssignmentConflictError


class DocumentBatch:
    """
    Represents a collection of scanned pages and their assignments.

    Manages the complete workflow from scanned PDFs to organized documents,
    including file tracking, assignment management, and validation.
    """

    def __init__(self, batch_id: Optional[str] = None, staging_directory: Optional[Path] = None):
        self.batch_id = batch_id or str(uuid.uuid4())
        self.staging_directory = staging_directory

        # Core collections
        self.scanned_files: List[ScannedFile] = []
        self.assignment_manager = AssignmentManager()

        # Schema and state
        self.applied_schema: Optional[IndexSchema] = None
        self.processing_state = ProcessingState.IDLE

        # Timestamps and metadata
        self.batch_timestamp = datetime.now()
        self.last_modified = datetime.now()
        self.created_by = ""
        self.description = ""

        # File mapping for quick lookups
        self._file_id_to_file: Dict[str, ScannedFile] = {}
        self._file_path_to_file: Dict[Path, ScannedFile] = {}

        # Cached properties
        self._total_pages: Optional[int] = None
        self._validation_results: Optional[Dict[str, Any]] = None

    @property
    def total_pages(self) -> int:
        """Get total number of pages across all files."""
        if self._total_pages is None:
            self._total_pages = sum(file.page_count for file in self.scanned_files)
        return self._total_pages

    @property
    def unassigned_page_count(self) -> int:
        """Get number of pages not assigned to any document."""
        all_pages = self.get_all_page_references()
        unassigned = self.assignment_manager.get_unassigned_pages(all_pages)
        return len(unassigned)

    @property
    def assignment_count(self) -> int:
        """Get number of page assignments."""
        return len(self.assignment_manager.assignments)

    @property
    def file_count(self) -> int:
        """Get number of scanned files."""
        return len(self.scanned_files)

    def add_scanned_file(self, file_path: Path) -> Optional[ScannedFile]:
        """
        Add a new scanned file to the batch.

        Args:
            file_path: Path to the PDF file

        Returns:
            ScannedFile instance if successful, None if failed
        """
        # Check if file already exists
        if file_path in self._file_path_to_file:
            logging.warning(f"File already in batch: {file_path}")
            return self._file_path_to_file[file_path]

        # Create scanned file
        scanned_file = ScannedFileFactory.create_from_path(file_path)
        if not scanned_file:
            logging.error(f"Failed to create ScannedFile for {file_path}")
            return None

        # Add to collections
        self.scanned_files.append(scanned_file)
        self._file_id_to_file[scanned_file.file_id] = scanned_file
        self._file_path_to_file[file_path] = scanned_file

        # Invalidate cached values
        self._invalidate_cache()

        self.last_modified = datetime.now()
        logging.info(f"Added file to batch: {file_path} ({scanned_file.page_count} pages)")

        return scanned_file

    def add_scanned_files(self, file_paths: List[Path]) -> List[ScannedFile]:
        """
        Add multiple scanned files to the batch.

        Args:
            file_paths: List of paths to PDF files

        Returns:
            List of successfully added ScannedFile instances
        """
        added_files = []
        for file_path in file_paths:
            scanned_file = self.add_scanned_file(file_path)
            if scanned_file:
                added_files.append(scanned_file)

        if added_files:
            logging.info(f"Added {len(added_files)} files to batch {self.batch_id}")

        return added_files

    def remove_file(self, file_id: str) -> bool:
        """
        Remove a file from the batch.

        Args:
            file_id: ID of the file to remove

        Returns:
            bool: True if file was found and removed
        """
        scanned_file = self._file_id_to_file.get(file_id)
        if not scanned_file:
            return False

        # Remove from all assignments first
        assignments_to_update = []
        for assignment in self.assignment_manager.assignments.values():
            pages_from_file = assignment.get_pages_from_file(file_id)
            if pages_from_file:
                assignments_to_update.append((assignment, pages_from_file))

        # Remove pages from assignments
        for assignment, pages in assignments_to_update:
            for page_ref in pages:
                assignment.remove_page(page_ref)

            # Remove assignment if it has no pages left
            if not assignment.has_pages():
                self.assignment_manager.remove_assignment(assignment.assignment_id)

        # Remove from collections
        self.scanned_files.remove(scanned_file)
        del self._file_id_to_file[file_id]
        del self._file_path_to_file[scanned_file.file_path]

        self._invalidate_cache()
        self.last_modified = datetime.now()

        logging.info(f"Removed file {file_id} from batch")
        return True

    def get_file_by_id(self, file_id: str) -> Optional[ScannedFile]:
        """Get a scanned file by its ID."""
        return self._file_id_to_file.get(file_id)

    def get_file_by_path(self, file_path: Path) -> Optional[ScannedFile]:
        """Get a scanned file by its path."""
        return self._file_path_to_file.get(file_path)

    def get_all_page_references(self) -> List[PageReference]:
        """Get all page references across all files."""
        all_pages = []
        for scanned_file in self.scanned_files:
            for page_num in range(1, scanned_file.page_count + 1):
                page_ref = PageReference(scanned_file.file_id, page_num)
                all_pages.append(page_ref)
        return all_pages

    def get_unassigned_pages(self) -> List[PageReference]:
        """Get pages that haven't been assigned to any document."""
        all_pages = self.get_all_page_references()
        return self.assignment_manager.get_unassigned_pages(all_pages)

    def get_assigned_pages(self) -> List[PageReference]:
        """Get all pages that have been assigned."""
        assigned_pages = []
        for assignment in self.assignment_manager.assignments.values():
            assigned_pages.extend(assignment.page_references)
        return assigned_pages

    def assign_pages_to_index(self, page_references: List[PageReference],
                              index_values: Dict[str, str]) -> PageAssignment:
        """
        Create a new page assignment.

        Args:
            page_references: Pages to assign
            index_values: Index field values for the assignment

        Returns:
            Created PageAssignment

        Raises:
            AssignmentConflictError: If pages are already assigned
        """
        # Check for conflicts
        conflicts = self.assignment_manager.check_page_conflicts(page_references)
        if conflicts:
            conflict_ids = [ref.page_id for ref in conflicts]
            raise AssignmentConflictError(
                f"Pages already assigned: {conflict_ids}",
                conflicting_assignments=conflict_ids
            )

        # Create assignment
        assignment = PageAssignment(schema=self.applied_schema)
        assignment.add_pages(page_references)
        assignment.update_index_values(index_values)

        # Add to manager
        self.assignment_manager.add_assignment(assignment)

        self.last_modified = datetime.now()
        logging.info(f"Created assignment {assignment.assignment_id} with {len(page_references)} pages")

        return assignment

    def remove_assignment(self, assignment_id: str) -> bool:
        """
        Remove a page assignment.

        Args:
            assignment_id: ID of assignment to remove

        Returns:
            bool: True if assignment was found and removed
        """
        if self.assignment_manager.remove_assignment(assignment_id):
            self.last_modified = datetime.now()
            logging.info(f"Removed assignment {assignment_id}")
            return True
        return False

    def clear_assignments(self):
        """Remove all page assignments."""
        assignment_count = len(self.assignment_manager.assignments)
        self.assignment_manager.clear()
        self.last_modified = datetime.now()
        logging.info(f"Cleared {assignment_count} assignments from batch")

    def get_assignment_by_id(self, assignment_id: str) -> Optional[PageAssignment]:
        """Get assignment by ID."""
        return self.assignment_manager.get_assignment(assignment_id)

    def get_assignments_for_file(self, file_id: str) -> List[PageAssignment]:
        """Get all assignments that contain pages from a specific file."""
        assignments = []
        for assignment in self.assignment_manager.assignments.values():
            if file_id in assignment.get_file_ids():
                assignments.append(assignment)
        return assignments

    def set_schema(self, schema: IndexSchema):
        """
        Set the indexing schema for this batch.

        Args:
            schema: Schema to apply
        """
        self.applied_schema = schema

        # Update all existing assignments to use this schema
        for assignment in self.assignment_manager.assignments.values():
            assignment.schema = schema

        self.last_modified = datetime.now()
        logging.info(f"Applied schema '{schema.name}' to batch")

    def validate_assignments(self) -> Dict[str, Any]:
        """
        Validate all assignments in the batch.

        Returns:
            Dictionary with validation results
        """
        results = {
            'is_valid': True,
            'assignment_results': {},
            'batch_errors': [],
            'batch_warnings': [],
            'statistics': {}
        }

        # Validate individual assignments
        assignment_results = self.assignment_manager.validate_all_assignments()
        results['assignment_results'] = assignment_results

        # Check batch-level issues
        batch_errors = []
        batch_warnings = []

        # Check if we have any assignments
        if not self.assignment_manager.assignments:
            batch_warnings.append("Batch has no page assignments")

        # Check for unassigned pages
        unassigned_count = self.unassigned_page_count
        if unassigned_count > 0:
            batch_warnings.append(f"{unassigned_count} pages are not assigned to any document")

        # Check for filename conflicts
        filename_conflicts = self.assignment_manager.get_filename_conflicts()
        for conflict in filename_conflicts:
            batch_errors.append(f"Filename conflict between assignments {conflict[0]} and {conflict[1]}: {conflict[2]}")

        # Check schema consistency
        if not self.applied_schema:
            batch_errors.append("No schema applied to batch")

        # Overall validation status
        has_assignment_errors = any(not valid for valid, _, _ in assignment_results.values())
        results['is_valid'] = not batch_errors and not has_assignment_errors
        results['batch_errors'] = batch_errors
        results['batch_warnings'] = batch_warnings

        # Calculate statistics
        valid_assignments = sum(1 for valid, _, _ in assignment_results.values() if valid)
        total_errors = len(batch_errors) + sum(len(errors) for _, errors, _ in assignment_results.values())
        total_warnings = len(batch_warnings) + sum(len(warnings) for _, _, warnings in assignment_results.values())

        results['statistics'] = {
            'total_assignments': len(assignment_results),
            'valid_assignments': valid_assignments,
            'invalid_assignments': len(assignment_results) - valid_assignments,
            'total_errors': total_errors,
            'total_warnings': total_warnings,
            'unassigned_pages': unassigned_count,
            'filename_conflicts': len(filename_conflicts)
        }

        # Cache results
        self._validation_results = results

        return results

    def preview_output_structure(self) -> Dict[str, Any]:
        """
        Generate a preview of the output folder structure.

        Returns:
            Dictionary representing the folder structure
        """
        structure = {
            'folders': defaultdict(list),
            'files': [],
            'statistics': {
                'total_documents': 0,
                'total_folders': 0,
                'estimated_size': 0
            }
        }

        for assignment in self.assignment_manager.assignments.values():
            if not assignment.is_valid:
                continue

            try:
                preview = assignment.generate_document_preview()

                # Add to structure
                folder_path = preview.folder_path or "Root"
                structure['folders'][folder_path].append({
                    'filename': f"{preview.filename}.pdf",
                    'page_count': preview.page_count,
                    'estimated_size': preview.estimated_file_size,
                    'assignment_id': assignment.assignment_id
                })

                structure['files'].append({
                    'full_path': str(preview.get_full_path()),
                    'folder': folder_path,
                    'filename': f"{preview.filename}.pdf",
                    'page_count': preview.page_count,
                    'estimated_size': preview.estimated_file_size
                })

                structure['statistics']['total_documents'] += 1
                structure['statistics']['estimated_size'] += preview.estimated_file_size

            except Exception as e:
                logging.warning(f"Could not generate preview for assignment {assignment.assignment_id}: {e}")

        structure['statistics']['total_folders'] = len(structure['folders'])

        return structure

    def calculate_output_statistics(self) -> Dict[str, Any]:
        """
        Calculate statistics about the output that will be generated.

        Returns:
            Dictionary with output statistics
        """
        stats = {
            'document_count': 0,
            'total_pages': 0,
            'estimated_total_size': 0,
            'folder_count': 0,
            'average_pages_per_document': 0,
            'largest_document_pages': 0,
            'smallest_document_pages': 0,
            'files_by_folder': {},
            'page_distribution': defaultdict(int)
        }

        page_counts = []
        folders = set()

        for assignment in self.assignment_manager.assignments.values():
            if not assignment.is_valid:
                continue

            try:
                preview = assignment.generate_document_preview()

                stats['document_count'] += 1
                stats['total_pages'] += preview.page_count
                stats['estimated_total_size'] += preview.estimated_file_size

                page_counts.append(preview.page_count)

                folder_path = preview.folder_path or "Root"
                folders.add(folder_path)

                if folder_path not in stats['files_by_folder']:
                    stats['files_by_folder'][folder_path] = 0
                stats['files_by_folder'][folder_path] += 1

                # Page distribution (for histogram)
                page_range = self._get_page_range(preview.page_count)
                stats['page_distribution'][page_range] += 1

            except Exception as e:
                logging.warning(f"Could not calculate stats for assignment {assignment.assignment_id}: {e}")

        # Calculate derived statistics
        if page_counts:
            stats['average_pages_per_document'] = sum(page_counts) / len(page_counts)
            stats['largest_document_pages'] = max(page_counts)
            stats['smallest_document_pages'] = min(page_counts)

        stats['folder_count'] = len(folders)

        return stats

    def _get_page_range(self, page_count: int) -> str:
        """Get page count range for distribution statistics."""
        if page_count == 1:
            return "1 page"
        elif page_count <= 5:
            return "2-5 pages"
        elif page_count <= 10:
            return "6-10 pages"
        elif page_count <= 25:
            return "11-25 pages"
        elif page_count <= 50:
            return "26-50 pages"
        else:
            return "50+ pages"

    def get_processing_summary(self) -> Dict[str, Any]:
        """
        Get summary information for processing operations.

        Returns:
            Dictionary with processing summary
        """
        validation_results = self.validate_assignments()
        output_stats = self.calculate_output_statistics()

        return {
            'batch_id': self.batch_id,
            'batch_name': self.description or f"Batch {self.batch_id[:8]}",
            'created': self.batch_timestamp,
            'last_modified': self.last_modified,
            'schema_name': self.applied_schema.name if self.applied_schema else None,

            # File and page statistics
            'input_files': len(self.scanned_files),
            'input_pages': self.total_pages,
            'output_documents': output_stats['document_count'],
            'output_pages': output_stats['total_pages'],
            'unassigned_pages': self.unassigned_page_count,

            # Validation status
            'is_ready_for_processing': validation_results['is_valid'],
            'validation_errors': len(validation_results['batch_errors']),
            'validation_warnings': len(validation_results['batch_warnings']),

            # Size estimates
            'estimated_output_size': output_stats['estimated_total_size'],
            'estimated_processing_time': self._estimate_processing_time(),

            # Organization
            'output_folders': output_stats['folder_count'],
            'average_pages_per_document': round(output_stats['average_pages_per_document'], 1)
        }

    def _estimate_processing_time(self) -> float:
        """Estimate processing time in seconds."""
        base_time = 5.0  # Base processing overhead
        page_processing_time = self.total_pages * 0.5  # ~0.5 seconds per page
        file_processing_time = len(self.scanned_files) * 2.0  # ~2 seconds per file
        assignment_time = len(self.assignment_manager.assignments) * 1.0  # ~1 second per assignment

        return base_time + page_processing_time + file_processing_time + assignment_time

    def _invalidate_cache(self):
        """Invalidate cached properties."""
        self._total_pages = None
        self._validation_results = None

    def cleanup_temp_files(self):
        """Clean up any temporary files associated with this batch."""
        if self.staging_directory and self.staging_directory.exists():
            try:
                import shutil
                # Remove staging directory
                shutil.rmtree(self.staging_directory)
                logging.info(f"Cleaned up staging directory: {self.staging_directory}")
            except Exception as e:
                logging.warning(f"Failed to clean up staging directory: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize batch to dictionary."""
        return {
            'batch_id': self.batch_id,
            'staging_directory': str(self.staging_directory) if self.staging_directory else None,
            'batch_timestamp': self.batch_timestamp.isoformat(),
            'last_modified': self.last_modified.isoformat(),
            'created_by': self.created_by,
            'description': self.description,
            'processing_state': self.processing_state.name,
            'applied_schema_name': self.applied_schema.name if self.applied_schema else None,
            'scanned_files': [
                {
                    'file_id': f.file_id,
                    'file_path': str(f.file_path),
                    'page_count': f.page_count,
                    'file_size': f.file_size
                }
                for f in self.scanned_files
            ],
            'assignments': [
                assignment.to_dict()
                for assignment in self.assignment_manager.assignments.values()
            ],
            'statistics': {
                'total_pages': self.total_pages,
                'unassigned_pages': self.unassigned_page_count,
                'assignment_count': self.assignment_count,
                'file_count': self.file_count
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], schema: Optional[IndexSchema] = None) -> 'DocumentBatch':
        """
        Create batch from dictionary.

        Args:
            data: Serialized batch data
            schema: Schema to apply (optional)

        Returns:
            Reconstructed DocumentBatch
        """
        staging_dir = Path(data['staging_directory']) if data.get('staging_directory') else None
        batch = cls(data['batch_id'], staging_dir)

        # Load metadata
        batch.batch_timestamp = datetime.fromisoformat(data['batch_timestamp'])
        batch.last_modified = datetime.fromisoformat(data['last_modified'])
        batch.created_by = data.get('created_by', '')
        batch.description = data.get('description', '')

        # Load processing state
        if 'processing_state' in data:
            batch.processing_state = ProcessingState[data['processing_state']]

        # Set schema
        if schema:
            batch.set_schema(schema)

        # Note: File and assignment loading would require additional context
        # This would typically be handled by a batch manager that has access
        # to the file system and schema registry

        return batch

    def create_backup(self, backup_path: Path) -> bool:
        """
        Create a backup of the batch data.

        Args:
            backup_path: Path for backup file

        Returns:
            bool: True if backup created successfully
        """
        try:
            import json

            backup_data = self.to_dict()
            backup_data['backup_created'] = datetime.now().isoformat()
            backup_data['backup_version'] = '1.0'

            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2)

            logging.info(f"Created batch backup: {backup_path}")
            return True

        except Exception as e:
            logging.error(f"Failed to create backup: {e}")
            return False

    def __str__(self) -> str:
        return (f"DocumentBatch({self.file_count} files, {self.total_pages} pages, "
                f"{self.assignment_count} assignments)")

    def __repr__(self) -> str:
        return (f"DocumentBatch(id='{self.batch_id[:8]}...', files={self.file_count}, "
                f"assignments={self.assignment_count}, state={self.processing_state.name})")


class BatchManager:
    """
    Manages multiple document batches and provides batch-level operations.
    """

    def __init__(self):
        self.batches: Dict[str, DocumentBatch] = {}
        self.active_batch_id: Optional[str] = None

    def create_batch(self, staging_directory: Optional[Path] = None,
                     description: str = "") -> DocumentBatch:
        """Create a new document batch."""
        batch = DocumentBatch(staging_directory=staging_directory)
        batch.description = description

        self.batches[batch.batch_id] = batch
        self.active_batch_id = batch.batch_id

        logging.info(f"Created new batch: {batch.batch_id}")
        return batch

    def get_batch(self, batch_id: str) -> Optional[DocumentBatch]:
        """Get a batch by ID."""
        return self.batches.get(batch_id)

    def get_active_batch(self) -> Optional[DocumentBatch]:
        """Get the currently active batch."""
        if self.active_batch_id:
            return self.batches.get(self.active_batch_id)
        return None

    def set_active_batch(self, batch_id: str) -> bool:
        """Set the active batch. Returns True if batch exists."""
        if batch_id in self.batches:
            self.active_batch_id = batch_id
            return True
        return False

    def remove_batch(self, batch_id: str) -> bool:
        """Remove a batch. Returns True if found and removed."""
        if batch_id in self.batches:
            batch = self.batches[batch_id]
            batch.cleanup_temp_files()
            del self.batches[batch_id]

            if self.active_batch_id == batch_id:
                self.active_batch_id = None

            logging.info(f"Removed batch: {batch_id}")
            return True
        return False

    def get_batch_list(self) -> List[Dict[str, Any]]:
        """Get summary information for all batches."""
        return [
            {
                'batch_id': batch.batch_id,
                'description': batch.description or f"Batch {batch.batch_id[:8]}",
                'created': batch.batch_timestamp,
                'modified': batch.last_modified,
                'file_count': batch.file_count,
                'page_count': batch.total_pages,
                'assignment_count': batch.assignment_count,
                'processing_state': batch.processing_state.name,
                'is_active': batch.batch_id == self.active_batch_id
            }
            for batch in self.batches.values()
        ]

    def cleanup_all_batches(self):
        """Clean up temporary files for all batches."""
        for batch in self.batches.values():
            batch.cleanup_temp_files()

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics across all managed batches."""
        total_batches = len(self.batches)
        total_files = sum(batch.file_count for batch in self.batches.values())
        total_pages = sum(batch.total_pages for batch in self.batches.values())
        total_assignments = sum(batch.assignment_count for batch in self.batches.values())

        return {
            'total_batches': total_batches,
            'total_files': total_files,
            'total_pages': total_pages,
            'total_assignments': total_assignments,
            'active_batch_id': self.active_batch_id,
            'batches_by_state': {
                state.name: len([b for b in self.batches.values() if b.processing_state == state])
                for state in ProcessingState
            }
        }