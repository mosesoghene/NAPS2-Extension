"""
Validation engine for assignments and document processing.

Validates page assignments, checks for conflicts, ensures data integrity,
and provides validation feedback for the UI.
"""

import logging
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set, Any
from datetime import datetime
import platform

from ..core.exceptions import SchemaValidationError, AssignmentConflictError
from ..core.signals import app_signals
from ..models.enums import FieldType, ConflictType, ConflictResolution


class ValidationEngine:
    """Validates assignments and prevents conflicts."""

    def __init__(self):
        """Initialize validation engine with platform-specific rules."""
        self.validation_rules: Dict[str, Any] = {}
        self.error_messages: Dict[str, str] = {}
        self.warning_thresholds: Dict[str, Any] = {}

        # Initialize validation rules
        self._initialize_validation_rules()
        self._initialize_error_messages()
        self._initialize_warning_thresholds()

        # Platform-specific path validation
        self.is_windows = platform.system() == "Windows"
        self.max_path_length = 260 if self.is_windows else 4096
        self.max_filename_length = 255

        # Reserved names (Windows)
        self.reserved_names = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }

        logging.debug("ValidationEngine initialized")

    def validate_batch_assignments(self, batch) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Validate all assignments in a document batch.

        Args:
            batch: DocumentBatch to validate

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        try:
            logging.info(f"Validating batch with {len(batch.page_assignments)} assignments")

            errors = []
            is_valid = True

            if not batch.page_assignments:
                return True, []

            # Validate individual assignments
            for assignment in batch.page_assignments:
                assignment_errors = self._validate_single_assignment(assignment)
                if assignment_errors:
                    is_valid = False
                    errors.extend(assignment_errors)

            # Check for naming conflicts across assignments
            conflict_errors = self.check_naming_conflicts(batch.page_assignments)
            if conflict_errors:
                is_valid = False
                errors.extend(conflict_errors)

            # Validate folder structure
            folder_errors = self._validate_batch_folder_structure(batch.page_assignments)
            if folder_errors:
                is_valid = False
                errors.extend(folder_errors)

            # Check for duplicate page assignments
            duplicate_errors = self._check_duplicate_page_assignments(batch.page_assignments)
            if duplicate_errors:
                is_valid = False
                errors.extend(duplicate_errors)

            logging.info(f"Batch validation completed. Valid: {is_valid}, Errors: {len(errors)}")

            # Emit validation signal
            app_signals.batch_validation_completed.emit(is_valid, errors)

            return is_valid, errors

        except Exception as e:
            error_msg = f"Batch validation failed: {e}"
            logging.error(error_msg)
            return False, [{'type': 'system_error', 'message': error_msg}]

    def _validate_single_assignment(self, assignment) -> List[Dict[str, Any]]:
        """Validate a single page assignment."""
        errors = []

        try:
            # Check required fields
            required_errors = self.check_required_fields(assignment)
            errors.extend(required_errors)

            # Validate field values
            field_errors = self.validate_field_values(assignment.index_values, assignment.schema)
            errors.extend(field_errors)

            # Validate generated paths
            path_errors = self._validate_assignment_paths(assignment)
            errors.extend(path_errors)

            # Check page references
            page_errors = self._validate_page_references(assignment)
            errors.extend(page_errors)

        except Exception as e:
            errors.append({
                'type': 'assignment_error',
                'assignment_id': assignment.assignment_id,
                'message': f"Assignment validation failed: {e}"
            })

        return errors

    def check_naming_conflicts(self, assignments: List) -> List[Dict[str, Any]]:
        """
        Check for file naming conflicts between assignments.

        Args:
            assignments: List of PageAssignment objects

        Returns:
            List of conflict error dictionaries
        """
        try:
            conflicts = []
            output_paths = {}  # path -> list of assignment_ids

            for assignment in assignments:
                try:
                    # Generate output path for this assignment
                    folder_path = assignment.schema.generate_folder_structure(assignment.index_values)
                    filename = assignment.schema.generate_filename(assignment.index_values)
                    full_path = Path(folder_path) / f"{filename}.pdf"

                    # Normalize path for comparison
                    normalized_path = str(full_path).lower() if self.is_windows else str(full_path)

                    if normalized_path in output_paths:
                        output_paths[normalized_path].append(assignment.assignment_id)
                    else:
                        output_paths[normalized_path] = [assignment.assignment_id]

                except Exception as e:
                    conflicts.append({
                        'type': ConflictType.INVALID_PATH.value,
                        'assignment_id': assignment.assignment_id,
                        'message': f"Cannot generate path for assignment: {e}"
                    })

            # Find conflicts
            for path, assignment_ids in output_paths.items():
                if len(assignment_ids) > 1:
                    conflicts.append({
                        'type': ConflictType.DUPLICATE_FILENAME.value,
                        'path': path,
                        'conflicting_assignments': assignment_ids,
                        'message': f"Multiple assignments would create the same file: {path}"
                    })

            return conflicts

        except Exception as e:
            logging.error(f"Error checking naming conflicts: {e}")
            return [{'type': 'system_error', 'message': f"Conflict checking failed: {e}"}]

    def validate_folder_structure(self, folder_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Validate folder structure paths.

        Args:
            folder_paths: List of folder path strings

        Returns:
            List of validation errors
        """
        errors = []

        for folder_path in folder_paths:
            try:
                path_obj = Path(folder_path)

                # Check path length
                if len(str(path_obj)) > self.max_path_length:
                    errors.append({
                        'type': 'path_too_long',
                        'path': folder_path,
                        'message': f"Path exceeds maximum length ({self.max_path_length}): {folder_path}"
                    })

                # Check each path component
                for component in path_obj.parts:
                    component_errors = self._validate_path_component(component)
                    errors.extend([{**error, 'path': folder_path} for error in component_errors])

            except Exception as e:
                errors.append({
                    'type': 'invalid_path',
                    'path': folder_path,
                    'message': f"Invalid path: {e}"
                })

        return errors

    def check_required_fields(self, assignment) -> List[Dict[str, Any]]:
        """Check if all required fields are filled."""
        errors = []

        try:
            for field in assignment.schema.fields:
                if field.required:
                    value = assignment.index_values.get(field.name, "").strip()
                    if not value:
                        errors.append({
                            'type': ConflictType.MISSING_REQUIRED_FIELD.value,
                            'assignment_id': assignment.assignment_id,
                            'field_name': field.name,
                            'message': f"Required field '{field.name}' is empty"
                        })

        except Exception as e:
            errors.append({
                'type': 'validation_error',
                'assignment_id': assignment.assignment_id,
                'message': f"Required field validation failed: {e}"
            })

        return errors

    def validate_field_values(self, values: Dict[str, str], schema) -> List[Dict[str, Any]]:
        """
        Validate field values against schema rules.

        Args:
            values: Dictionary of field values
            schema: IndexSchema object

        Returns:
            List of validation errors
        """
        errors = []

        try:
            for field in schema.fields:
                field_name = field.name
                field_value = values.get(field_name, "")

                if not field_value and not field.required:
                    continue  # Skip empty optional fields

                # Validate based on field type
                field_errors = self._validate_field_by_type(field, field_value)
                errors.extend(field_errors)

                # Apply custom validation rules
                rule_errors = self._apply_custom_validation_rules(field, field_value)
                errors.extend(rule_errors)

        except Exception as e:
            errors.append({
                'type': 'schema_validation_error',
                'message': f"Field validation failed: {e}"
            })

        return errors

    def _validate_field_by_type(self, field, value: str) -> List[Dict[str, Any]]:
        """Validate field value based on its type."""
        errors = []

        try:
            if field.field_type == FieldType.TEXT:
                # Check length limits
                if len(value) > 255:
                    errors.append({
                        'type': 'field_validation_error',
                        'field_name': field.name,
                        'message': f"Text field '{field.name}' exceeds 255 characters"
                    })

            elif field.field_type == FieldType.DATE:
                # Validate date format
                if not self._is_valid_date(value):
                    errors.append({
                        'type': 'field_validation_error',
                        'field_name': field.name,
                        'message': f"Invalid date format in field '{field.name}': {value}"
                    })

            elif field.field_type == FieldType.NUMBER:
                # Validate numeric value
                if not self._is_valid_number(value):
                    errors.append({
                        'type': 'field_validation_error',
                        'field_name': field.name,
                        'message': f"Invalid number format in field '{field.name}': {value}"
                    })

            elif field.field_type == FieldType.DROPDOWN:
                # Validate against dropdown options
                if field.dropdown_options and value not in field.dropdown_options:
                    errors.append({
                        'type': 'field_validation_error',
                        'field_name': field.name,
                        'message': f"Value '{value}' not in dropdown options for field '{field.name}'"
                    })

            elif field.field_type == FieldType.BOOLEAN:
                # Validate boolean value
                if value.lower() not in ['true', 'false', '1', '0', 'yes', 'no']:
                    errors.append({
                        'type': 'field_validation_error',
                        'field_name': field.name,
                        'message': f"Invalid boolean value in field '{field.name}': {value}"
                    })

        except Exception as e:
            errors.append({
                'type': 'field_type_validation_error',
                'field_name': field.name,
                'message': f"Type validation failed for field '{field.name}': {e}"
            })

        return errors

    def _apply_custom_validation_rules(self, field, value: str) -> List[Dict[str, Any]]:
        """Apply custom validation rules to field value."""
        errors = []

        try:
            if hasattr(field, 'validation_rules') and field.validation_rules:
                rules = field.validation_rules

                # Pattern matching
                if 'pattern' in rules:
                    pattern = rules['pattern']
                    if not re.match(pattern, value):
                        errors.append({
                            'type': 'field_validation_error',
                            'field_name': field.name,
                            'message': f"Field '{field.name}' does not match required pattern"
                        })

                # Min/max length
                if 'min_length' in rules and len(value) < rules['min_length']:
                    errors.append({
                        'type': 'field_validation_error',
                        'field_name': field.name,
                        'message': f"Field '{field.name}' is too short (minimum {rules['min_length']})"
                    })

                if 'max_length' in rules and len(value) > rules['max_length']:
                    errors.append({
                        'type': 'field_validation_error',
                        'field_name': field.name,
                        'message': f"Field '{field.name}' is too long (maximum {rules['max_length']})"
                    })

        except Exception as e:
            errors.append({
                'type': 'custom_validation_error',
                'field_name': field.name,
                'message': f"Custom validation failed for field '{field.name}': {e}"
            })

        return errors

    def validate_file_system_compatibility(self, paths: List[str]) -> List[Dict[str, Any]]:
        """Check if paths are compatible with the current file system."""
        errors = []

        for path in paths:
            try:
                path_obj = Path(path)

                # Check overall path length
                if len(str(path_obj)) > self.max_path_length:
                    errors.append({
                        'type': 'path_length_error',
                        'path': path,
                        'message': f"Path too long for file system: {path}"
                    })

                # Check filename length
                if len(path_obj.name) > self.max_filename_length:
                    errors.append({
                        'type': 'filename_length_error',
                        'path': path,
                        'message': f"Filename too long: {path_obj.name}"
                    })

                # Check for invalid characters
                invalid_chars = self._get_invalid_path_characters()
                for char in invalid_chars:
                    if char in str(path_obj):
                        errors.append({
                            'type': 'invalid_character_error',
                            'path': path,
                            'character': char,
                            'message': f"Path contains invalid character '{char}': {path}"
                        })
                        break

                # Check for reserved names (Windows)
                if self.is_windows:
                    for part in path_obj.parts:
                        name_without_ext = part.split('.')[0].upper()
                        if name_without_ext in self.reserved_names:
                            errors.append({
                                'type': 'reserved_name_error',
                                'path': path,
                                'reserved_name': part,
                                'message': f"Path contains reserved name '{part}': {path}"
                            })

            except Exception as e:
                errors.append({
                    'type': 'path_validation_error',
                    'path': path,
                    'message': f"Path validation failed: {e}"
                })

        return errors

    def suggest_conflict_resolutions(self, conflicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Suggest resolutions for detected conflicts."""
        suggestions = []

        for conflict in conflicts:
            conflict_type = conflict.get('type')

            if conflict_type == ConflictType.DUPLICATE_FILENAME.value:
                suggestions.append({
                    'conflict': conflict,
                    'suggested_resolution': ConflictResolution.AUTO_RENAME,
                    'alternatives': [ConflictResolution.PROMPT_USER, ConflictResolution.SKIP_DUPLICATE],
                    'description': "Automatically rename files to avoid conflicts"
                })

            elif conflict_type == ConflictType.INVALID_PATH.value:
                suggestions.append({
                    'conflict': conflict,
                    'suggested_resolution': ConflictResolution.PROMPT_USER,
                    'alternatives': [ConflictResolution.AUTO_RENAME, ConflictResolution.SKIP_DUPLICATE],
                    'description': "Prompt user to fix invalid path"
                })

            elif conflict_type == ConflictType.MISSING_REQUIRED_FIELD.value:
                suggestions.append({
                    'conflict': conflict,
                    'suggested_resolution': ConflictResolution.PROMPT_USER,
                    'alternatives': [ConflictResolution.SKIP_DUPLICATE],
                    'description': "Prompt user to fill required fields"
                })

        return suggestions

    def validate_schema_compatibility(self, schema) -> List[Dict[str, Any]]:
        """Validate schema structure and compatibility."""
        errors = []

        try:
            # Check for required components
            if not schema.fields:
                errors.append({
                    'type': 'schema_error',
                    'message': "Schema has no fields defined"
                })

            # Check for at least one filename field
            filename_fields = [f for f in schema.fields if f.role.value == 'FILENAME']
            if not filename_fields:
                errors.append({
                    'type': 'schema_error',
                    'message': "Schema must have at least one field with FILENAME role"
                })

            # Validate field names
            field_names = set()
            for field in schema.fields:
                if field.name in field_names:
                    errors.append({
                        'type': 'schema_error',
                        'field_name': field.name,
                        'message': f"Duplicate field name: {field.name}"
                    })
                field_names.add(field.name)

                # Validate field name format
                if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', field.name):
                    errors.append({
                        'type': 'schema_error',
                        'field_name': field.name,
                        'message': f"Invalid field name format: {field.name}"
                    })

        except Exception as e:
            errors.append({
                'type': 'schema_validation_error',
                'message': f"Schema validation failed: {e}"
            })

        return errors

    # Helper methods
    def _validate_assignment_paths(self, assignment) -> List[Dict[str, Any]]:
        """Validate paths generated by assignment."""
        errors = []

        try:
            folder_path = assignment.schema.generate_folder_structure(assignment.index_values)
            filename = assignment.schema.generate_filename(assignment.index_values)

            # Validate folder path
            folder_errors = self.validate_folder_structure([folder_path])
            errors.extend(folder_errors)

            # Validate filename
            filename_errors = self._validate_filename(filename)
            errors.extend([{**error, 'assignment_id': assignment.assignment_id} for error in filename_errors])

        except Exception as e:
            errors.append({
                'type': 'path_generation_error',
                'assignment_id': assignment.assignment_id,
                'message': f"Cannot generate paths: {e}"
            })

        return errors

    def _validate_page_references(self, assignment) -> List[Dict[str, Any]]:
        """Validate page references in assignment."""
        errors = []

        if not assignment.page_references:
            errors.append({
                'type': 'assignment_error',
                'assignment_id': assignment.assignment_id,
                'message': "Assignment has no page references"
            })

        return errors

    def _validate_batch_folder_structure(self, assignments: List) -> List[Dict[str, Any]]:
        """Validate folder structure across all assignments."""
        errors = []

        try:
            folder_paths = []
            for assignment in assignments:
                try:
                    folder_path = assignment.schema.generate_folder_structure(assignment.index_values)
                    folder_paths.append(folder_path)
                except Exception:
                    pass  # Already handled in individual validation

            structure_errors = self.validate_folder_structure(folder_paths)
            errors.extend(structure_errors)

        except Exception as e:
            errors.append({
                'type': 'folder_structure_error',
                'message': f"Folder structure validation failed: {e}"
            })

        return errors

    def _check_duplicate_page_assignments(self, assignments: List) -> List[Dict[str, Any]]:
        """Check for pages assigned to multiple assignments."""
        errors = []

        try:
            page_assignments = {}  # page_id -> list of assignment_ids

            for assignment in assignments:
                for page_ref in assignment.page_references:
                    page_id = page_ref.get_unique_id()

                    if page_id in page_assignments:
                        page_assignments[page_id].append(assignment.assignment_id)
                    else:
                        page_assignments[page_id] = [assignment.assignment_id]

            # Find duplicates
            for page_id, assignment_ids in page_assignments.items():
                if len(assignment_ids) > 1:
                    errors.append({
                        'type': 'duplicate_page_assignment',
                        'page_id': page_id,
                        'conflicting_assignments': assignment_ids,
                        'message': f"Page {page_id} is assigned to multiple assignments"
                    })

        except Exception as e:
            errors.append({
                'type': 'duplicate_check_error',
                'message': f"Duplicate page check failed: {e}"
            })

        return errors

    def _validate_filename(self, filename: str) -> List[Dict[str, Any]]:
        """Validate a filename."""
        errors = []

        # Check length
        if len(filename) > self.max_filename_length:
            errors.append({
                'type': 'filename_length_error',
                'filename': filename,
                'message': f"Filename too long: {filename}"
            })

        # Check for invalid characters
        invalid_chars = self._get_invalid_filename_characters()
        for char in invalid_chars:
            if char in filename:
                errors.append({
                    'type': 'invalid_character_error',
                    'filename': filename,
                    'character': char,
                    'message': f"Filename contains invalid character '{char}': {filename}"
                })

        # Check for reserved names
        if self.is_windows:
            name_without_ext = filename.split('.')[0].upper()
            if name_without_ext in self.reserved_names:
                errors.append({
                    'type': 'reserved_name_error',
                    'filename': filename,
                    'message': f"Filename uses reserved name: {filename}"
                })

        return errors

    def _validate_path_component(self, component: str) -> List[Dict[str, Any]]:
        """Validate individual path component."""
        errors = []

        if not component or component in ['.', '..']:
            return errors

        # Check length
        if len(component) > self.max_filename_length:
            errors.append({
                'type': 'component_length_error',
                'component': component,
                'message': f"Path component too long: {component}"
            })

        # Check for invalid characters
        invalid_chars = self._get_invalid_path_characters()
        for char in invalid_chars:
            if char in component:
                errors.append({
                    'type': 'invalid_character_error',
                    'component': component,
                    'character': char,
                    'message': f"Path component contains invalid character '{char}': {component}"
                })

        return errors

    def _get_invalid_filename_characters(self) -> Set[str]:
        """Get set of invalid filename characters for current OS."""
        if self.is_windows:
            return {'<', '>', ':', '"', '|', '?', '*', '/', '\\'}
        else:
            return {'/', '\0'}

    def _get_invalid_path_characters(self) -> Set[str]:
        """Get set of invalid path characters for current OS."""
        if self.is_windows:
            return {'<', '>', ':', '"', '|', '?', '*'}
        else:
            return {'\0'}

    def _is_valid_date(self, date_str: str) -> bool:
        """Check if string is a valid date."""
        date_formats = [
            '%Y-%m-%d',
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%Y/%m/%d',
            '%d-%m-%Y',
            '%m-%d-%Y'
        ]

        for fmt in date_formats:
            try:
                datetime.strptime(date_str, fmt)
                return True
            except ValueError:
                continue
        return False

    def _is_valid_number(self, number_str: str) -> bool:
        """Check if string is a valid number."""
        try:
            float(number_str)
            return True
        except ValueError:
            return False

    def _initialize_validation_rules(self):
        """Initialize validation rules dictionary."""
        self.validation_rules = {
            'text_max_length': 255,
            'filename_max_length': self.max_filename_length,
            'path_max_length': self.max_path_length,
            'date_formats': [
                '%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y',
                '%Y/%m/%d', '%d-%m-%Y', '%m-%d-%Y'
            ],
            'boolean_values': ['true', 'false', '1', '0', 'yes', 'no'],
        }

    def _initialize_error_messages(self):
        """Initialize error message templates."""
        self.error_messages = {
            'required_field_empty': "Required field '{field_name}' cannot be empty",
            'text_too_long': "Text in field '{field_name}' exceeds maximum length",
            'invalid_date_format': "Invalid date format in field '{field_name}'",
            'invalid_number_format': "Invalid number format in field '{field_name}'",
            'invalid_boolean_value': "Invalid boolean value in field '{field_name}'",
            'duplicate_filename': "Multiple assignments would create the same filename",
            'invalid_path_character': "Path contains invalid character '{character}'",
            'path_too_long': "Path exceeds maximum length for file system",
            'filename_too_long': "Filename exceeds maximum length",
            'reserved_filename': "Filename uses a reserved system name",
            'duplicate_page_assignment': "Page is assigned to multiple assignments",
            'no_filename_fields': "Schema must have at least one filename field",
            'no_pages_assigned': "Assignment has no pages assigned",
        }

    def _initialize_warning_thresholds(self):
        """Initialize warning threshold settings."""
        self.warning_thresholds = {
            'path_length_warning': int(self.max_path_length * 0.8),
            'filename_length_warning': int(self.max_filename_length * 0.8),
            'max_assignments_per_batch': 50,
            'max_pages_per_assignment': 20,
        }

    def get_validation_summary(self, errors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate validation summary from error list."""
        summary = {
            'total_errors': len(errors),
            'error_types': {},
            'critical_errors': 0,
            'warnings': 0,
            'is_valid': len(errors) == 0
        }

        critical_types = {
            ConflictType.DUPLICATE_FILENAME.value,
            ConflictType.MISSING_REQUIRED_FIELD.value,
            'invalid_path'
        }

        for error in errors:
            error_type = error.get('type', 'unknown')

            if error_type in summary['error_types']:
                summary['error_types'][error_type] += 1
            else:
                summary['error_types'][error_type] = 1

            if error_type in critical_types:
                summary['critical_errors'] += 1
            else:
                summary['warnings'] += 1

        return summary