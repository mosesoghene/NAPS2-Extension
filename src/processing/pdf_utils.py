"""
PDF manipulation utilities for page extraction and merging.

Provides core PDF processing functionality including page extraction,
merging, thumbnail generation, and metadata handling using PyPDF2.
"""

import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, Union
import hashlib
import io

try:
    import PyPDF2
    from PyPDF2 import PdfReader, PdfWriter
    from PIL import Image
    import fitz  # PyMuPDF for thumbnail generation
except ImportError as e:
    logging.error(f"Required PDF processing libraries not available: {e}")
    raise ImportError("Please install PyPDF2, Pillow, and PyMuPDF")

from ..core.exceptions import PDFProcessingError
from ..core.signals import app_signals


class PDFProcessor:
    """PDF manipulation utilities for page extraction and merging."""

    def __init__(self, temp_directory: Path = None):
        """
        Initialize PDF processor.

        Args:
            temp_directory: Directory for temporary files
        """
        self.temp_directory = temp_directory or Path.cwd() / "temp"
        self.temp_directory.mkdir(exist_ok=True)

        # Default settings
        self.thumbnail_size = (150, 200)
        self.quality_settings = {
            'low': {'dpi': 72, 'quality': 60},
            'medium': {'dpi': 150, 'quality': 80},
            'high': {'dpi': 300, 'quality': 95},
            'original': {'dpi': None, 'quality': 100}
        }
        self.compression_level = 6

        logging.debug(f"PDFProcessor initialized with temp directory: {self.temp_directory}")

    def extract_pages(self, source_file: Union[str, Path], page_numbers: List[int],
                      output_file: Union[str, Path]) -> bool:
        """
        Extract specific pages from a PDF file.

        Args:
            source_file: Path to source PDF file
            page_numbers: List of page numbers to extract (1-based)
            output_file: Path for output PDF file

        Returns:
            bool: True if successful, False otherwise

        Raises:
            PDFProcessingError: If extraction fails
        """
        source_file = Path(source_file)
        output_file = Path(output_file)

        try:
            logging.info(f"Extracting pages {page_numbers} from {source_file.name}")

            if not source_file.exists():
                raise PDFProcessingError(f"Source file not found: {source_file}")

            if not page_numbers:
                raise PDFProcessingError("No page numbers specified for extraction")

            with open(source_file, 'rb') as input_file:
                reader = PdfReader(input_file)
                total_pages = len(reader.pages)

                # Validate page numbers
                invalid_pages = [p for p in page_numbers if p < 1 or p > total_pages]
                if invalid_pages:
                    raise PDFProcessingError(
                        f"Invalid page numbers: {invalid_pages}. PDF has {total_pages} pages"
                    )

                writer = PdfWriter()

                # Add specified pages (convert to 0-based indexing)
                for page_num in sorted(page_numbers):
                    page_index = page_num - 1
                    page = reader.pages[page_index]
                    writer.add_page(page)

                # Ensure output directory exists
                output_file.parent.mkdir(parents=True, exist_ok=True)

                # Write output file
                with open(output_file, 'wb') as output:
                    writer.write(output)

            logging.info(f"Successfully extracted {len(page_numbers)} pages to {output_file.name}")
            return True

        except Exception as e:
            error_msg = f"Failed to extract pages from {source_file.name}: {e}"
            logging.error(error_msg)
            raise PDFProcessingError(error_msg, str(source_file))

    def merge_pages(self, page_references: List[Tuple[str, int]], output_file: Union[str, Path]) -> bool:
        """
        Merge pages from multiple PDF files into a single document.

        Args:
            page_references: List of (file_path, page_number) tuples
            output_file: Path for merged output file

        Returns:
            bool: True if successful, False otherwise

        Raises:
            PDFProcessingError: If merging fails
        """
        output_file = Path(output_file)

        try:
            logging.info(f"Merging {len(page_references)} pages into {output_file.name}")

            if not page_references:
                raise PDFProcessingError("No pages specified for merging")

            writer = PdfWriter()
            processed_files = {}  # Cache opened files

            for file_path, page_number in page_references:
                file_path = Path(file_path)

                if not file_path.exists():
                    raise PDFProcessingError(f"Source file not found: {file_path}")

                # Use cached reader if already opened
                if str(file_path) not in processed_files:
                    with open(file_path, 'rb') as f:
                        reader = PdfReader(f)
                        processed_files[str(file_path)] = reader
                else:
                    reader = processed_files[str(file_path)]

                total_pages = len(reader.pages)
                if page_number < 1 or page_number > total_pages:
                    raise PDFProcessingError(
                        f"Invalid page number {page_number} in {file_path.name}. "
                        f"File has {total_pages} pages"
                    )

                # Add page (convert to 0-based indexing)
                page_index = page_number - 1
                page = reader.pages[page_index]
                writer.add_page(page)

            # Ensure output directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Write merged file
            with open(output_file, 'wb') as output:
                writer.write(output)

            logging.info(f"Successfully merged {len(page_references)} pages")
            return True

        except Exception as e:
            error_msg = f"Failed to merge pages: {e}"
            logging.error(error_msg)
            raise PDFProcessingError(error_msg)

    def get_page_count(self, pdf_file: Union[str, Path]) -> int:
        """
        Get the number of pages in a PDF file.

        Args:
            pdf_file: Path to PDF file

        Returns:
            int: Number of pages

        Raises:
            PDFProcessingError: If file cannot be read
        """
        pdf_file = Path(pdf_file)

        try:
            if not pdf_file.exists():
                raise PDFProcessingError(f"PDF file not found: {pdf_file}")

            with open(pdf_file, 'rb') as f:
                reader = PdfReader(f)
                page_count = len(reader.pages)

            logging.debug(f"PDF {pdf_file.name} has {page_count} pages")
            return page_count

        except Exception as e:
            error_msg = f"Failed to get page count for {pdf_file.name}: {e}"
            logging.error(error_msg)
            raise PDFProcessingError(error_msg, str(pdf_file))

    def generate_page_thumbnail(self, pdf_file: Union[str, Path], page_number: int,
                                size: Tuple[int, int] = None) -> Optional[Path]:
        """
        Generate thumbnail image for a specific PDF page.

        Args:
            pdf_file: Path to PDF file
            page_number: Page number to generate thumbnail for (1-based)
            size: Thumbnail size as (width, height) tuple

        Returns:
            Path: Path to generated thumbnail image, None if failed

        Raises:
            PDFProcessingError: If thumbnail generation fails
        """
        pdf_file = Path(pdf_file)
        size = size or self.thumbnail_size

        try:
            if not pdf_file.exists():
                raise PDFProcessingError(f"PDF file not found: {pdf_file}")

            # Create thumbnail filename
            file_hash = self._get_file_hash(pdf_file)
            thumbnail_name = f"{file_hash}_p{page_number}_{size[0]}x{size[1]}.png"
            thumbnail_path = self.temp_directory / "thumbnails" / thumbnail_name

            # Return existing thumbnail if available
            if thumbnail_path.exists():
                logging.debug(f"Using cached thumbnail: {thumbnail_name}")
                return thumbnail_path

            # Ensure thumbnail directory exists
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate thumbnail using PyMuPDF
            with fitz.open(pdf_file) as doc:
                if page_number < 1 or page_number > len(doc):
                    raise PDFProcessingError(
                        f"Invalid page number {page_number}. PDF has {len(doc)} pages"
                    )

                page = doc[page_number - 1]  # Convert to 0-based index

                # Get page as pixmap
                mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
                pix = page.get_pixmap(matrix=mat)

                # Convert to PIL Image
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data))

                # Resize to target size while maintaining aspect ratio
                image.thumbnail(size, Image.Resampling.LANCZOS)

                # Save thumbnail
                image.save(thumbnail_path, "PNG", optimize=True)

            logging.debug(f"Generated thumbnail: {thumbnail_name}")
            return thumbnail_path

        except Exception as e:
            error_msg = f"Failed to generate thumbnail for {pdf_file.name} page {page_number}: {e}"
            logging.error(error_msg)
            raise PDFProcessingError(error_msg, str(pdf_file), page_number)

    def add_metadata(self, pdf_file: Union[str, Path], metadata: Dict[str, str]) -> bool:
        """
        Add metadata to a PDF file.

        Args:
            pdf_file: Path to PDF file
            metadata: Dictionary of metadata key-value pairs

        Returns:
            bool: True if successful

        Raises:
            PDFProcessingError: If metadata addition fails
        """
        pdf_file = Path(pdf_file)

        try:
            logging.info(f"Adding metadata to {pdf_file.name}")

            if not pdf_file.exists():
                raise PDFProcessingError(f"PDF file not found: {pdf_file}")

            # Create backup
            backup_file = pdf_file.with_suffix(f"{pdf_file.suffix}.backup")

            with open(pdf_file, 'rb') as input_file:
                reader = PdfReader(input_file)
                writer = PdfWriter()

                # Copy all pages
                for page in reader.pages:
                    writer.add_page(page)

                # Add metadata
                writer.add_metadata(metadata)

                # Write to backup first
                with open(backup_file, 'wb') as backup:
                    writer.write(backup)

            # Replace original with backup
            backup_file.replace(pdf_file)

            logging.info(f"Successfully added metadata to {pdf_file.name}")
            return True

        except Exception as e:
            error_msg = f"Failed to add metadata to {pdf_file.name}: {e}"
            logging.error(error_msg)
            raise PDFProcessingError(error_msg, str(pdf_file))

    def validate_pdf(self, pdf_file: Union[str, Path]) -> bool:
        """
        Check if a file is a valid PDF.

        Args:
            pdf_file: Path to PDF file

        Returns:
            bool: True if valid PDF, False otherwise
        """
        pdf_file = Path(pdf_file)

        try:
            if not pdf_file.exists():
                return False

            with open(pdf_file, 'rb') as f:
                reader = PdfReader(f)
                # Try to access pages to verify structure
                _ = len(reader.pages)

            return True

        except Exception as e:
            logging.debug(f"PDF validation failed for {pdf_file.name}: {e}")
            return False

    def get_pdf_info(self, pdf_file: Union[str, Path]) -> Dict[str, Any]:
        """
        Get comprehensive information about a PDF file.

        Args:
            pdf_file: Path to PDF file

        Returns:
            Dict containing PDF information

        Raises:
            PDFProcessingError: If file cannot be read
        """
        pdf_file = Path(pdf_file)

        try:
            if not pdf_file.exists():
                raise PDFProcessingError(f"PDF file not found: {pdf_file}")

            info = {
                'file_path': str(pdf_file),
                'file_size': pdf_file.stat().st_size,
                'is_valid': False,
                'page_count': 0,
                'metadata': {},
                'encrypted': False,
                'file_hash': self._get_file_hash(pdf_file)
            }

            with open(pdf_file, 'rb') as f:
                reader = PdfReader(f)

                info['is_valid'] = True
                info['page_count'] = len(reader.pages)
                info['encrypted'] = reader.is_encrypted

                # Extract metadata
                if reader.metadata:
                    info['metadata'] = {
                        key.lstrip('/'): str(value)
                        for key, value in reader.metadata.items()
                    }

            logging.debug(f"Retrieved PDF info for {pdf_file.name}")
            return info

        except Exception as e:
            error_msg = f"Failed to get PDF info for {pdf_file.name}: {e}"
            logging.error(error_msg)
            raise PDFProcessingError(error_msg, str(pdf_file))

    def rotate_pages(self, pdf_file: Union[str, Path], page_numbers: List[int],
                     degrees: int) -> bool:
        """
        Rotate specific pages in a PDF file.

        Args:
            pdf_file: Path to PDF file
            page_numbers: List of page numbers to rotate (1-based)
            degrees: Rotation degrees (90, 180, 270, or -90, -180, -270)

        Returns:
            bool: True if successful

        Raises:
            PDFProcessingError: If rotation fails
        """
        pdf_file = Path(pdf_file)

        try:
            logging.info(f"Rotating pages {page_numbers} by {degrees}° in {pdf_file.name}")

            if not pdf_file.exists():
                raise PDFProcessingError(f"PDF file not found: {pdf_file}")

            if degrees not in [90, 180, 270, -90, -180, -270]:
                raise PDFProcessingError(f"Invalid rotation degrees: {degrees}")

            # Create backup
            backup_file = pdf_file.with_suffix(f"{pdf_file.suffix}.backup")

            with open(pdf_file, 'rb') as input_file:
                reader = PdfReader(input_file)
                writer = PdfWriter()
                total_pages = len(reader.pages)

                # Validate page numbers
                invalid_pages = [p for p in page_numbers if p < 1 or p > total_pages]
                if invalid_pages:
                    raise PDFProcessingError(f"Invalid page numbers: {invalid_pages}")

                # Process each page
                for i, page in enumerate(reader.pages):
                    page_number = i + 1

                    if page_number in page_numbers:
                        page.rotate(degrees)

                    writer.add_page(page)

                # Write to backup first
                with open(backup_file, 'wb') as backup:
                    writer.write(backup)

            # Replace original with backup
            backup_file.replace(pdf_file)

            logging.info(f"Successfully rotated {len(page_numbers)} pages")
            return True

        except Exception as e:
            error_msg = f"Failed to rotate pages in {pdf_file.name}: {e}"
            logging.error(error_msg)
            raise PDFProcessingError(error_msg, str(pdf_file))

    def split_pdf(self, pdf_file: Union[str, Path], split_points: List[int],
                  output_directory: Union[str, Path]) -> List[Path]:
        """
        Split PDF at specified page numbers.

        Args:
            pdf_file: Path to PDF file
            split_points: List of page numbers where to split (1-based)
            output_directory: Directory for output files

        Returns:
            List[Path]: List of created PDF files

        Raises:
            PDFProcessingError: If splitting fails
        """
        pdf_file = Path(pdf_file)
        output_directory = Path(output_directory)

        try:
            logging.info(f"Splitting {pdf_file.name} at pages {split_points}")

            if not pdf_file.exists():
                raise PDFProcessingError(f"PDF file not found: {pdf_file}")

            output_directory.mkdir(parents=True, exist_ok=True)

            with open(pdf_file, 'rb') as input_file:
                reader = PdfReader(input_file)
                total_pages = len(reader.pages)

                # Validate split points
                invalid_points = [p for p in split_points if p < 1 or p > total_pages]
                if invalid_points:
                    raise PDFProcessingError(f"Invalid split points: {invalid_points}")

                # Create split ranges
                split_points_sorted = sorted(set([1] + split_points + [total_pages + 1]))
                output_files = []

                base_name = pdf_file.stem

                for i in range(len(split_points_sorted) - 1):
                    start_page = split_points_sorted[i]
                    end_page = split_points_sorted[i + 1] - 1

                    if start_page <= end_page:
                        output_file = output_directory / f"{base_name}_part{i + 1}.pdf"
                        writer = PdfWriter()

                        # Add pages to this part
                        for page_num in range(start_page, end_page + 1):
                            page_index = page_num - 1
                            writer.add_page(reader.pages[page_index])

                        # Write part file
                        with open(output_file, 'wb') as output:
                            writer.write(output)

                        output_files.append(output_file)

            logging.info(f"Successfully split PDF into {len(output_files)} parts")
            return output_files

        except Exception as e:
            error_msg = f"Failed to split {pdf_file.name}: {e}"
            logging.error(error_msg)
            raise PDFProcessingError(error_msg, str(pdf_file))

    def _get_file_hash(self, file_path: Path) -> str:
        """Generate SHA-256 hash for a file."""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()[:16]  # Use first 16 characters
        except Exception as e:
            logging.warning(f"Could not generate hash for {file_path}: {e}")
            return "unknown"

    def cleanup_temp_files(self):
        """Clean up temporary files created during processing."""
        try:
            temp_thumbnails = self.temp_directory / "thumbnails"
            if temp_thumbnails.exists():
                for thumb_file in temp_thumbnails.glob("*.png"):
                    thumb_file.unlink()
                logging.info("Cleaned up temporary thumbnail files")
        except Exception as e:
            logging.warning(f"Error cleaning up temp files: {e}")

