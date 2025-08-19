"""
Scanned file representation and PDF handling.

Represents individual PDF files from NAPS2 with metadata, thumbnail generation,
and page manipulation capabilities.
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, Tuple, List
import uuid

from ..core.exceptions import FileProcessingError, PDFProcessingError
from .enums import ThumbnailSize, FileFormat


class ScannedFile:
    """
    Represents a single PDF file from NAPS2.

    Provides access to file metadata, page information, thumbnail generation,
    and page extraction capabilities.
    """

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self.file_id = str(uuid.uuid4())

        # Cache properties
        self._page_count: Optional[int] = None
        self._file_size: Optional[int] = None
        self._scan_timestamp: Optional[datetime] = None
        self._file_hash: Optional[str] = None
        self._pdf_metadata: Optional[Dict[str, Any]] = None

        # Thumbnail cache: page_number -> thumbnail_path
        self.thumbnail_cache: Dict[int, Path] = {}

        # State tracking
        self.is_corrupted = False
        self._metadata_loaded = False

        # Validate file exists and is accessible
        if not self.file_path.exists():
            raise FileProcessingError(f"File not found: {file_path}")

        if not self.file_path.is_file():
            raise FileProcessingError(f"Path is not a file: {file_path}")

        # Initial validation
        try:
            self._validate_pdf()
        except Exception as e:
            logging.warning(f"PDF validation failed for {file_path}: {e}")
            self.is_corrupted = True

    def _validate_pdf(self):
        """Validate that the file is a readable PDF."""
        # Check file extension
        if self.file_path.suffix.lower() != '.pdf':
            raise PDFProcessingError("File is not a PDF", str(self.file_path))

        # Try to read basic PDF information
        # This will be implemented when we add PDF processing utilities
        # For now, we'll do basic file size check
        if self.file_path.stat().st_size < 100:  # Less than 100 bytes is suspicious
            raise PDFProcessingError("PDF file appears to be corrupted or empty", str(self.file_path))

    @property
    def page_count(self) -> int:
        """Get the number of pages in this PDF."""
        if self._page_count is None:
            self._load_pdf_metadata()
        return self._page_count or 0

    @property
    def file_size(self) -> int:
        """Get file size in bytes."""
        if self._file_size is None:
            try:
                self._file_size = self.file_path.stat().st_size
            except OSError as e:
                raise FileProcessingError(f"Cannot access file size: {e}", str(self.file_path))
        return self._file_size

    @property
    def scan_timestamp(self) -> datetime:
        """Get the file creation/modification timestamp."""
        if self._scan_timestamp is None:
            try:
                stat = self.file_path.stat()
                # Use creation time if available (Windows), otherwise modification time
                timestamp = getattr(stat, 'st_birthtime', None) or stat.st_mtime
                self._scan_timestamp = datetime.fromtimestamp(timestamp)
            except OSError as e:
                raise FileProcessingError(f"Cannot access file timestamp: {e}", str(self.file_path))
        return self._scan_timestamp

    @property
    def pdf_metadata(self) -> Dict[str, Any]:
        """Get PDF metadata dictionary."""
        if self._pdf_metadata is None:
            self._load_pdf_metadata()
        return self._pdf_metadata or {}

    def _load_pdf_metadata(self):
        """Load PDF metadata including page count."""
        if self.is_corrupted or self._metadata_loaded:
            return

        try:
            # This will be implemented when we add PDF utilities
            # For now, provide basic fallback
            self._pdf_metadata = {
                'title': self.file_path.stem,
                'creator': 'NAPS2',
                'creation_date': self.scan_timestamp,
                'file_size': self.file_size
            }

            # Estimate page count based on file size as fallback
            # This is very rough - real implementation will use PDF library
            estimated_pages = max(1, self.file_size // 50000)  # ~50KB per page estimate
            self._page_count = min(estimated_pages, 100)  # Cap at reasonable limit

            self._metadata_loaded = True

        except Exception as e:
            logging.error(f"Failed to load PDF metadata for {self.file_path}: {e}")
            self.is_corrupted = True
            self._pdf_metadata = {}
            self._page_count = 0

    def get_file_hash(self) -> str:
        """Generate unique hash for file identification."""
        if self._file_hash is None:
            try:
                hasher = hashlib.md5()
                with open(self.file_path, 'rb') as f:
                    # Read in chunks for memory efficiency
                    for chunk in iter(lambda: f.read(8192), b""):
                        hasher.update(chunk)
                self._file_hash = hasher.hexdigest()
            except IOError as e:
                raise FileProcessingError(f"Cannot read file for hashing: {e}", str(self.file_path))
        return self._file_hash

    def is_valid_pdf(self) -> bool:
        """Check if the PDF file is valid and readable."""
        return not self.is_corrupted and self.page_count > 0

    def get_file_metadata(self) -> Dict[str, Any]:
        """Get complete file system metadata."""
        try:
            stat = self.file_path.stat()
            return {
                'file_path': str(self.file_path),
                'file_name': self.file_path.name,
                'file_size': stat.st_size,
                'created': datetime.fromtimestamp(getattr(stat, 'st_birthtime', stat.st_ctime)),
                'modified': datetime.fromtimestamp(stat.st_mtime),
                'accessed': datetime.fromtimestamp(stat.st_atime),
                'is_readonly': not stat.st_mode & 0o200,
                'file_hash': self.get_file_hash(),
                'page_count': self.page_count,
                'is_valid': self.is_valid_pdf()
            }
        except OSError as e:
            raise FileProcessingError(f"Cannot access file metadata: {e}", str(self.file_path))

    def generate_thumbnail(self, page_number: int, size: ThumbnailSize = ThumbnailSize.MEDIUM) -> Optional[Path]:
        """
        Generate thumbnail for a specific page.

        Args:
            page_number: Page number (1-based)
            size: Thumbnail size

        Returns:
            Path to generated thumbnail or None if failed
        """
        # Validate page number
        if page_number < 1 or page_number > self.page_count:
            raise PDFProcessingError(
                f"Page number {page_number} is out of range (1-{self.page_count})",
                str(self.file_path),
                page_number
            )

        # Check cache first
        cache_key = f"{page_number}_{size.value}"
        if cache_key in self.thumbnail_cache:
            thumbnail_path = self.thumbnail_cache[cache_key]
            if thumbnail_path.exists():
                return thumbnail_path

        # Generate new thumbnail
        try:
            # This will be implemented with actual PDF processing
            # For now, return placeholder
            from ..core.application import app_signals

            # Create thumbnail filename
            thumbnail_name = f"{self.file_id}_p{page_number:03d}_{size.width}x{size.height}.png"

            # This would normally generate the actual thumbnail
            # thumbnail_path = self._create_thumbnail(page_number, size, thumbnail_name)

            # Placeholder implementation - signal that thumbnail generation is needed
            app_signals.thumbnail_generation_progress.emit(page_number, self.page_count)

            # Return None for now - real implementation will return actual path
            return None

        except Exception as e:
            logging.error(f"Thumbnail generation failed for {self.file_path} page {page_number}: {e}")
            return None

    def extract_page_range(self, start_page: int, end_page: int, output_file: Path) -> bool:
        """
        Extract a range of pages to a new PDF file.

        Args:
            start_page: First page to extract (1-based)
            end_page: Last page to extract (1-based, inclusive)
            output_file: Path for the output PDF

        Returns:
            bool: True if successful, False otherwise
        """
        # Validate page range
        if start_page < 1 or end_page > self.page_count or start_page > end_page:
            raise PDFProcessingError(
                f"Invalid page range {start_page}-{end_page} for PDF with {self.page_count} pages",
                str(self.file_path)
            )

        try:
            # This will be implemented with actual PDF processing utilities
            # For now, just create a placeholder
            logging.info(f"Would extract pages {start_page}-{end_page} from {self.file_path} to {output_file}")

            # Placeholder - real implementation would use PDF library
            return True

        except Exception as e:
            logging.error(f"Page extraction failed: {e}")
            raise PDFProcessingError(
                f"Failed to extract pages {start_page}-{end_page}: {e}",
                str(self.file_path)
            )

    def refresh_metadata(self):
        """Refresh cached metadata by reloading from file."""
        self._page_count = None
        self._file_size = None
        self._scan_timestamp = None
        self._file_hash = None
        self._pdf_metadata = None
        self._metadata_loaded = False

        # Clear thumbnail cache
        self.thumbnail_cache.clear()

        # Reload
        self._validate_pdf()
        self._load_pdf_metadata()

    def clear_thumbnail_cache(self):
        """Clear the thumbnail cache for this file."""
        self.thumbnail_cache.clear()

    def get_thumbnail_path(self, page_number: int, size: ThumbnailSize) -> Optional[Path]:
        """Get cached thumbnail path if available."""
        cache_key = f"{page_number}_{size.value}"
        return self.thumbnail_cache.get(cache_key)

    def has_thumbnail(self, page_number: int, size: ThumbnailSize) -> bool:
        """Check if thumbnail exists for given page and size."""
        thumbnail_path = self.get_thumbnail_path(page_number, size)
        return thumbnail_path is not None and thumbnail_path.exists()

    def get_page_list(self) -> List[int]:
        """Get list of all page numbers (1-based)."""
        return list(range(1, self.page_count + 1))

    def estimate_extraction_time(self, page_count: int) -> float:
        """Estimate time needed to extract given number of pages (in seconds)."""
        # Very rough estimation based on file size and page count
        base_time = 0.5  # Base processing time
        size_factor = self.file_size / 1_000_000  # Size in MB
        page_factor = page_count * 0.1  # Time per page

        return base_time + (size_factor * 0.1) + page_factor

    def __str__(self) -> str:
        """String representation."""
        return f"ScannedFile({self.file_path.name}, {self.page_count} pages)"

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (f"ScannedFile(path='{self.file_path}', pages={self.page_count}, "
                f"size={self.file_size:,} bytes, valid={self.is_valid_pdf()})")

    def __eq__(self, other) -> bool:
        """Equality comparison based on file hash."""
        if not isinstance(other, ScannedFile):
            return False
        try:
            return self.get_file_hash() == other.get_file_hash()
        except Exception:
            return self.file_path == other.file_path

    def __hash__(self) -> int:
        """Hash based on file ID."""
        return hash(self.file_id)


class ScannedFileFactory:
    """Factory for creating ScannedFile instances with validation."""

    @staticmethod
    def create_from_path(file_path: Path) -> Optional[ScannedFile]:
        """
        Create ScannedFile from path with error handling.

        Args:
            file_path: Path to PDF file

        Returns:
            ScannedFile instance or None if creation failed
        """
        try:
            return ScannedFile(file_path)
        except Exception as e:
            logging.error(f"Failed to create ScannedFile from {file_path}: {e}")
            return None

    @staticmethod
    def create_from_paths(file_paths: List[Path]) -> List[ScannedFile]:
        """
        Create multiple ScannedFile instances, skipping failed ones.

        Args:
            file_paths: List of paths to PDF files

        Returns:
            List of successfully created ScannedFile instances
        """
        scanned_files = []
        for path in file_paths:
            scanned_file = ScannedFileFactory.create_from_path(path)
            if scanned_file:
                scanned_files.append(scanned_file)
        return scanned_files

    @staticmethod
    def validate_pdf_file(file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate a PDF file without creating a full ScannedFile instance.

        Args:
            file_path: Path to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if not file_path.exists():
                return False, "File does not exist"

            if not file_path.is_file():
                return False, "Path is not a file"

            if file_path.suffix.lower() != '.pdf':
                return False, "File is not a PDF"

            if file_path.stat().st_size < 100:
                return False, "File appears to be empty or corrupted"

            return True, None

        except Exception as e:
            return False, str(e)

