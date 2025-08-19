"""
Core exception classes for the Scanner Extension application.

Provides a hierarchy of custom exceptions for different types of errors
that can occur during application operation.
"""


class ScannerExtensionError(Exception):
    """Base exception for all Scanner Extension errors."""

    def __init__(self, message: str, details: str = None):
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class SchemaValidationError(ScannerExtensionError):
    """Raised when schema validation fails."""

    def __init__(self, message: str, field_name: str = None, field_value: str = None):
        super().__init__(message)
        self.field_name = field_name
        self.field_value = field_value

    def __str__(self) -> str:
        if self.field_name:
            return f"Schema validation error for field '{self.field_name}': {self.message}"
        return f"Schema validation error: {self.message}"


class FileProcessingError(ScannerExtensionError):
    """Raised when file operations fail."""

    def __init__(self, message: str, file_path: str = None, operation: str = None):
        super().__init__(message)
        self.file_path = file_path
        self.operation = operation

    def __str__(self) -> str:
        parts = ["File processing error"]
        if self.operation:
            parts.append(f"during {self.operation}")
        if self.file_path:
            parts.append(f"on '{self.file_path}'")
        parts.append(f": {self.message}")
        return " ".join(parts)


class AssignmentConflictError(ScannerExtensionError):
    """Raised when page assignment conflicts occur."""

    def __init__(self, message: str, conflicting_assignments: list = None):
        super().__init__(message)
        self.conflicting_assignments = conflicting_assignments or []

    def __str__(self) -> str:
        if self.conflicting_assignments:
            count = len(self.conflicting_assignments)
            return f"Assignment conflict ({count} conflicts): {self.message}"
        return f"Assignment conflict: {self.message}"


class PDFProcessingError(ScannerExtensionError):
    """Raised when PDF manipulation fails."""

    def __init__(self, message: str, pdf_file: str = None, page_number: int = None):
        super().__init__(message)
        self.pdf_file = pdf_file
        self.page_number = page_number

    def __str__(self) -> str:
        parts = ["PDF processing error"]
        if self.pdf_file:
            parts.append(f"in '{self.pdf_file}'")
        if self.page_number is not None:
            parts.append(f"on page {self.page_number}")
        parts.append(f": {self.message}")
        return " ".join(parts)


class ConfigurationError(ScannerExtensionError):
    """Raised when configuration issues occur."""

    def __init__(self, message: str, config_key: str = None):
        super().__init__(message)
        self.config_key = config_key

    def __str__(self) -> str:
        if self.config_key:
            return f"Configuration error for '{self.config_key}': {self.message}"
        return f"Configuration error: {self.message}"


class CacheError(ScannerExtensionError):
    """Raised when cache operations fail."""

    def __init__(self, message: str, cache_key: str = None):
        super().__init__(message)
        self.cache_key = cache_key

    def __str__(self) -> str:
        if self.cache_key:
            return f"Cache error for '{self.cache_key}': {self.message}"
        return f"Cache error: {self.message}"


class ExportError(ScannerExtensionError):
    """Raised when document export fails."""

    def __init__(self, message: str, output_path: str = None):
        super().__init__(message)
        self.output_path = output_path

    def __str__(self) -> str:
        if self.output_path:
            return f"Export error to '{self.output_path}': {self.message}"
        return f"Export error: {self.message}"
