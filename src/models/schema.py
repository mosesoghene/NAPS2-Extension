"""
Schema and field definitions for document indexing.

Defines the structure and validation rules for document indexing schemas,
including individual fields and complete schema definitions.
"""

import json
import re
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from copy import deepcopy

from .enums import FieldType, FieldRole, AppConstants
from ..core.exceptions import SchemaValidationError


class IndexField:
    """
    Individual field definition within a schema.

    Represents a single input field with its type, validation rules,
    and role in the document organization process.
    """

    def __init__(self, name: str, field_type: FieldType, role: FieldRole,
                 required: bool = False):
        self.name = name
        self.field_type = field_type
        self.role = role
        self.required = required
        self.default_value: Optional[str] = None
        self.validation_rules: Dict[str, Any] = {}
        self.display_order = 0
        self.dropdown_options: Optional[List[str]] = None
        self.description = ""
        self.placeholder_text = ""

        # Auto-set dropdown options list for dropdown fields
        if field_type == FieldType.DROPDOWN and self.dropdown_options is None:
            self.dropdown_options = []

    def validate_value(self, value: Any) -> tuple[bool, Optional[str]]:
        """
        Validate a value against this field's rules.

        Args:
            value: The value to validate

        Returns:
            tuple: (is_valid, error_message)
        """
        # Handle None/empty values
        if value is None or (isinstance(value, str) and not value.strip()):
            if self.required:
                return False, f"Field '{self.name}' is required"
            return True, None

        # Convert to string for most validations
        str_value = str(value).strip()

        # Type-specific validation
        try:
            if self.field_type == FieldType.TEXT:
                return self._validate_text(str_value)
            elif self.field_type == FieldType.DATE:
                return self._validate_date(str_value)
            elif self.field_type == FieldType.NUMBER:
                return self._validate_number(str_value)
            elif self.field_type == FieldType.DROPDOWN:
                return self._validate_dropdown(str_value)
            elif self.field_type == FieldType.BOOLEAN:
                return self._validate_boolean(str_value)
            else:
                return False, f"Unknown field type: {self.field_type}"

        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def _validate_text(self, value: str) -> tuple[bool, Optional[str]]:
        """Validate text field value."""
        # Check minimum length
        min_length = self.validation_rules.get('min_length', 0)
        if len(value) < min_length:
            return False, f"Text must be at least {min_length} characters"

        # Check maximum length
        max_length = self.validation_rules.get('max_length', 1000)
        if len(value) > max_length:
            return False, f"Text cannot exceed {max_length} characters"

        # Check pattern if specified
        pattern = self.validation_rules.get('pattern')
        if pattern and not re.match(pattern, value):
            pattern_desc = self.validation_rules.get('pattern_description', 'required format')
            return False, f"Text must match {pattern_desc}"

        # Check for invalid path characters if used in folder/filename
        if self.role in (FieldRole.FOLDER, FieldRole.FILENAME):
            if AppConstants.has_invalid_chars(value):
                return False, "Contains invalid characters for file/folder names"
            if AppConstants.is_reserved_name(value):
                return False, "Cannot use reserved system names"

        return True, None

    def _validate_date(self, value: str) -> tuple[bool, Optional[str]]:
        """Validate date field value."""
        # Try common date formats
        date_formats = [
            '%Y-%m-%d',  # 2024-01-15
            '%m/%d/%Y',  # 01/15/2024
            '%d/%m/%Y',  # 15/01/2024
            '%Y/%m/%d',  # 2024/01/15
            '%m-%d-%Y',  # 01-15-2024
            '%d-%m-%Y',  # 15-01-2024
        ]

        parsed_date = None
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(value, fmt).date()
                break
            except ValueError:
                continue

        if parsed_date is None:
            return False, "Invalid date format. Use YYYY-MM-DD, MM/DD/YYYY, or similar"

        # Check date range if specified
        min_date = self.validation_rules.get('min_date')
        max_date = self.validation_rules.get('max_date')

        if min_date and parsed_date < min_date:
            return False, f"Date must be after {min_date}"

        if max_date and parsed_date > max_date:
            return False, f"Date must be before {max_date}"

        return True, None

    def _validate_number(self, value: str) -> tuple[bool, Optional[str]]:
        """Validate number field value."""
        try:
            # Try to parse as float first
            num_value = float(value)

            # Check if integer is required
            if self.validation_rules.get('integer_only', False):
                if not value.lstrip('-').isdigit():
                    return False, "Must be a whole number"
                num_value = int(value)

        except ValueError:
            return False, "Must be a valid number"

        # Check minimum value
        min_value = self.validation_rules.get('min_value')
        if min_value is not None and num_value < min_value:
            return False, f"Number must be at least {min_value}"

        # Check maximum value
        max_value = self.validation_rules.get('max_value')
        if max_value is not None and num_value > max_value:
            return False, f"Number cannot exceed {max_value}"

        return True, None

    def _validate_dropdown(self, value: str) -> tuple[bool, Optional[str]]:
        """Validate dropdown field value."""
        if not self.dropdown_options:
            return False, "No dropdown options defined"

        if value not in self.dropdown_options:
            return False, f"Must select one of: {', '.join(self.dropdown_options)}"

        return True, None

    def _validate_boolean(self, value: str) -> tuple[bool, Optional[str]]:
        """Validate boolean field value."""
        valid_true = {'true', 'yes', '1', 'on', 'checked'}
        valid_false = {'false', 'no', '0', 'off', 'unchecked', ''}

        if value.lower() not in valid_true and value.lower() not in valid_false:
            return False, "Must be yes/no, true/false, or 1/0"

        return True, None

    def get_default_value(self) -> str:
        """Get the default value for this field."""
        if self.default_value is not None:
            return self.default_value

        # Type-specific defaults
        if self.field_type == FieldType.BOOLEAN:
            return "false"
        elif self.field_type == FieldType.NUMBER:
            return "0"
        elif self.field_type == FieldType.DATE:
            return datetime.now().strftime('%Y-%m-%d')
        else:
            return ""

    def set_validation_rules(self, rules: Dict[str, Any]):
        """Set validation rules for this field."""
        self.validation_rules.update(rules)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize field to dictionary."""
        return {
            'name': self.name,
            'field_type': self.field_type.value,
            'role': self.role.value,
            'required': self.required,
            'default_value': self.default_value,
            'validation_rules': self.validation_rules,
            'display_order': self.display_order,
            'dropdown_options': self.dropdown_options,
            'description': self.description,
            'placeholder_text': self.placeholder_text
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IndexField':
        """Deserialize field from dictionary."""
        field = cls(
            name=data['name'],
            field_type=FieldType(data['field_type']),
            role=FieldRole(data['role']),
            required=data.get('required', False)
        )

        field.default_value = data.get('default_value')
        field.validation_rules = data.get('validation_rules', {})
        field.display_order = data.get('display_order', 0)
        field.dropdown_options = data.get('dropdown_options')
        field.description = data.get('description', '')
        field.placeholder_text = data.get('placeholder_text', '')

        return field

    def clone(self) -> 'IndexField':
        """Create a copy of this field."""
        return IndexField.from_dict(self.to_dict())


class IndexSchema:
    """
    Complete schema definition for document indexing.

    Defines the structure, validation rules, and organization logic
    for a specific type of document batch.
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.fields: List[IndexField] = []
        self.folder_separator = "/"
        self.filename_template = "{timestamp}_{sequential}"
        self.created_date = datetime.now()
        self.modified_date = datetime.now()

        # Schema metadata
        self.version = "1.0"
        self.author = ""
        self.category = ""
        self.tags: List[str] = []

    def add_field(self, field: IndexField):
        """Add a field to this schema."""
        # Check for duplicate names
        if any(f.name == field.name for f in self.fields):
            raise SchemaValidationError(f"Field '{field.name}' already exists")

        # Set display order if not specified
        if field.display_order == 0:
            field.display_order = len(self.fields) + 1

        self.fields.append(field)
        self.modified_date = datetime.now()

    def remove_field(self, field_name: str) -> bool:
        """Remove a field by name. Returns True if found and removed."""
        for i, field in enumerate(self.fields):
            if field.name == field_name:
                del self.fields[i]
                self.modified_date = datetime.now()
                return True
        return False

    def reorder_fields(self, field_order: List[str]):
        """Reorder fields according to the provided list of field names."""
        if set(field_order) != set(f.name for f in self.fields):
            raise SchemaValidationError("Field order list doesn't match existing fields")

        # Create new field list in specified order
        field_dict = {f.name: f for f in self.fields}
        self.fields = [field_dict[name] for name in field_order]

        # Update display orders
        for i, field in enumerate(self.fields):
            field.display_order = i + 1

        self.modified_date = datetime.now()

    def get_field_by_name(self, name: str) -> Optional[IndexField]:
        """Retrieve a field by name."""
        for field in self.fields:
            if field.name == name:
                return field
        return None

    def get_fields_by_role(self, role: FieldRole) -> List[IndexField]:
        """Get all fields with a specific role."""
        return [f for f in self.fields if f.role == role]

    def validate_schema(self) -> tuple[bool, List[str]]:
        """
        Validate the schema structure and consistency.

        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors = []

        # Check basic requirements
        if not self.name.strip():
            errors.append("Schema name is required")

        if not self.fields:
            errors.append("Schema must have at least one field")

        # Check for duplicate field names
        field_names = [f.name for f in self.fields]
        if len(field_names) != len(set(field_names)):
            errors.append("Duplicate field names found")

        # Validate each field
        for field in self.fields:
            # Check field name
            if not field.name.strip():
                errors.append("All fields must have names")
                continue

            # Check dropdown options
            if field.field_type == FieldType.DROPDOWN:
                if not field.dropdown_options or len(field.dropdown_options) == 0:
                    errors.append(f"Dropdown field '{field.name}' must have options")

            # Validate default value if set
            if field.default_value:
                is_valid, error = field.validate_value(field.default_value)
                if not is_valid:
                    errors.append(f"Default value for '{field.name}': {error}")

        # Check that we have at least one folder or filename field for organization
        folder_fields = self.get_fields_by_role(FieldRole.FOLDER)
        filename_fields = self.get_fields_by_role(FieldRole.FILENAME)

        if not folder_fields and not filename_fields:
            errors.append("Schema should have at least one folder or filename field")

        return len(errors) == 0, errors

    def generate_folder_structure(self, values: Dict[str, str]) -> str:
        """
        Generate folder path from field values.

        Args:
            values: Dictionary mapping field names to values

        Returns:
            str: Generated folder path
        """
        folder_parts = []
        folder_fields = sorted(
            self.get_fields_by_role(FieldRole.FOLDER),
            key=lambda f: f.display_order
        )

        for field in folder_fields:
            value = values.get(field.name, "").strip()
            if value:
                # Clean the value for use in folder name
                clean_value = AppConstants.get_safe_filename(value)
                if clean_value:
                    folder_parts.append(clean_value)

        return self.folder_separator.join(folder_parts) if folder_parts else ""

    def generate_filename(self, values: Dict[str, str],
                          timestamp: Optional[datetime] = None,
                          sequential: Optional[int] = None) -> str:
        """
        Generate filename from field values and template.

        Args:
            values: Dictionary mapping field names to values
            timestamp: Optional timestamp for filename
            sequential: Optional sequential number

        Returns:
            str: Generated filename (without extension)
        """
        # Collect filename field values
        filename_parts = []
        filename_fields = sorted(
            self.get_fields_by_role(FieldRole.FILENAME),
            key=lambda f: f.display_order
        )

        for field in filename_fields:
            value = values.get(field.name, "").strip()
            if value:
                clean_value = AppConstants.get_safe_filename(value)
                if clean_value:
                    filename_parts.append(clean_value)

        # Build template variables
        template_vars = {
            'timestamp': timestamp.strftime('%Y%m%d_%H%M%S') if timestamp else datetime.now().strftime('%Y%m%d_%H%M%S'),
            'sequential': f"{sequential:03d}" if sequential is not None else "001",
            'date': timestamp.strftime('%Y-%m-%d') if timestamp else datetime.now().strftime('%Y-%m-%d'),
            'time': timestamp.strftime('%H-%M-%S') if timestamp else datetime.now().strftime('%H-%M-%S')
        }

        # Add field values to template variables
        for field_name, value in values.items():
            if value and value.strip():
                clean_value = AppConstants.get_safe_filename(value.strip())
                template_vars[field_name.lower().replace(' ', '_')] = clean_value

        # Generate filename from template
        try:
            filename = self.filename_template.format(**template_vars)
        except KeyError as e:
            # Fall back to basic naming if template fails
            filename = f"{template_vars['timestamp']}"
            if filename_parts:
                filename += f"_{'_'.join(filename_parts)}"

        # Add filename parts if not already included
        if filename_parts and not any(part in filename for part in filename_parts):
            filename += f"_{'_'.join(filename_parts)}"

        return AppConstants.get_safe_filename(filename)

    def to_json(self) -> str:
        """Serialize schema to JSON string."""
        schema_dict = {
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'author': self.author,
            'category': self.category,
            'tags': self.tags,
            'folder_separator': self.folder_separator,
            'filename_template': self.filename_template,
            'created_date': self.created_date.isoformat(),
            'modified_date': self.modified_date.isoformat(),
            'fields': [field.to_dict() for field in self.fields]
        }
        return json.dumps(schema_dict, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'IndexSchema':
        """Deserialize schema from JSON string."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise SchemaValidationError(f"Invalid JSON format: {e}")

        schema = cls(
            name=data.get('name', ''),
            description=data.get('description', '')
        )

        # Set metadata
        schema.version = data.get('version', '1.0')
        schema.author = data.get('author', '')
        schema.category = data.get('category', '')
        schema.tags = data.get('tags', [])
        schema.folder_separator = data.get('folder_separator', '/')
        schema.filename_template = data.get('filename_template', '{timestamp}_{sequential}')

        # Parse dates
        try:
            if 'created_date' in data:
                schema.created_date = datetime.fromisoformat(data['created_date'])
            if 'modified_date' in data:
                schema.modified_date = datetime.fromisoformat(data['modified_date'])
        except ValueError:
            # Use current time if date parsing fails
            pass

        # Load fields
        for field_data in data.get('fields', []):
            try:
                field = IndexField.from_dict(field_data)
                schema.fields.append(field)
            except Exception as e:
                raise SchemaValidationError(f"Error loading field '{field_data.get('name', 'unknown')}': {e}")

        return schema

    def clone(self) -> 'IndexSchema':
        """Create a copy of this schema."""
        return IndexSchema.from_json(self.to_json())

    def get_required_fields(self) -> List[IndexField]:
        """Get all required fields in this schema."""
        return [f for f in self.fields if f.required]

    def validate_assignment_values(self, values: Dict[str, str]) -> tuple[bool, List[str]]:
        """
        Validate a complete set of assignment values against this schema.

        Args:
            values: Dictionary mapping field names to values

        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors = []

        # Check all fields
        for field in self.fields:
            value = values.get(field.name)
            is_valid, error = field.validate_value(value)
            if not is_valid:
                errors.append(error)

        return len(errors) == 0, errors

    def get_field_summary(self) -> Dict[str, int]:
        """Get summary statistics about fields in this schema."""
        summary = {
            'total_fields': len(self.fields),
            'required_fields': len([f for f in self.fields if f.required]),
            'folder_fields': len(self.get_fields_by_role(FieldRole.FOLDER)),
            'filename_fields': len(self.get_fields_by_role(FieldRole.FILENAME)),
            'metadata_fields': len(self.get_fields_by_role(FieldRole.METADATA)),
        }

        # Count by type
        for field_type in FieldType:
            count = len([f for f in self.fields if f.field_type == field_type])
            summary[f'{field_type.value}_fields'] = count

        return summary

    def __str__(self) -> str:
        """String representation of schema."""
        field_count = len(self.fields)
        required_count = len([f for f in self.fields if f.required])
        return f"IndexSchema('{self.name}', {field_count} fields, {required_count} required)"

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (f"IndexSchema(name='{self.name}', description='{self.description[:50]}...', "
                f"fields={len(self.fields)}, created={self.created_date.date()})")


class SchemaBuilder:
    """
    Helper class for building schemas programmatically.

    Provides a fluent interface for creating schemas with validation.
    """

    def __init__(self, name: str, description: str = ""):
        self.schema = IndexSchema(name, description)

    def add_text_field(self, name: str, role: FieldRole = FieldRole.METADATA,
                       required: bool = False, **kwargs) -> 'SchemaBuilder':
        """Add a text field to the schema."""
        field = IndexField(name, FieldType.TEXT, role, required)

        # Set optional properties
        if 'default_value' in kwargs:
            field.default_value = kwargs['default_value']
        if 'min_length' in kwargs or 'max_length' in kwargs or 'pattern' in kwargs:
            rules = {}
            if 'min_length' in kwargs:
                rules['min_length'] = kwargs['min_length']
            if 'max_length' in kwargs:
                rules['max_length'] = kwargs['max_length']
            if 'pattern' in kwargs:
                rules['pattern'] = kwargs['pattern']
                rules['pattern_description'] = kwargs.get('pattern_description', 'required format')
            field.set_validation_rules(rules)

        if 'description' in kwargs:
            field.description = kwargs['description']
        if 'placeholder' in kwargs:
            field.placeholder_text = kwargs['placeholder']

        self.schema.add_field(field)
        return self

    def add_date_field(self, name: str, role: FieldRole = FieldRole.METADATA,
                       required: bool = False, **kwargs) -> 'SchemaBuilder':
        """Add a date field to the schema."""
        field = IndexField(name, FieldType.DATE, role, required)

        if 'default_value' in kwargs:
            field.default_value = kwargs['default_value']
        if 'min_date' in kwargs or 'max_date' in kwargs:
            rules = {}
            if 'min_date' in kwargs:
                rules['min_date'] = kwargs['min_date']
            if 'max_date' in kwargs:
                rules['max_date'] = kwargs['max_date']
            field.set_validation_rules(rules)

        if 'description' in kwargs:
            field.description = kwargs['description']

        self.schema.add_field(field)
        return self

    def add_number_field(self, name: str, role: FieldRole = FieldRole.METADATA,
                         required: bool = False, **kwargs) -> 'SchemaBuilder':
        """Add a number field to the schema."""
        field = IndexField(name, FieldType.NUMBER, role, required)

        if 'default_value' in kwargs:
            field.default_value = str(kwargs['default_value'])

        rules = {}
        if 'min_value' in kwargs:
            rules['min_value'] = kwargs['min_value']
        if 'max_value' in kwargs:
            rules['max_value'] = kwargs['max_value']
        if 'integer_only' in kwargs:
            rules['integer_only'] = kwargs['integer_only']
        if rules:
            field.set_validation_rules(rules)

        if 'description' in kwargs:
            field.description = kwargs['description']

        self.schema.add_field(field)
        return self

    def add_dropdown_field(self, name: str, options: List[str],
                           role: FieldRole = FieldRole.METADATA,
                           required: bool = False, **kwargs) -> 'SchemaBuilder':
        """Add a dropdown field to the schema."""
        field = IndexField(name, FieldType.DROPDOWN, role, required)
        field.dropdown_options = options

        if 'default_value' in kwargs:
            field.default_value = kwargs['default_value']
        if 'description' in kwargs:
            field.description = kwargs['description']

        self.schema.add_field(field)
        return self

    def add_boolean_field(self, name: str, role: FieldRole = FieldRole.METADATA,
                          required: bool = False, **kwargs) -> 'SchemaBuilder':
        """Add a boolean field to the schema."""
        field = IndexField(name, FieldType.BOOLEAN, role, required)

        if 'default_value' in kwargs:
            field.default_value = str(kwargs['default_value']).lower()
        if 'description' in kwargs:
            field.description = kwargs['description']

        self.schema.add_field(field)
        return self

    def set_filename_template(self, template: str) -> 'SchemaBuilder':
        """Set the filename generation template."""
        self.schema.filename_template = template
        return self

    def set_folder_separator(self, separator: str) -> 'SchemaBuilder':
        """Set the folder separator character."""
        self.schema.folder_separator = separator
        return self

    def set_metadata(self, **kwargs) -> 'SchemaBuilder':
        """Set schema metadata."""
        if 'author' in kwargs:
            self.schema.author = kwargs['author']
        if 'category' in kwargs:
            self.schema.category = kwargs['category']
        if 'tags' in kwargs:
            self.schema.tags = kwargs['tags']
        if 'version' in kwargs:
            self.schema.version = kwargs['version']
        return self

    def build(self) -> IndexSchema:
        """Build and validate the final schema."""
        is_valid, errors = self.schema.validate_schema()
        if not is_valid:
            raise SchemaValidationError(f"Schema validation failed: {'; '.join(errors)}")
        return self.schema


def create_default_schemas() -> List[IndexSchema]:
    """Create a set of default schemas for common document types."""
    schemas = []

    # General Documents Schema
    general = (SchemaBuilder("General Documents", "Basic document indexing")
               .add_text_field("Document Type", FieldRole.FOLDER, required=True,
                               description="Type of document (e.g., Invoice, Contract, Report)")
               .add_date_field("Document Date", FieldRole.FILENAME, required=True,
                               description="Date of the document")
               .add_text_field("Description", FieldRole.FILENAME, required=False,
                               description="Brief description of the document")
               .add_text_field("Category", FieldRole.FOLDER, required=False,
                               description="Document category for organization")
               .set_filename_template("{document_date}_{document_type}_{description}")
               .build())
    schemas.append(general)

    # Legal Documents Schema
    legal = (SchemaBuilder("Legal Documents", "Legal document management")
             .add_dropdown_field("Document Type",
                                 ["Contract", "Agreement", "Legal Notice", "Court Document", "Other"],
                                 FieldRole.FOLDER, required=True)
             .add_text_field("Case Number", FieldRole.FOLDER, required=False,
                             description="Case or matter number")
             .add_text_field("Client Name", FieldRole.FOLDER, required=True,
                             description="Client or party name")
             .add_date_field("Document Date", FieldRole.FILENAME, required=True)
             .add_text_field("Document Title", FieldRole.FILENAME, required=True,
                             description="Title or subject of document")
             .add_dropdown_field("Priority", ["Low", "Medium", "High", "Urgent"],
                                 FieldRole.METADATA, required=False)
             .set_filename_template("{document_date}_{document_title}")
             .build())
    schemas.append(legal)

    # Medical Records Schema
    medical = (SchemaBuilder("Medical Records", "Patient medical document management")
               .add_text_field("Patient ID", FieldRole.FOLDER, required=True,
                               description="Patient identifier")
               .add_text_field("Patient Name", FieldRole.FOLDER, required=True,
                               description="Patient full name")
               .add_dropdown_field("Document Type",
                                   ["Lab Results", "Doctor Notes", "Prescription", "Insurance", "Other"],
                                   FieldRole.FOLDER, required=True)
               .add_date_field("Service Date", FieldRole.FILENAME, required=True,
                               description="Date of service or document")
               .add_text_field("Provider", FieldRole.METADATA, required=False,
                               description="Healthcare provider name")
               .add_text_field("Notes", FieldRole.METADATA, required=False,
                               description="Additional notes")
               .set_filename_template("{service_date}_{document_type}")
               .build())
    schemas.append(medical)

    # Business Documents Schema
    business = (SchemaBuilder("Business Documents", "Business document organization")
                .add_dropdown_field("Department",
                                    ["Accounting", "HR", "Legal", "Marketing", "Operations", "Other"],
                                    FieldRole.FOLDER, required=True)
                .add_dropdown_field("Document Type",
                                    ["Invoice", "Receipt", "Contract", "Report", "Memo", "Other"],
                                    FieldRole.FOLDER, required=True)
                .add_date_field("Document Date", FieldRole.FILENAME, required=True)
                .add_text_field("Vendor/Client", FieldRole.FILENAME, required=False,
                                description="Vendor or client name")
                .add_text_field("Reference Number", FieldRole.FILENAME, required=False,
                                description="Invoice, PO, or reference number")
                .add_number_field("Amount", FieldRole.METADATA, required=False,
                                  description="Dollar amount if applicable")
                .set_filename_template("{document_date}_{reference_number}_{vendor_client}")
                .build())
    schemas.append(business)

    return schemas