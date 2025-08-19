"""
Enums and constants for the Scanner Extension application.

Defines all enumeration types and constants used throughout the application
for type safety and consistent behavior.
"""

from enum import Enum, auto


class FieldType(Enum):
    """Types of index fields available in schemas."""
    TEXT = "text"
    DATE = "date"
    NUMBER = "number"
    DROPDOWN = "dropdown"
    BOOLEAN = "boolean"

    @classmethod
    def get_display_names(cls):
        """Get user-friendly display names for field types."""
        return {
            cls.TEXT: "Text",
            cls.DATE: "Date",
            cls.NUMBER: "Number",
            cls.DROPDOWN: "Dropdown",
            cls.BOOLEAN: "Yes/No"
        }

    def get_display_name(self):
        """Get display name for this field type."""
        return self.get_display_names()[self]


class FieldRole(Enum):
    """Roles that fields can play in document organization."""
    FOLDER = "folder"  # Used to create folder structure
    FILENAME = "filename"  # Used in filename generation
    METADATA = "metadata"  # Stored as metadata only

    @classmethod
    def get_display_names(cls):
        """Get user-friendly display names for field roles."""
        return {
            cls.FOLDER: "Folder Structure",
            cls.FILENAME: "File Name",
            cls.METADATA: "Metadata Only"
        }

    def get_display_name(self):
        """Get display name for this field role."""
        return self.get_display_names()[self]


class SelectionMode(Enum):
    """Page selection modes for the page panel."""
    SINGLE = auto()  # Single page selection only
    MULTIPLE = auto()  # Multiple individual pages
    RANGE = auto()  # Range selection with Shift
    DRAG = auto()  # Drag rectangle selection

    @classmethod
    def get_default(cls):
        """Get default selection mode."""
        return cls.MULTIPLE


class ConflictType(Enum):
    """Types of conflicts that can occur during processing."""
    DUPLICATE_FILENAME = "duplicate_filename"
    INVALID_PATH = "invalid_path"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_FIELD_VALUE = "invalid_field_value"
    PATH_TOO_LONG = "path_too_long"
    RESERVED_NAME = "reserved_name"
    INVALID_CHARACTERS = "invalid_characters"

    @classmethod
    def get_display_names(cls):
        """Get user-friendly display names for conflict types."""
        return {
            cls.DUPLICATE_FILENAME: "Duplicate File Name",
            cls.INVALID_PATH: "Invalid Path",
            cls.MISSING_REQUIRED_FIELD: "Missing Required Field",
            cls.INVALID_FIELD_VALUE: "Invalid Field Value",
            cls.PATH_TOO_LONG: "Path Too Long",
            cls.RESERVED_NAME: "Reserved System Name",
            cls.INVALID_CHARACTERS: "Invalid Characters in Path"
        }

    def get_display_name(self):
        """Get display name for this conflict type."""
        return self.get_display_names()[self]


class ConflictResolution(Enum):
    """Strategies for resolving conflicts."""
    AUTO_RENAME = "auto_rename"  # Automatically rename with suffix
    PROMPT_USER = "prompt_user"  # Ask user what to do
    SKIP_DUPLICATE = "skip_duplicate"  # Skip conflicting items
    OVERWRITE = "overwrite"  # Replace existing files
    MERGE = "merge"  # Merge with existing (where applicable)

    @classmethod
    def get_display_names(cls):
        """Get user-friendly display names for resolution strategies."""
        return {
            cls.AUTO_RENAME: "Automatically Rename",
            cls.PROMPT_USER: "Ask Me Each Time",
            cls.SKIP_DUPLICATE: "Skip Duplicates",
            cls.OVERWRITE: "Overwrite Existing",
            cls.MERGE: "Merge When Possible"
        }

    def get_display_name(self):
        """Get display name for this resolution strategy."""
        return self.get_display_names()[self]


class PDFQuality(Enum):
    """PDF output quality settings."""
    LOW = "low"  # Heavily compressed
    MEDIUM = "medium"  # Balanced compression
    HIGH = "high"  # Light compression
    ORIGINAL = "original"  # No compression

    @classmethod
    def get_display_names(cls):
        """Get user-friendly display names for quality settings."""
        return {
            cls.LOW: "Low (Smallest File)",
            cls.MEDIUM: "Medium (Balanced)",
            cls.HIGH: "High (Better Quality)",
            cls.ORIGINAL: "Original (No Compression)"
        }

    def get_display_name(self):
        """Get display name for this quality setting."""
        return self.get_display_names()[self]

    def get_compression_level(self):
        """Get compression level (0-100) for this quality."""
        levels = {
            self.LOW: 30,
            self.MEDIUM: 60,
            self.HIGH: 85,
            self.ORIGINAL: 100
        }
        return levels[self]


class NamingStrategy(Enum):
    """File naming strategies."""
    PRESERVE_ORIGINAL = "preserve_original"  # Keep original scan names
    TIMESTAMP = "timestamp"  # Use timestamp-based names
    SEQUENTIAL = "sequential"  # Use sequential numbering
    SCHEMA_BASED = "schema_based"  # Use schema field values
    CUSTOM_TEMPLATE = "custom_template"  # User-defined template

    @classmethod
    def get_display_names(cls):
        """Get user-friendly display names for naming strategies."""
        return {
            cls.PRESERVE_ORIGINAL: "Keep Original Names",
            cls.TIMESTAMP: "Use Timestamps",
            cls.SEQUENTIAL: "Sequential Numbering",
            cls.SCHEMA_BASED: "Use Index Values",
            cls.CUSTOM_TEMPLATE: "Custom Template"
        }

    def get_display_name(self):
        """Get display name for this naming strategy."""
        return self.get_display_names()[self]


class ProcessingState(Enum):
    """States for batch processing operations."""
    IDLE = auto()
    PREPARING = auto()
    PROCESSING = auto()
    COMPLETING = auto()
    COMPLETED = auto()
    ERROR = auto()
    CANCELLED = auto()

    @property
    def is_active(self):
        """Check if this state represents active processing."""
        return self in (self.PREPARING, self.PROCESSING, self.COMPLETING)

    @property
    def is_finished(self):
        """Check if this state represents finished processing."""
        return self in (self.COMPLETED, self.ERROR, self.CANCELLED)


class ThumbnailSize(Enum):
    """Standard thumbnail sizes."""
    SMALL = (100, 133)  # Small thumbnails
    MEDIUM = (150, 200)  # Default size
    LARGE = (200, 267)  # Large thumbnails
    XLARGE = (300, 400)  # Extra large

    def __init__(self, width, height):
        self.width = width
        self.height = height

    @property
    def size_tuple(self):
        """Get size as (width, height) tuple."""
        return (self.width, self.height)

    @classmethod
    def get_default(cls):
        """Get default thumbnail size."""
        return cls.MEDIUM


class CacheType(Enum):
    """Types of cached data."""
    THUMBNAILS = "thumbnails"
    PDF_METADATA = "pdf_metadata"
    SCHEMA_VALIDATION = "schema_validation"
    FILE_HASHES = "file_hashes"
    FOLDER_PREVIEWS = "folder_previews"


class ValidationSeverity(Enum):
    """Severity levels for validation messages."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    @property
    def blocks_processing(self):
        """Check if this severity level blocks processing."""
        return self in (self.ERROR, self.CRITICAL)

    @classmethod
    def get_color_codes(cls):
        """Get color codes for different severity levels."""
        return {
            cls.INFO: "#2196F3",  # Blue
            cls.WARNING: "#FF9800",  # Orange
            cls.ERROR: "#F44336",  # Red
            cls.CRITICAL: "#9C27B0"  # Purple
        }

    def get_color(self):
        """Get color code for this severity level."""
        return self.get_color_codes()[self]


class SortOrder(Enum):
    """Sort orders for various lists."""
    ASCENDING = "asc"
    DESCENDING = "desc"

    @classmethod
    def get_default(cls):
        """Get default sort order."""
        return cls.ASCENDING


class FileFormat(Enum):
    """Supported file formats."""
    PDF = "pdf"

    @classmethod
    def get_supported_extensions(cls):
        """Get supported file extensions."""
        return {cls.PDF: [".pdf"]}

    def get_extensions(self):
        """Get file extensions for this format."""
        return self.get_supported_extensions()[self]

    @classmethod
    def from_extension(cls, extension: str):
        """Get format from file extension."""
        extension = extension.lower()
        for format_type, extensions in cls.get_supported_extensions().items():
            if extension in extensions:
                return format_type
        return None


# Application constants
class AppConstants:
    """Application-wide constants."""

    # Version info
    VERSION = "1.0.0"
    BUILD_DATE = "2024"

    # File system limits
    MAX_FILENAME_LENGTH = 255
    MAX_PATH_LENGTH = 260  # Windows limitation
    MAX_FOLDER_DEPTH = 10

    # Processing limits
    MAX_BATCH_SIZE = 1000
    MAX_PAGES_PER_DOCUMENT = 500

    # UI constants
    DEFAULT_THUMBNAIL_SIZE = ThumbnailSize.MEDIUM
    MIN_THUMBNAIL_SIZE = ThumbnailSize.SMALL
    MAX_THUMBNAIL_SIZE = ThumbnailSize.XLARGE

    # Cache settings
    DEFAULT_CACHE_SIZE_MB = 500
    MIN_CACHE_SIZE_MB = 50
    MAX_CACHE_SIZE_MB = 5000

    # Timeout settings
    FILE_MONITOR_TIMEOUT = 30  # seconds
    PROCESSING_TIMEOUT = 300  # seconds
    THUMBNAIL_GENERATION_TIMEOUT = 60  # seconds

    # File patterns
    TEMP_FILE_PREFIX = "scanner_ext_"
    BACKUP_FILE_SUFFIX = ".backup"

    # Default schema names
    DEFAULT_SCHEMA_NAMES = [
        "General Documents",
        "Legal Documents",
        "Medical Records",
        "Business Documents",
        "Personal Documents"
    ]

    # Reserved file/folder names (Windows)
    RESERVED_NAMES = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    }

    # Invalid path characters
    INVALID_PATH_CHARS = set('<>:"|?*')

    @classmethod
    def is_reserved_name(cls, name: str) -> bool:
        """Check if a name is reserved by the operating system."""
        return name.upper() in cls.RESERVED_NAMES

    @classmethod
    def has_invalid_chars(cls, path: str) -> bool:
        """Check if a path contains invalid characters."""
        return any(char in cls.INVALID_PATH_CHARS for char in path)

    @classmethod
    def get_safe_filename(cls, filename: str) -> str:
        """Create a safe filename by removing invalid characters."""
        # Replace invalid characters with underscore
        safe_name = ''.join('_' if char in cls.INVALID_PATH_CHARS else char
                            for char in filename)

        # Handle reserved names
        if cls.is_reserved_name(safe_name.split('.')[0]):
            safe_name = f"_{safe_name}"

        # Truncate if too long
        if len(safe_name) > cls.MAX_FILENAME_LENGTH:
            name, ext = safe_name.rsplit('.', 1) if '.' in safe_name else (safe_name, '')
            max_name_len = cls.MAX_FILENAME_LENGTH - len(ext) - 1 if ext else cls.MAX_FILENAME_LENGTH
            safe_name = f"{name[:max_name_len]}.{ext}" if ext else name[:max_name_len]

        return safe_name