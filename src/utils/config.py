"""
Application settings and preferences management.

Handles loading, saving, and managing application configuration with
validation, defaults, and backup/restore capabilities.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union
from datetime import datetime
import shutil

from ..core.exceptions import ConfigurationError
from ..core.signals import app_signals


class ConfigurationManager:
    """Application settings and preferences management."""

    def __init__(self, config_file_path: Union[str, Path]):
        """
        Initialize configuration manager.

        Args:
            config_file_path: Path to main configuration file
        """
        self.config_file_path = Path(config_file_path)
        self.config_file_path.parent.mkdir(parents=True, exist_ok=True)

        # User data directory
        self.user_data_directory = self.config_file_path.parent

        # Current settings storage
        self.current_settings: Dict[str, Any] = {}

        # Default settings template
        self.default_settings = {
            "application": {
                "name": "Scanner Extension",
                "version": "1.0.0",
                "default_schema": "general",
                "auto_save": True,
                "auto_save_interval": 300,  # seconds
                "max_recent_files": 10,
                "language": "en",
                "theme": "default"
            },
            "ui": {
                "default_thumbnail_size": 150,
                "max_thumbnails_per_row": 6,
                "window_title_template": "{app_name} - {batch_name}",
                "show_page_numbers": True,
                "show_assignment_indicators": True,
                "zoom_step": 0.25,
                "default_zoom": 1.0
            },
            "window": {
                "geometry": None,
                "state": None,
                "maximized": False,
                "remember_layout": True
            },
            "processing": {
                "max_batch_size": 100,
                "scan_timeout_seconds": 30,
                "parallel_processing": True,
                "max_worker_threads": 4,
                "temp_file_cleanup": True,
                "backup_originals": False
            },
            "thumbnails": {
                "cache_size_mb": 100,
                "cache_cleanup_interval": 3600,  # seconds
                "thumbnail_quality": "medium",
                "generate_on_demand": True,
                "cache_thumbnails": True
            },
            "export": {
                "default_quality": "medium",
                "default_naming_strategy": "timestamp",
                "create_index_by_default": True,
                "default_output_directory": str(Path.home() / "Documents" / "Scanned Documents"),
                "preserve_timestamps": True,
                "compress_output": False,
                "conflict_resolution": "prompt"
            },
            "monitoring": {
                "watch_directory": "",
                "auto_start_monitoring": False,
                "file_detection_delay": 2.0,  # seconds
                "supported_extensions": [".pdf"],
                "ignore_hidden_files": True
            },
            "validation": {
                "strict_validation": True,
                "warn_on_conflicts": True,
                "auto_fix_paths": True,
                "validate_on_assignment": True
            },
            "cache": {
                "max_size_mb": 500,
                "cleanup_on_startup": True,
                "max_age_days": 30
            },
            "logging": {
                "level": "INFO",
                "log_to_file": True,
                "max_log_files": 5,
                "max_log_size_mb": 10
            }
        }

        logging.debug(f"Configuration manager initialized with file: {self.config_file_path}")

    def load_application_config(self) -> bool:
        """
        Load configuration from file.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if self.config_file_path.exists():
                logging.info(f"Loading configuration from {self.config_file_path}")

                with open(self.config_file_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)

                # Merge with defaults to ensure all keys exist
                self.current_settings = self._merge_settings(self.default_settings, loaded_config)

                # Validate configuration
                self._validate_configuration()

                logging.info("Configuration loaded successfully")
            else:
                logging.info("Configuration file not found, using defaults")
                self.current_settings = self.default_settings.copy()

                # Save default configuration
                self.save_application_config()

            app_signals.config_loaded.emit()
            return True

        except json.JSONDecodeError as e:
            logging.error(f"Configuration file is corrupted: {e}")
            self._handle_corrupted_config()
            return False

        except Exception as e:
            logging.error(f"Failed to load configuration: {e}")
            self.current_settings = self.default_settings.copy()
            return False

    def save_application_config(self) -> bool:
        """
        Save current configuration to file.

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create backup of existing config
            if self.config_file_path.exists():
                self._create_backup()

            # Ensure directory exists
            self.config_file_path.parent.mkdir(parents=True, exist_ok=True)

            # Add save timestamp
            save_config = self.current_settings.copy()
            save_config['_metadata'] = {
                'last_saved': datetime.now().isoformat(),
                'version': self.get_setting('application.version', '1.0.0')
            }

            # Write configuration
            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                json.dump(save_config, f, indent=2, ensure_ascii=False)

            logging.info("Configuration saved successfully")
            app_signals.config_saved.emit()
            return True

        except Exception as e:
            error_msg = f"Failed to save configuration: {e}"
            logging.error(error_msg)
            raise ConfigurationError(error_msg)

    def get_setting(self, key: str, default_value: Any = None) -> Any:
        """
        Get a configuration setting by key path.

        Args:
            key: Setting key in dot notation (e.g., 'ui.thumbnail_size')
            default_value: Default value if key not found

        Returns:
            Configuration value or default
        """
        try:
            keys = key.split('.')
            value = self.current_settings

            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default_value

            return value

        except Exception as e:
            logging.debug(f"Error getting setting '{key}': {e}")
            return default_value

    def set_setting(self, key: str, value: Any) -> bool:
        """
        Set a configuration setting by key path.

        Args:
            key: Setting key in dot notation
            value: Value to set

        Returns:
            bool: True if successful
        """
        try:
            keys = key.split('.')
            target = self.current_settings

            # Navigate to parent of target key
            for k in keys[:-1]:
                if k not in target:
                    target[k] = {}
                target = target[k]

            # Set the final key
            old_value = target.get(keys[-1])
            target[keys[-1]] = value

            # Emit change signal if value actually changed
            if old_value != value:
                app_signals.config_changed.emit(key, value)
                logging.debug(f"Setting '{key}' changed from {old_value} to {value}")

            return True

        except Exception as e:
            logging.error(f"Failed to set setting '{key}': {e}")
            return False

    def reset_to_defaults(self) -> bool:
        """
        Reset all settings to defaults.

        Returns:
            bool: True if successful
        """
        try:
            logging.info("Resetting configuration to defaults")

            # Create backup before reset
            if self.config_file_path.exists():
                backup_path = self._create_backup("pre_reset")
                logging.info(f"Configuration backup created: {backup_path}")

            self.current_settings = self.default_settings.copy()
            self.save_application_config()

            app_signals.config_reset.emit()
            logging.info("Configuration reset to defaults")
            return True

        except Exception as e:
            error_msg = f"Failed to reset configuration: {e}"
            logging.error(error_msg)
            raise ConfigurationError(error_msg)

    def validate_configuration(self) -> bool:
        """
        Validate current configuration integrity.

        Returns:
            bool: True if valid, False otherwise
        """
        try:
            return self._validate_configuration()
        except ConfigurationError:
            return False

    def _validate_configuration(self):
        """Internal configuration validation."""
        errors = []

        # Validate required sections
        required_sections = ['application', 'ui', 'processing', 'export']
        for section in required_sections:
            if section not in self.current_settings:
                errors.append(f"Missing required section: {section}")

        # Validate specific settings
        validations = [
            ('ui.default_thumbnail_size', int, lambda x: x > 0),
            ('ui.max_thumbnails_per_row', int, lambda x: x > 0),
            ('processing.max_batch_size', int, lambda x: x > 0),
            ('processing.scan_timeout_seconds', (int, float), lambda x: x > 0),
            ('thumbnails.cache_size_mb', int, lambda x: x > 0),
            ('export.default_quality', str, lambda x: x in ['low', 'medium', 'high', 'original']),
            ('cache.max_size_mb', int, lambda x: x > 0),
        ]

        for key, expected_type, validator in validations:
            value = self.get_setting(key)
            if value is not None:
                if not isinstance(value, expected_type):
                    errors.append(f"Setting '{key}' must be of type {expected_type.__name__}")
                elif not validator(value):
                    errors.append(f"Setting '{key}' has invalid value: {value}")

        # Validate paths
        path_settings = [
            'export.default_output_directory',
            'monitoring.watch_directory'
        ]

        for key in path_settings:
            path_value = self.get_setting(key)
            if path_value and not self._is_valid_path(path_value):
                errors.append(f"Invalid path for setting '{key}': {path_value}")

        if errors:
            error_msg = "Configuration validation failed: " + "; ".join(errors)
            raise ConfigurationError(error_msg)

        logging.debug("Configuration validation passed")

    def _is_valid_path(self, path_str: str) -> bool:
        """Check if a path string is valid."""
        try:
            path = Path(path_str)
            # Just check if path can be created - don't require it to exist
            return True
        except (ValueError, OSError):
            return False

    def backup_configuration(self) -> Optional[Path]:
        """
        Create a backup of current configuration.

        Returns:
            Path to backup file if successful, None otherwise
        """
        try:
            return self._create_backup("manual")
        except Exception as e:
            logging.error(f"Failed to create configuration backup: {e}")
            return None

    def restore_configuration(self, backup_path: Union[str, Path]) -> bool:
        """
        Restore configuration from backup.

        Args:
            backup_path: Path to backup file

        Returns:
            bool: True if successful
        """
        backup_path = Path(backup_path)

        try:
            if not backup_path.exists():
                raise ConfigurationError(f"Backup file not found: {backup_path}")

            logging.info(f"Restoring configuration from {backup_path}")

            # Create backup of current config before restore
            self._create_backup("pre_restore")

            # Load backup
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_config = json.load(f)

            # Remove metadata if present
            if '_metadata' in backup_config:
                del backup_config['_metadata']

            # Merge with defaults and validate
            self.current_settings = self._merge_settings(self.default_settings, backup_config)
            self._validate_configuration()

            # Save restored configuration
            self.save_application_config()

            logging.info("Configuration restored successfully")
            return True

        except Exception as e:
            error_msg = f"Failed to restore configuration from {backup_path}: {e}"
            logging.error(error_msg)
            raise ConfigurationError(error_msg)

    def _create_backup(self, suffix: str = "") -> Path:
        """Create a backup of current configuration file."""
        if not self.config_file_path.exists():
            raise ConfigurationError("No configuration file exists to backup")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"config_backup_{timestamp}"
        if suffix:
            backup_name += f"_{suffix}"
        backup_name += ".json"

        backup_dir = self.user_data_directory / "backups"
        backup_dir.mkdir(exist_ok=True)
        backup_path = backup_dir / backup_name

        shutil.copy2(self.config_file_path, backup_path)
        logging.debug(f"Configuration backup created: {backup_path}")
        return backup_path

    def _handle_corrupted_config(self):
        """Handle corrupted configuration file."""
        try:
            # Move corrupted file to backup
            corrupted_name = f"config_corrupted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            corrupted_path = self.user_data_directory / "backups" / corrupted_name
            corrupted_path.parent.mkdir(exist_ok=True)

            shutil.move(self.config_file_path, corrupted_path)
            logging.warning(f"Corrupted config moved to: {corrupted_path}")

            # Reset to defaults
            self.current_settings = self.default_settings.copy()
            self.save_application_config()

        except Exception as e:
            logging.error(f"Failed to handle corrupted configuration: {e}")
            self.current_settings = self.default_settings.copy()

    def _merge_settings(self, defaults: Dict[str, Any], user_settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively merge user settings with defaults.

        Args:
            defaults: Default settings dictionary
            user_settings: User settings dictionary

        Returns:
            Merged settings dictionary
        """
        result = defaults.copy()

        for key, value in user_settings.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_settings(result[key], value)
            else:
                result[key] = value

        return result

    def get_user_data_directory(self) -> Path:
        """Get user data directory path."""
        return self.user_data_directory

    def get_temp_directory(self) -> Path:
        """Get temporary directory path."""
        temp_dir = self.user_data_directory / "temp"
        temp_dir.mkdir(exist_ok=True)
        return temp_dir

    def get_cache_directory(self) -> Path:
        """Get cache directory path."""
        cache_dir = self.user_data_directory / "cache"
        cache_dir.mkdir(exist_ok=True)
        return cache_dir

    def get_logs_directory(self) -> Path:
        """Get logs directory path."""
        logs_dir = self.user_data_directory / "logs"
        logs_dir.mkdir(exist_ok=True)
        return logs_dir

    def get_backup_directory(self) -> Path:
        """Get backups directory path."""
        backup_dir = self.user_data_directory / "backups"
        backup_dir.mkdir(exist_ok=True)
        return backup_dir

    def cleanup_old_backups(self, max_backups: int = 10):
        """
        Clean up old backup files.

        Args:
            max_backups: Maximum number of backup files to keep
        """
        try:
            backup_dir = self.get_backup_directory()
            backup_files = list(backup_dir.glob("config_backup_*.json"))

            if len(backup_files) > max_backups:
                # Sort by modification time, oldest first
                backup_files.sort(key=lambda x: x.stat().st_mtime)

                # Remove oldest files
                files_to_remove = backup_files[:-max_backups]
                for file_path in files_to_remove:
                    file_path.unlink()
                    logging.debug(f"Removed old backup: {file_path.name}")

                logging.info(f"Cleaned up {len(files_to_remove)} old backup files")

        except Exception as e:
            logging.warning(f"Failed to cleanup old backups: {e}")

    # Convenience methods for common settings
    def get_thumbnail_size(self) -> int:
        """Get thumbnail size setting."""
        return self.get_setting('ui.default_thumbnail_size', 150)

    def get_max_thumbnails_per_row(self) -> int:
        """Get max thumbnails per row setting."""
        return self.get_setting('ui.max_thumbnails_per_row', 6)

    def get_default_output_directory(self) -> Path:
        """Get default output directory."""
        path_str = self.get_setting('export.default_output_directory',
                                    str(Path.home() / "Documents" / "Scanned Documents"))
        return Path(path_str)

    def get_cache_size_limit(self) -> int:
        """Get cache size limit in MB."""
        return self.get_setting('cache.max_size_mb', 500)

    def is_auto_save_enabled(self) -> bool:
        """Check if auto-save is enabled."""
        return self.get_setting('application.auto_save', True)

    def get_auto_save_interval(self) -> int:
        """Get auto-save interval in seconds."""
        return self.get_setting('application.auto_save_interval', 300)

    def should_remember_window_layout(self) -> bool:
        """Check if window layout should be remembered."""
        return self.get_setting('window.remember_layout', True)

