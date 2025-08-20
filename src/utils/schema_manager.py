"""
Schema loading, saving, and management utilities.

Handles indexing schema persistence, validation, import/export,
and provides built-in default schemas for common document types.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from ..core.exceptions import SchemaValidationError, ConfigurationError
from ..core.signals import app_signals
from ..models.enums import FieldType, FieldRole


class SchemaManager:
    """Manages schema loading, saving, and validation."""

    def __init__(self, schemas_directory: Path):
        """
        Initialize schema manager.

        Args:
            schemas_directory: Directory to store schema files
        """
        self.schemas_directory = Path(schemas_directory)
        self.schemas_directory.mkdir(parents=True, exist_ok=True)

        # Schema cache
        self.loaded_schemas: Dict[str, 'IndexSchema'] = {}
        self.default_schema: Optional['IndexSchema'] = None
        self.schema_cache: Dict[str, 'IndexSchema'] = {}

        # File extension for schema files
        self.schema_extension = '.json'

        # Initialize with built-in schemas if directory is empty
        if not any(self.schemas_directory.glob(f'*{self.schema_extension}')):
            self._create_default_schemas()

        logging.debug(f"SchemaManager initialized with directory: {self.schemas_directory}")

    def load_schema(self, schema_name: str) -> Optional['IndexSchema']:
        """
        Load schema by name.

        Args:
            schema_name: Name of schema to load

        Returns:
            IndexSchema object or None if not found

        Raises:
            SchemaValidationError: If schema file is invalid
        """
        try:
            # Check cache first
            if schema_name in self.schema_cache:
                logging.debug(f"Returning cached schema: {schema_name}")
                return self.schema_cache[schema_name]

            # Build file path
            schema_file = self.schemas_directory / f"{schema_name}{self.schema_extension}"

            if not schema_file.exists():
                logging.warning(f"Schema file not found: {schema_file}")
                return None

            logging.info(f"Loading schema from: {schema_file}")

            # Load and parse JSON
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema_data = json.load(f)

            # Import here to avoid circular imports
            from ..models.schema import IndexSchema

            # Create schema from JSON data
            schema = IndexSchema.from_dict(schema_data)

            # Validate schema
            validation_errors = self._validate_schema_data(schema)
            if validation_errors:
                error_msg = f"Schema validation failed: {'; '.join(validation_errors)}"
                raise SchemaValidationError(error_msg)

            # Cache the schema
            self.schema_cache[schema_name] = schema

            logging.info(f"Successfully loaded schema: {schema_name}")
            app_signals.schema_loaded.emit(schema)

            return schema

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in schema file {schema_name}: {e}"
            logging.error(error_msg)
            raise SchemaValidationError(error_msg)

        except Exception as e:
            error_msg = f"Failed to load schema {schema_name}: {e}"
            logging.error(error_msg)
            raise SchemaValidationError(error_msg)

    def save_schema(self, schema: 'IndexSchema', name: str = None) -> bool:
        """
        Save schema with given name.

        Args:
            schema: IndexSchema object to save
            name: Name to save under (uses schema.name if None)

        Returns:
            bool: True if successful

        Raises:
            SchemaValidationError: If schema is invalid
        """
        try:
            save_name = name or schema.name
            if not save_name:
                raise SchemaValidationError("Schema must have a name to save")

            # Validate schema before saving
            validation_errors = self._validate_schema_data(schema)
            if validation_errors:
                error_msg = f"Cannot save invalid schema: {'; '.join(validation_errors)}"
                raise SchemaValidationError(error_msg)

            schema_file = self.schemas_directory / f"{save_name}{self.schema_extension}"

            logging.info(f"Saving schema to: {schema_file}")

            # Create backup if file exists
            if schema_file.exists():
                backup_file = schema_file.with_suffix(f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                shutil.copy2(schema_file, backup_file)
                logging.debug(f"Created backup: {backup_file}")

            # Update schema metadata
            schema.modified_date = datetime.now()
            if not hasattr(schema, 'created_date') or not schema.created_date:
                schema.created_date = schema.modified_date

            # Convert to dictionary and save
            schema_data = schema.to_dict()

            with open(schema_file, 'w', encoding='utf-8') as f:
                json.dump(schema_data, f, indent=2, ensure_ascii=False, default=self._json_serializer)

            # Update cache
            self.schema_cache[save_name] = schema

            logging.info(f"Successfully saved schema: {save_name}")
            app_signals.schema_saved.emit(save_name)

            return True

        except Exception as e:
            error_msg = f"Failed to save schema {save_name}: {e}"
            logging.error(error_msg)
            raise SchemaValidationError(error_msg)

    def delete_schema(self, schema_name: str) -> bool:
        """
        Delete schema by name.

        Args:
            schema_name: Name of schema to delete

        Returns:
            bool: True if successful
        """
        try:
            schema_file = self.schemas_directory / f"{schema_name}{self.schema_extension}"

            if not schema_file.exists():
                logging.warning(f"Schema file does not exist: {schema_file}")
                return False

            # Create backup before deletion
            backup_dir = self.schemas_directory / "deleted"
            backup_dir.mkdir(exist_ok=True)

            backup_file = backup_dir / f"{schema_name}_deleted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            shutil.copy2(schema_file, backup_file)

            # Delete the file
            schema_file.unlink()

            # Remove from cache
            self.schema_cache.pop(schema_name, None)

            logging.info(f"Deleted schema: {schema_name}")
            app_signals.schema_deleted.emit(schema_name)

            return True

        except Exception as e:
            logging.error(f"Failed to delete schema {schema_name}: {e}")
            return False

    def list_available_schemas(self) -> List[str]:
        """
        Return list of available schema names.

        Returns:
            List of schema names (without file extensions)
        """
        try:
            schema_files = self.schemas_directory.glob(f'*{self.schema_extension}')
            schema_names = [f.stem for f in schema_files if f.is_file()]
            schema_names.sort()

            logging.debug(f"Found {len(schema_names)} schemas")
            return schema_names

        except Exception as e:
            logging.error(f"Error listing schemas: {e}")
            return []

    def get_schema_info(self, schema_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a schema without loading it fully.

        Args:
            schema_name: Name of schema

        Returns:
            Dictionary with schema information or None if not found
        """
        try:
            schema_file = self.schemas_directory / f"{schema_name}{self.schema_extension}"

            if not schema_file.exists():
                return None

            # Get file stats
            file_stats = schema_file.stat()

            # Load just the metadata
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema_data = json.load(f)

            info = {
                'name': schema_data.get('name', schema_name),
                'description': schema_data.get('description', ''),
                'field_count': len(schema_data.get('fields', [])),
                'file_size': file_stats.st_size,
                'modified_date': datetime.fromtimestamp(file_stats.st_mtime),
                'created_date': schema_data.get('created_date'),
                'version': schema_data.get('version', '1.0'),
            }

            return info

        except Exception as e:
            logging.error(f"Error getting schema info for {schema_name}: {e}")
            return None

    def validate_schema_compatibility(self, schema: 'IndexSchema') -> List[str]:
        """
        Validate schema structure and compatibility.

        Args:
            schema: Schema to validate

        Returns:
            List of validation error messages
        """
        return self._validate_schema_data(schema)

    def import_schema_from_file(self, file_path: Path, new_name: str = None) -> bool:
        """
        Import schema from external file.

        Args:
            file_path: Path to schema file to import
            new_name: Optional new name for imported schema

        Returns:
            bool: True if successful

        Raises:
            SchemaValidationError: If import fails
        """
        try:
            file_path = Path(file_path)

            if not file_path.exists():
                raise SchemaValidationError(f"Import file not found: {file_path}")

            logging.info(f"Importing schema from: {file_path}")

            # Load and validate
            with open(file_path, 'r', encoding='utf-8') as f:
                schema_data = json.load(f)

            from ..models.schema import IndexSchema
            schema = IndexSchema.from_dict(schema_data)

            # Set new name if provided
            if new_name:
                schema.name = new_name

            # Validate
            validation_errors = self._validate_schema_data(schema)
            if validation_errors:
                error_msg = f"Invalid schema file: {'; '.join(validation_errors)}"
                raise SchemaValidationError(error_msg)

            # Save imported schema
            self.save_schema(schema)

            logging.info(f"Successfully imported schema: {schema.name}")
            return True

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in import file: {e}"
            logging.error(error_msg)
            raise SchemaValidationError(error_msg)

        except Exception as e:
            error_msg = f"Schema import failed: {e}"
            logging.error(error_msg)
            raise SchemaValidationError(error_msg)

    def export_schema_to_file(self, schema: 'IndexSchema', file_path: Path) -> bool:
        """
        Export schema to external file.

        Args:
            schema: Schema to export
            file_path: Destination file path

        Returns:
            bool: True if successful
        """
        try:
            file_path = Path(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            logging.info(f"Exporting schema {schema.name} to: {file_path}")

            # Add export metadata
            schema_data = schema.to_dict()
            schema_data['_export_info'] = {
                'exported_at': datetime.now().isoformat(),
                'exported_by': 'Scanner Extension',
                'version': '1.0'
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(schema_data, f, indent=2, ensure_ascii=False, default=self._json_serializer)

            logging.info(f"Successfully exported schema: {schema.name}")
            return True

        except Exception as e:
            logging.error(f"Schema export failed: {e}")
            return False

    def create_default_schemas(self) -> bool:
        """
        Create built-in default schemas.

        Returns:
            bool: True if successful
        """
        return self._create_default_schemas()

    def _create_default_schemas(self) -> bool:
        """Create default schemas for common document types."""
        try:
            logging.info("Creating default schemas")

            from ..models.schema import IndexSchema, IndexField

            # General Documents Schema
            general_schema = IndexSchema("general", "General document indexing")
            general_schema.add_field(IndexField("document_type", FieldType.DROPDOWN, FieldRole.FOLDER,
                                               required=True, dropdown_options=["Invoice", "Receipt", "Contract", "Letter", "Report", "Other"]))
            general_schema.add_field(IndexField("date", FieldType.DATE, FieldRole.FILENAME, required=True))
            general_schema.add_field(IndexField("description", FieldType.TEXT, FieldRole.FILENAME, required=True))
            general_schema.add_field(IndexField("notes", FieldType.TEXT, FieldRole.METADATA))

            # Business Documents Schema
            business_schema = IndexSchema("business", "Business document management")
            business_schema.add_field(IndexField("department", FieldType.DROPDOWN, FieldRole.FOLDER,
                                                required=True, dropdown_options=["HR", "Finance", "Legal", "Operations", "Marketing", "IT"]))
            business_schema.add_field(IndexField("document_type", FieldType.DROPDOWN, FieldRole.FOLDER,
                                                required=True, dropdown_options=["Invoice", "Purchase Order", "Contract", "Policy", "Memo", "Report"]))
            business_schema.add_field(IndexField("date", FieldType.DATE, FieldRole.FILENAME, required=True))
            business_schema.add_field(IndexField("vendor_client", FieldType.TEXT, FieldRole.FILENAME))
            business_schema.add_field(IndexField("amount", FieldType.NUMBER, FieldRole.METADATA))
            business_schema.add_field(IndexField("reference_number", FieldType.TEXT, FieldRole.FILENAME))

            # Legal Documents Schema
            legal_schema = IndexSchema("legal", "Legal document organization")
            legal_schema.add_field(IndexField("case_number", FieldType.TEXT, FieldRole.FOLDER, required=True))
            legal_schema.add_field(IndexField("document_type", FieldType.DROPDOWN, FieldRole.FOLDER,
                                             required=True, dropdown_options=["Pleading", "Discovery", "Correspondence", "Contract", "Brief", "Order", "Other"]))
            legal_schema.add_field(IndexField("date", FieldType.DATE, FieldRole.FILENAME, required=True))
            legal_schema.add_field(IndexField("party", FieldType.TEXT, FieldRole.FILENAME))
            legal_schema.add_field(IndexField("attorney", FieldType.TEXT, FieldRole.METADATA))
            legal_schema.add_field(IndexField("confidential", FieldType.BOOLEAN, FieldRole.METADATA))

            # Medical Records Schema
            medical_schema = IndexSchema("medical", "Medical records management")
            medical_schema.add_field(IndexField("patient_id", FieldType.TEXT, FieldRole.FOLDER, required=True))
            medical_schema.add_field(IndexField("date", FieldType.DATE, FieldRole.FILENAME, required=True))
            medical_schema.add_field(IndexField("provider", FieldType.TEXT, FieldRole.FILENAME))
            medical_schema.add_field(IndexField("diagnosis", FieldType.TEXT, FieldRole.METADATA))
            medical_schema.add_field(IndexField("confidential", FieldType.BOOLEAN, FieldRole.METADATA, default_value="true"))

            # Personal Documents Schema
            personal_schema = IndexSchema("personal", "Personal document filing")
            personal_schema.add_field(IndexField("category", FieldType.DROPDOWN, FieldRole.FOLDER,
                                                required=True, dropdown_options=["Financial", "Insurance", "Medical", "Legal", "Education", "Personal", "Home", "Auto"]))
            personal_schema.add_field(IndexField("document_type", FieldType.TEXT, FieldRole.FOLDER, required=True))
            personal_schema.add_field(IndexField("date", FieldType.DATE, FieldRole.FILENAME, required=True))
            personal_schema.add_field(IndexField("description", FieldType.TEXT, FieldRole.FILENAME, required=True))
            personal_schema.add_field(IndexField("important", FieldType.BOOLEAN, FieldRole.METADATA))

            # Save all default schemas
            schemas_to_create = [
                general_schema,
                business_schema,
                legal_schema,
                medical_schema,
                personal_schema
            ]

            success_count = 0
            for schema in schemas_to_create:
                try:
                    schema.created_date = datetime.now()
                    schema.modified_date = schema.created_date
                    self.save_schema(schema)
                    success_count += 1
                except Exception as e:
                    logging.error(f"Failed to create default schema {schema.name}: {e}")

            # Set general as default
            if success_count > 0:
                self.default_schema = general_schema

            logging.info(f"Created {success_count} default schemas")
            return success_count > 0

        except Exception as e:
            logging.error(f"Error creating default schemas: {e}")
            return False

    def backup_schemas(self) -> Optional[Path]:
        """
        Create backup of all schemas.

        Returns:
            Path to backup directory if successful, None otherwise
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = self.schemas_directory.parent / f"schema_backup_{timestamp}"
            backup_dir.mkdir(parents=True, exist_ok=True)

            schema_files = list(self.schemas_directory.glob(f'*{self.schema_extension}'))

            if not schema_files:
                logging.warning("No schemas found to backup")
                return None

            for schema_file in schema_files:
                backup_file = backup_dir / schema_file.name
                shutil.copy2(schema_file, backup_file)

            logging.info(f"Backed up {len(schema_files)} schemas to: {backup_dir}")
            return backup_dir

        except Exception as e:
            logging.error(f"Schema backup failed: {e}")
            return None

    def restore_schemas(self, backup_path: Path) -> bool:
        """
        Restore schemas from backup.

        Args:
            backup_path: Path to backup directory

        Returns:
            bool: True if successful
        """
        try:
            backup_path = Path(backup_path)

            if not backup_path.exists() or not backup_path.is_dir():
                raise ConfigurationError(f"Backup directory not found: {backup_path}")

            backup_files = list(backup_path.glob(f'*{self.schema_extension}'))

            if not backup_files:
                raise ConfigurationError(f"No schema files found in backup: {backup_path}")

            logging.info(f"Restoring {len(backup_files)} schemas from: {backup_path}")

            # Create backup of current schemas first
            current_backup = self.backup_schemas()
            if current_backup:
                logging.info(f"Current schemas backed up to: {current_backup}")

            # Clear cache
            self.schema_cache.clear()

            # Copy backup files
            restored_count = 0
            for backup_file in backup_files:
                try:
                    target_file = self.schemas_directory / backup_file.name
                    shutil.copy2(backup_file, target_file)
                    restored_count += 1
                except Exception as e:
                    logging.error(f"Failed to restore {backup_file.name}: {e}")

            logging.info(f"Restored {restored_count} schema files")
            return restored_count > 0

        except Exception as e:
            error_msg = f"Schema restore failed: {e}"
            logging.error(error_msg)
            raise ConfigurationError(error_msg)

    def _validate_schema_data(self, schema: 'IndexSchema') -> List[str]:
        """Validate schema data structure."""
        errors = []

        try:
            # Check basic properties
            if not schema.name or not schema.name.strip():
                errors.append("Schema must have a name")

            if not schema.fields:
                errors.append("Schema must have at least one field")

            # Check for at least one filename field
            filename_fields = [f for f in schema.fields if f.role == FieldRole.FILENAME]
            if not filename_fields:
                errors.append("Schema must have at least one field with FILENAME role")

            # Validate individual fields
            field_names = set()
            for i, field in enumerate(schema.fields):
                # Check for duplicate field names
                if field.name in field_names:
                    errors.append(f"Duplicate field name: {field.name}")
                field_names.add(field.name)

                # Validate field name format
                if not field.name or not field.name.strip():
                    errors.append(f"Field at index {i} has empty name")
                elif not field.name.replace('_', '').replace('-', '').isalnum():
                    errors.append(f"Field name '{field.name}' contains invalid characters")

                # Validate dropdown fields
                if field.field_type == FieldType.DROPDOWN:
                    if not field.dropdown_options:
                        errors.append(f"Dropdown field '{field.name}' has no options")
                    elif len(field.dropdown_options) < 2:
                        errors.append(f"Dropdown field '{field.name}' must have at least 2 options")

            # Check folder structure generation
            try:
                test_values = {field.name: "test" for field in schema.fields}
                schema.generate_folder_structure(test_values)
                schema.generate_filename(test_values)
            except Exception as e:
                errors.append(f"Schema cannot generate valid paths: {e}")

        except Exception as e:
            errors.append(f"Schema validation error: {e}")

        return errors

    def _json_serializer(self, obj):
        """JSON serializer for datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    def get_default_schema(self) -> Optional['IndexSchema']:
        """Get the default schema."""
        if not self.default_schema:
            # Try to load general schema as default
            schemas = self.list_available_schemas()
            if 'general' in schemas:
                self.default_schema = self.load_schema('general')
            elif schemas:
                self.default_schema = self.load_schema(schemas[0])

        return self.default_schema

    def set_default_schema(self, schema_name: str) -> bool:
        """
        Set the default schema.

        Args:
            schema_name: Name of schema to set as default

        Returns:
            bool: True if successful
        """
        try:
            schema = self.load_schema(schema_name)
            if schema:
                self.default_schema = schema
                logging.info(f"Set default schema to: {schema_name}")
                return True
            return False
        except Exception as e:
            logging.error(f"Failed to set default schema: {e}")
            return False

    def get_schemas_summary(self) -> Dict[str, Any]:
        """Get summary information about all schemas."""
        summary = {
            'total_schemas': 0,
            'schemas': {},
            'default_schema': self.default_schema.name if self.default_schema else None,
            'directory': str(self.schemas_directory),
            'cache_size': len(self.schema_cache)
        }

        try:
            schema_names = self.list_available_schemas()
            summary['total_schemas'] = len(schema_names)

            for name in schema_names:
                info = self.get_schema_info(name)
                if info:
                    summary['schemas'][name] = info

        except Exception as e:
            logging.error(f"Error getting schemas summary: {e}")

        return summary

    def clear_cache(self):
        """Clear the schema cache."""
        self.schema_cache.clear()
        logging.debug("Schema cache cleared")

    def refresh_schema(self, schema_name: str) -> Optional['IndexSchema']:
        """
        Refresh a schema by reloading from file.

        Args:
            schema_name: Name of schema to refresh

        Returns:
            Refreshed schema or None if not found
        """
        try:
            # Remove from cache
            self.schema_cache.pop(schema_name, None)

            # Reload from file
            return self.load_schema(schema_name)

        except Exception as e:
            logging.error(f"Failed to refresh schema {schema_name}: {e}")
            return None

    def duplicate_schema(self, source_name: str, new_name: str) -> bool:
        """
        Duplicate an existing schema with a new name.

        Args:
            source_name: Name of schema to duplicate
            new_name: Name for the duplicated schema

        Returns:
            bool: True if successful
        """
        try:
            # Load source schema
            source_schema = self.load_schema(source_name)
            if not source_schema:
                return False

            # Clone the schema
            cloned_schema = source_schema.clone()
            cloned_schema.name = new_name
            cloned_schema.description = f"Copy of {source_schema.description}"
            cloned_schema.created_date = datetime.now()
            cloned_schema.modified_date = cloned_schema.created_date

            # Save the duplicate
            return self.save_schema(cloned_schema)

        except Exception as e:
            logging.error(f"Failed to duplicate schema {source_name} to {new_name}: {e}")
            return False

    def cleanup_old_backups(self, max_backups: int = 10):
        """
        Clean up old backup files.

        Args:
            max_backups: Maximum number of backup files to keep
        """
        try:
            backup_dirs = []

            # Find backup directories
            parent_dir = self.schemas_directory.parent
            for item in parent_dir.iterdir():
                if item.is_dir() and item.name.startswith('schema_backup_'):
                    backup_dirs.append(item)

            # Sort by creation time
            backup_dirs.sort(key=lambda x: x.stat().st_ctime, reverse=True)

            # Remove old backups
            if len(backup_dirs) > max_backups:
                for old_backup in backup_dirs[max_backups:]:
                    shutil.rmtree(old_backup)
                    logging.debug(f"Removed old backup: {old_backup}")

            logging.info(f"Cleaned up schema backups, kept {min(len(backup_dirs), max_backups)} most recent")

        except Exception as e:
            logging.warning(f"Failed to cleanup old backups: {e}")
