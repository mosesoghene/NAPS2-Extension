"""
High-level document batch processing orchestration.

Manages the complete workflow from document batches to organized output files,
including validation, processing, and export operations.
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
import json

from PySide6.QtCore import QObject, QThread, QMutex, QMutexLocker, Signal, QTimer

from ..core.exceptions import ExportError, PDFProcessingError, AssignmentConflictError
from ..core.signals import app_signals
from ..models.batch import DocumentBatch
from ..models.assignment import PageAssignment
from ..models.enums import ProcessingState, ConflictResolution, PDFQuality
from .pdf_utils import PDFProcessor
from ..utils.validation import ValidationEngine


class ProcessingResult:
    """Represents the result of processing a single assignment."""

    def __init__(self, assignment_id: str, success: bool, output_path: Path = None,
                 error_message: str = None, page_count: int = 0):
        self.assignment_id = assignment_id
        self.success = success
        self.output_path = output_path
        self.error_message = error_message
        self.page_count = page_count
        self.processing_time = 0.0
        self.file_size = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            'assignment_id': self.assignment_id,
            'success': self.success,
            'output_path': str(self.output_path) if self.output_path else None,
            'error_message': self.error_message,
            'page_count': self.page_count,
            'processing_time': self.processing_time,
            'file_size': self.file_size
        }


class BatchProcessingResult:
    """Represents the result of processing an entire batch."""

    def __init__(self, batch_id: str):
        self.batch_id = batch_id
        self.started_at = datetime.now()
        self.completed_at: Optional[datetime] = None
        self.assignment_results: List[ProcessingResult] = []
        self.total_assignments = 0
        self.successful_assignments = 0
        self.failed_assignments = 0
        self.total_pages_processed = 0
        self.total_output_size = 0
        self.output_directory: Optional[Path] = None
        self.summary_file: Optional[Path] = None

    @property
    def processing_time(self) -> float:
        """Get total processing time in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def success_rate(self) -> float:
        """Get success rate as percentage."""
        if self.total_assignments == 0:
            return 0.0
        return (self.successful_assignments / self.total_assignments) * 100

    def add_result(self, result: ProcessingResult):
        """Add assignment processing result."""
        self.assignment_results.append(result)

        if result.success:
            self.successful_assignments += 1
            self.total_pages_processed += result.page_count
            self.total_output_size += result.file_size
        else:
            self.failed_assignments += 1

    def complete(self):
        """Mark batch processing as complete."""
        self.completed_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            'batch_id': self.batch_id,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'processing_time': self.processing_time,
            'total_assignments': self.total_assignments,
            'successful_assignments': self.successful_assignments,
            'failed_assignments': self.failed_assignments,
            'success_rate': self.success_rate,
            'total_pages_processed': self.total_pages_processed,
            'total_output_size': self.total_output_size,
            'output_directory': str(self.output_directory) if self.output_directory else None,
            'assignment_results': [result.to_dict() for result in self.assignment_results]
        }


class DocumentProcessor(QObject):
    """High-level document batch processing orchestration."""

    # Signals
    processing_started = Signal(str)  # batch_id
    processing_progress = Signal(int, str)  # progress_percent, status_message
    assignment_processed = Signal(str, bool, str)  # assignment_id, success, message
    processing_completed = Signal(object)  # BatchProcessingResult
    processing_error = Signal(str)  # error_message
    processing_cancelled = Signal()

    def __init__(self, temp_directory: Path, max_workers: int = 4):
        super().__init__()

        self.temp_directory = Path(temp_directory)
        self.temp_directory.mkdir(parents=True, exist_ok=True)

        # Core components
        self.pdf_processor = PDFProcessor(self.temp_directory)
        self.validation_engine = ValidationEngine()
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)

        # Processing state
        self.current_batch: Optional[DocumentBatch] = None
        self.current_result: Optional[BatchProcessingResult] = None
        self.is_processing = False
        self.should_cancel = False

        # Configuration
        self.max_workers = max_workers
        self.conflict_resolution = ConflictResolution.PROMPT_USER
        self.pdf_quality = PDFQuality.MEDIUM
        self.preserve_timestamps = True
        self.create_summary = True
        self.cleanup_temp_files = True

        # Thread safety
        self.processing_lock = QMutex()

        # Progress tracking
        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self._emit_progress_update)

        logging.debug(f"DocumentProcessor initialized with {max_workers} workers")

    def process_batch(self, batch: DocumentBatch, output_directory: Path,
                      processing_options: Dict[str, Any] = None) -> bool:
        """
        Process a document batch asynchronously.

        Args:
            batch: DocumentBatch to process
            output_directory: Output directory for processed files
            processing_options: Optional processing configuration

        Returns:
            bool: True if processing started successfully
        """
        try:
            with QMutexLocker(self.processing_lock):
                if self.is_processing:
                    logging.warning("Processing already in progress")
                    return False

                self.is_processing = True
                self.should_cancel = False

            # Apply processing options
            if processing_options:
                self._apply_processing_options(processing_options)

            # Validate batch before processing
            is_valid, validation_errors = self.validation_engine.validate_batch_assignments(batch)
            if not is_valid:
                error_msg = f"Batch validation failed: {len(validation_errors)} errors"
                logging.error(error_msg)
                self.processing_error.emit(error_msg)
                self.is_processing = False
                return False

            # Initialize processing result
            self.current_batch = batch
            self.current_result = BatchProcessingResult(batch.batch_id)
            self.current_result.total_assignments = len(batch.assignment_manager.assignments)
            self.current_result.output_directory = output_directory

            # Update batch state
            batch.processing_state = ProcessingState.PREPARING

            # Start processing in thread pool
            future = self.thread_pool.submit(self._process_batch_internal, batch, output_directory)

            # Emit started signal
            self.processing_started.emit(batch.batch_id)
            app_signals.processing_started.emit(batch)

            # Start progress timer
            self.progress_timer.start(1000)  # Update every second

            logging.info(f"Started processing batch {batch.batch_id}")
            return True

        except Exception as e:
            error_msg = f"Failed to start batch processing: {e}"
            logging.error(error_msg)
            self.processing_error.emit(error_msg)
            self.is_processing = False
            return False

    def _process_batch_internal(self, batch: DocumentBatch, output_directory: Path):
        """Internal batch processing implementation."""
        try:
            output_directory = Path(output_directory)
            output_directory.mkdir(parents=True, exist_ok=True)

            batch.processing_state = ProcessingState.PROCESSING

            # Process each assignment
            assignments = list(batch.assignment_manager.assignments.values())

            for i, assignment in enumerate(assignments):
                if self.should_cancel:
                    break

                try:
                    result = self._process_single_assignment(assignment, output_directory)
                    self.current_result.add_result(result)

                    # Emit assignment completed signal
                    success_msg = "Success" if result.success else result.error_message
                    self.assignment_processed.emit(assignment.assignment_id, result.success, success_msg)

                except Exception as e:
                    error_result = ProcessingResult(assignment.assignment_id, False, error_message=str(e))
                    self.current_result.add_result(error_result)
                    self.assignment_processed.emit(assignment.assignment_id, False, str(e))

                # Update progress
                progress = int(((i + 1) / len(assignments)) * 100)
                app_signals.processing_progress.emit(progress, f"Processed {i + 1} of {len(assignments)} assignments")

            # Generate summary if requested
            if self.create_summary and not self.should_cancel:
                self._create_processing_summary(output_directory)

            # Complete processing
            batch.processing_state = ProcessingState.COMPLETED if not self.should_cancel else ProcessingState.CANCELLED
            self.current_result.complete()

            # Stop progress timer
            self.progress_timer.stop()

            # Emit completion signal
            if self.should_cancel:
                self.processing_cancelled.emit()
                app_signals.processing_cancelled.emit()
            else:
                self.processing_completed.emit(self.current_result)
                app_signals.processing_completed.emit(self.current_result.to_dict())

            logging.info(
                f"Batch processing completed: {self.current_result.successful_assignments}/{self.current_result.total_assignments} successful")

        except Exception as e:
            error_msg = f"Batch processing failed: {e}"
            logging.error(error_msg)
            batch.processing_state = ProcessingState.ERROR
            self.processing_error.emit(error_msg)
            app_signals.processing_error.emit(error_msg)

        finally:
            # Cleanup
            if self.cleanup_temp_files:
                self._cleanup_temp_files()

            with QMutexLocker(self.processing_lock):
                self.is_processing = False
                self.current_batch = None

    def _process_single_assignment(self, assignment: PageAssignment, output_directory: Path) -> ProcessingResult:
        """Process a single page assignment."""
        start_time = datetime.now()

        try:
            logging.debug(f"Processing assignment {assignment.assignment_id}")

            # Generate output paths
            preview = assignment.generate_document_preview()
            relative_path = preview.get_full_path()
            output_file = output_directory / relative_path

            # Ensure output directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Handle file conflicts
            if output_file.exists():
                output_file = self._handle_file_conflict(output_file, assignment.assignment_id)

            # Collect page references for merging
            page_references = []
            for page_ref in assignment.page_references:
                # Get the actual file path for this page reference
                file_path = self._get_file_path_for_page_reference(page_ref)
                if file_path and file_path.exists():
                    page_references.append((str(file_path), page_ref.page_number))
                else:
                    raise PDFProcessingError(f"Source file not found for page reference: {page_ref}")

            if not page_references:
                raise PDFProcessingError("No valid page references found for assignment")

            # Merge pages into output file
            success = self.pdf_processor.merge_pages(page_references, output_file)

            if not success:
                raise PDFProcessingError("PDF merging failed")

            # Add metadata if available
            if assignment.index_values:
                metadata = self._generate_pdf_metadata(assignment)
                self.pdf_processor.add_metadata(output_file, metadata)

            # Set file timestamp if requested
            if self.preserve_timestamps and assignment.created_timestamp:
                self._set_file_timestamp(output_file, assignment.created_timestamp)

            # Calculate processing stats
            processing_time = (datetime.now() - start_time).total_seconds()
            file_size = output_file.stat().st_size if output_file.exists() else 0

            result = ProcessingResult(
                assignment.assignment_id,
                True,
                output_file,
                page_count=len(assignment.page_references),
            )
            result.processing_time = processing_time
            result.file_size = file_size

            logging.info(f"Successfully processed assignment {assignment.assignment_id}: {output_file}")
            return result

        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"Failed to process assignment {assignment.assignment_id}: {e}"
            logging.error(error_msg)

            result = ProcessingResult(assignment.assignment_id, False, error_message=str(e))
            result.processing_time = processing_time
            return result

    def _get_file_path_for_page_reference(self, page_ref) -> Optional[Path]:
        """Get file path for a page reference from current batch."""
        if not self.current_batch:
            return None

        scanned_file = self.current_batch.get_file_by_id(page_ref.file_id)
        return scanned_file.file_path if scanned_file else None

    def _handle_file_conflict(self, output_file: Path, assignment_id: str) -> Path:
        """Handle file naming conflicts based on resolution strategy."""
        if self.conflict_resolution == ConflictResolution.OVERWRITE:
            return output_file

        elif self.conflict_resolution == ConflictResolution.AUTO_RENAME:
            # Find available filename with suffix
            counter = 1
            while output_file.exists():
                stem = output_file.stem
                suffix = output_file.suffix
                parent = output_file.parent
                output_file = parent / f"{stem}_{counter}{suffix}"
                counter += 1
            return output_file

        elif self.conflict_resolution == ConflictResolution.SKIP_DUPLICATE:
            raise AssignmentConflictError(f"File already exists: {output_file}")

        else:  # PROMPT_USER - for now, auto-rename
            return self._handle_file_conflict(output_file, assignment_id)

    def _generate_pdf_metadata(self, assignment: PageAssignment) -> Dict[str, str]:
        """Generate PDF metadata from assignment values."""
        metadata = {
            '/Title': assignment.get_index_value('title') or assignment.output_filename,
            '/Creator': 'Scanner Extension',
            '/Producer': 'Scanner Extension Document Processor',
            '/CreationDate': datetime.now().strftime("D:%Y%m%d%H%M%S"),
        }

        # Add custom metadata from index values
        for field_name, value in assignment.index_values.items():
            if value and value.strip():
                # Clean field name for metadata key
                clean_name = field_name.replace(' ', '_').replace('-', '_')
                metadata[f'/Custom_{clean_name}'] = value.strip()

        return metadata

    def _set_file_timestamp(self, file_path: Path, timestamp: datetime):
        """Set file creation and modification timestamps."""
        try:
            import os
            timestamp_seconds = timestamp.timestamp()
            os.utime(file_path, (timestamp_seconds, timestamp_seconds))
        except Exception as e:
            logging.warning(f"Could not set timestamp for {file_path}: {e}")

    def _create_processing_summary(self, output_directory: Path):
        """Create processing summary file."""
        try:
            summary_file = output_directory / "processing_summary.json"

            summary_data = {
                'processing_summary': self.current_result.to_dict(),
                'batch_info': {
                    'batch_id': self.current_batch.batch_id,
                    'description': self.current_batch.description,
                    'total_input_files': len(self.current_batch.scanned_files),
                    'total_input_pages': self.current_batch.total_pages,
                    'schema_name': self.current_batch.applied_schema.name if self.current_batch.applied_schema else None
                },
                'processing_settings': {
                    'pdf_quality': self.pdf_quality.value,
                    'conflict_resolution': self.conflict_resolution.value,
                    'preserve_timestamps': self.preserve_timestamps,
                    'max_workers': self.max_workers
                }
            }

            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)

            self.current_result.summary_file = summary_file
            logging.info(f"Created processing summary: {summary_file}")

        except Exception as e:
            logging.warning(f"Failed to create processing summary: {e}")

    def _cleanup_temp_files(self):
        """Clean up temporary files created during processing."""
        try:
            temp_dirs = [
                self.temp_directory / "thumbnails",
                self.temp_directory / "staging",
                self.temp_directory / "temp_pdfs"
            ]

            for temp_dir in temp_dirs:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)

            logging.debug("Cleaned up temporary processing files")

        except Exception as e:
            logging.warning(f"Error cleaning up temp files: {e}")

    def _apply_processing_options(self, options: Dict[str, Any]):
        """Apply processing options from configuration."""
        if 'conflict_resolution' in options:
            self.conflict_resolution = ConflictResolution(options['conflict_resolution'])

        if 'pdf_quality' in options:
            self.pdf_quality = PDFQuality(options['pdf_quality'])

        if 'preserve_timestamps' in options:
            self.preserve_timestamps = bool(options['preserve_timestamps'])

        if 'create_summary' in options:
            self.create_summary = bool(options['create_summary'])

        if 'cleanup_temp_files' in options:
            self.cleanup_temp_files = bool(options['cleanup_temp_files'])

        if 'max_workers' in options:
            new_workers = int(options['max_workers'])
            if new_workers != self.max_workers:
                self.max_workers = new_workers
                # Recreate thread pool with new worker count
                self.thread_pool.shutdown(wait=False)
                self.thread_pool = ThreadPoolExecutor(max_workers=new_workers)

    def _emit_progress_update(self):
        """Emit periodic progress updates."""
        if not self.is_processing or not self.current_result:
            return

        try:
            completed = len(self.current_result.assignment_results)
            total = self.current_result.total_assignments

            if total > 0:
                progress = int((completed / total) * 100)
                status = f"Processing: {completed}/{total} assignments"
                self.processing_progress.emit(progress, status)

        except Exception as e:
            logging.debug(f"Error emitting progress update: {e}")

    def cancel_processing(self) -> bool:
        """Cancel current processing operation."""
        try:
            if not self.is_processing:
                return False

            logging.info("Cancelling document processing...")
            self.should_cancel = True

            if self.current_batch:
                self.current_batch.processing_state = ProcessingState.CANCELLED

            return True

        except Exception as e:
            logging.error(f"Error cancelling processing: {e}")
            return False

    def get_processing_status(self) -> Dict[str, Any]:
        """Get current processing status."""
        with QMutexLocker(self.processing_lock):
            status = {
                'is_processing': self.is_processing,
                'should_cancel': self.should_cancel,
                'current_batch_id': self.current_batch.batch_id if self.current_batch else None,
                'max_workers': self.max_workers
            }

            if self.current_result:
                status.update({
                    'total_assignments': self.current_result.total_assignments,
                    'completed_assignments': len(self.current_result.assignment_results),
                    'successful_assignments': self.current_result.successful_assignments,
                    'failed_assignments': self.current_result.failed_assignments,
                    'processing_time': self.current_result.processing_time,
                    'success_rate': self.current_result.success_rate
                })

            return status

    def shutdown(self):
        """Shutdown document processor and cleanup resources."""
        try:
            logging.info("Shutting down document processor...")

            # Cancel any ongoing processing
            self.cancel_processing()

            # Stop timers
            if self.progress_timer.isActive():
                self.progress_timer.stop()

            # Shutdown thread pool
            self.thread_pool.shutdown(wait=True, timeout=30)

            # Final cleanup
            if self.cleanup_temp_files:
                self._cleanup_temp_files()

            logging.info("Document processor shutdown complete")

        except Exception as e:
            logging.error(f"Error during document processor shutdown: {e}")

    def __del__(self):
        """Destructor - ensure proper cleanup."""
        self.shutdown()