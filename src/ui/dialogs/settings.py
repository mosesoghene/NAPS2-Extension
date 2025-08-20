"""
Application settings and preferences dialog.

Provides comprehensive interface for configuring all application settings
organized into logical tabs with validation and default value management.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QTabWidget, QWidget, QGroupBox, QLabel, QLineEdit, QPushButton,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QSlider,
    QFileDialog, QColorDialog, QFontDialog, QButtonGroup,
    QRadioButton, QTextEdit, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QStandardPaths
from PySide6.QtGui import QFont, QColor, QPalette

from src.utils.config import ConfigurationManager
from src.models.enums import ThumbnailSize, ConflictResolution, PDFQuality
from src.core.signals import app_signals


class SettingsDialog(QDialog):
    """Application settings and preferences dialog."""

    # Signals
    settings_applied = Signal(dict)  # settings_dict
    settings_reset = Signal()

    def __init__(self, config_manager: ConfigurationManager, parent=None):
        super().__init__(parent)

        self.config_manager = config_manager
        self.settings_widgets = {}
        self.modified_settings = {}
        self.has_changes = False

        self._setup_ui()
        self._load_current_settings()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the settings dialog UI."""
        self.setWindowTitle("Application Settings")
        self.setModal(True)
        self.resize(700, 600)

        layout = QVBoxLayout(self)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create tabs
        self._create_general_tab()
        self._create_scanning_tab()
        self._create_export_tab()
        self._create_appearance_tab()
        self._create_advanced_tab()

        # Button layout
        button_layout = QHBoxLayout()

        self.restore_defaults_button = QPushButton("Restore Defaults")
        self.restore_defaults_button.clicked.connect(self._restore_defaults)
        button_layout.addWidget(self.restore_defaults_button)

        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.apply_button = QPushButton("Apply")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_settings)
        button_layout.addWidget(self.apply_button)

        self.ok_button = QPushButton("OK")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self._ok_clicked)
        button_layout.addWidget(self.ok_button)

        layout.addLayout(button_layout)

    def _create_general_tab(self) -> QWidget:
        """Create general settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Application settings
        app_group = QGroupBox("Application Settings")
        app_layout = QFormLayout(app_group)

        # Language selection
        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "Spanish", "French", "German"])
        app_layout.addRow("Language:", self.language_combo)
        self.settings_widgets["application.language"] = self.language_combo

        # Auto-save settings
        self.auto_save_check = QCheckBox("Enable auto-save")
        app_layout.addRow(self.auto_save_check)
        self.settings_widgets["application.auto_save"] = self.auto_save_check

        self.auto_save_interval_spin = QSpinBox()
        self.auto_save_interval_spin.setRange(30, 3600)
        self.auto_save_interval_spin.setSuffix(" seconds")
        app_layout.addRow("Auto-save interval:", self.auto_save_interval_spin)
        self.settings_widgets["application.auto_save_interval"] = self.auto_save_interval_spin

        # Recent files
        self.max_recent_spin = QSpinBox()
        self.max_recent_spin.setRange(0, 20)
        app_layout.addRow("Max recent files:", self.max_recent_spin)
        self.settings_widgets["application.max_recent_files"] = self.max_recent_spin

        layout.addWidget(app_group)

        # Directory settings
        dirs_group = QGroupBox("Default Directories")
        dirs_layout = QFormLayout(dirs_group)

        # Default output directory
        output_layout = QHBoxLayout()
        self.output_dir_edit = QLineEdit()
        output_layout.addWidget(self.output_dir_edit)

        self.output_dir_browse = QPushButton("Browse...")
        self.output_dir_browse.clicked.connect(
            lambda: self._browse_directory(self.output_dir_edit, "Select Default Output Directory")
        )
        output_layout.addWidget(self.output_dir_browse)

        dirs_layout.addRow("Default output:", output_layout)
        self.settings_widgets["export.default_output_directory"] = self.output_dir_edit

        # Watch directory
        watch_layout = QHBoxLayout()
        self.watch_dir_edit = QLineEdit()
        watch_layout.addWidget(self.watch_dir_edit)

        self.watch_dir_browse = QPushButton("Browse...")
        self.watch_dir_browse.clicked.connect(
            lambda: self._browse_directory(self.watch_dir_edit, "Select Watch Directory")
        )
        watch_layout.addWidget(self.watch_dir_browse)

        dirs_layout.addRow("Watch directory:", watch_layout)
        self.settings_widgets["monitoring.watch_directory"] = self.watch_dir_edit

        layout.addWidget(dirs_group)

        layout.addStretch()
        self.tab_widget.addTab(widget, "General")
        return widget

    def _create_scanning_tab(self) -> QWidget:
        """Create scanning/monitoring settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # File monitoring
        monitor_group = QGroupBox("File Monitoring")
        monitor_layout = QFormLayout(monitor_group)

        self.auto_monitor_check = QCheckBox("Start monitoring automatically")
        monitor_layout.addRow(self.auto_monitor_check)
        self.settings_widgets["monitoring.auto_start_monitoring"] = self.auto_monitor_check

        self.detection_delay_spin = QDoubleSpinBox()
        self.detection_delay_spin.setRange(0.5, 30.0)
        self.detection_delay_spin.setSingleStep(0.5)
        self.detection_delay_spin.setSuffix(" seconds")
        monitor_layout.addRow("File detection delay:", self.detection_delay_spin)
        self.settings_widgets["monitoring.file_detection_delay"] = self.detection_delay_spin

        self.ignore_hidden_check = QCheckBox("Ignore hidden files")
        monitor_layout.addRow(self.ignore_hidden_check)
        self.settings_widgets["monitoring.ignore_hidden_files"] = self.ignore_hidden_check

        layout.addWidget(monitor_group)

        # Batch processing
        batch_group = QGroupBox("Batch Processing")
        batch_layout = QFormLayout(batch_group)

        self.max_batch_size_spin = QSpinBox()
        self.max_batch_size_spin.setRange(1, 1000)
        batch_layout.addRow("Max batch size:", self.max_batch_size_spin)
        self.settings_widgets["processing.max_batch_size"] = self.max_batch_size_spin

        self.scan_timeout_spin = QSpinBox()
        self.scan_timeout_spin.setRange(5, 300)
        self.scan_timeout_spin.setSuffix(" seconds")
        batch_layout.addRow("Scan timeout:", self.scan_timeout_spin)
        self.settings_widgets["processing.scan_timeout_seconds"] = self.scan_timeout_spin

        self.parallel_processing_check = QCheckBox("Enable parallel processing")
        batch_layout.addRow(self.parallel_processing_check)
        self.settings_widgets["processing.parallel_processing"] = self.parallel_processing_check

        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, 16)
        batch_layout.addRow("Max worker threads:", self.max_workers_spin)
        self.settings_widgets["processing.max_worker_threads"] = self.max_workers_spin

        layout.addWidget(batch_group)

        # Thumbnail settings
        thumb_group = QGroupBox("Thumbnails")
        thumb_layout = QFormLayout(thumb_group)

        self.thumb_size_combo = QComboBox()
        for size in ThumbnailSize:
            self.thumb_size_combo.addItem(f"{size.width}x{size.height}", size.width)
        thumb_layout.addRow("Thumbnail size:", self.thumb_size_combo)
        self.settings_widgets["ui.default_thumbnail_size"] = self.thumb_size_combo

        self.cache_thumbs_check = QCheckBox("Cache thumbnails")
        thumb_layout.addRow(self.cache_thumbs_check)
        self.settings_widgets["thumbnails.cache_thumbnails"] = self.cache_thumbs_check

        self.thumb_quality_combo = QComboBox()
        self.thumb_quality_combo.addItems(["Low", "Medium", "High"])
        thumb_layout.addRow("Thumbnail quality:", self.thumb_quality_combo)
        self.settings_widgets["thumbnails.thumbnail_quality"] = self.thumb_quality_combo

        layout.addWidget(thumb_group)

        layout.addStretch()
        self.tab_widget.addTab(widget, "Scanning")
        return widget

    def _create_export_tab(self) -> QWidget:
        """Create export settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Default export settings
        export_group = QGroupBox("Default Export Settings")
        export_layout = QFormLayout(export_group)

        # PDF quality
        self.pdf_quality_combo = QComboBox()
        for quality in PDFQuality:
            self.pdf_quality_combo.addItem(quality.get_display_name(), quality.value)
        export_layout.addRow("PDF quality:", self.pdf_quality_combo)
        self.settings_widgets["export.default_quality"] = self.pdf_quality_combo

        # Conflict resolution
        self.conflict_resolution_combo = QComboBox()
        for resolution in ConflictResolution:
            self.conflict_resolution_combo.addItem(resolution.get_display_name(), resolution.value)
        export_layout.addRow("Conflict resolution:", self.conflict_resolution_combo)
        self.settings_widgets["export.conflict_resolution"] = self.conflict_resolution_combo

        # Export options
        self.create_index_check = QCheckBox("Create index file by default")
        export_layout.addRow(self.create_index_check)
        self.settings_widgets["export.create_index_by_default"] = self.create_index_check

        self.preserve_timestamps_check = QCheckBox("Preserve timestamps")
        export_layout.addRow(self.preserve_timestamps_check)
        self.settings_widgets["export.preserve_timestamps"] = self.preserve_timestamps_check

        self.compress_output_check = QCheckBox("Compress output")
        export_layout.addRow(self.compress_output_check)
        self.settings_widgets["export.compress_output"] = self.compress_output_check

        layout.addWidget(export_group)

        # Validation settings
        validation_group = QGroupBox("Validation Settings")
        validation_layout = QFormLayout(validation_group)

        self.strict_validation_check = QCheckBox("Strict validation")
        validation_layout.addRow(self.strict_validation_check)
        self.settings_widgets["validation.strict_validation"] = self.strict_validation_check

        self.warn_conflicts_check = QCheckBox("Warn on conflicts")
        validation_layout.addRow(self.warn_conflicts_check)
        self.settings_widgets["validation.warn_on_conflicts"] = self.warn_conflicts_check

        self.auto_fix_paths_check = QCheckBox("Auto-fix paths")
        validation_layout.addRow(self.auto_fix_paths_check)
        self.settings_widgets["validation.auto_fix_paths"] = self.auto_fix_paths_check

        layout.addWidget(validation_group)

        layout.addStretch()
        self.tab_widget.addTab(widget, "Export")
        return widget

    def _create_appearance_tab(self) -> QWidget:
        """Create appearance settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Theme settings
        theme_group = QGroupBox("Theme Settings")
        theme_layout = QFormLayout(theme_group)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Default", "Dark", "Light"])
        theme_layout.addRow("Theme:", self.theme_combo)
        self.settings_widgets["application.theme"] = self.theme_combo

        layout.addWidget(theme_group)

        # UI settings
        ui_group = QGroupBox("User Interface")
        ui_layout = QFormLayout(ui_group)

        self.show_page_numbers_check = QCheckBox("Show page numbers")
        ui_layout.addRow(self.show_page_numbers_check)
        self.settings_widgets["ui.show_page_numbers"] = self.show_page_numbers_check

        self.show_assignment_indicators_check = QCheckBox("Show assignment indicators")
        ui_layout.addRow(self.show_assignment_indicators_check)
        self.settings_widgets["ui.show_assignment_indicators"] = self.show_assignment_indicators_check

        self.max_thumbs_per_row_spin = QSpinBox()
        self.max_thumbs_per_row_spin.setRange(1, 20)
        ui_layout.addRow("Max thumbnails per row:", self.max_thumbs_per_row_spin)
        self.settings_widgets["ui.max_thumbnails_per_row"] = self.max_thumbs_per_row_spin

        # Font settings
        font_layout = QHBoxLayout()
        self.font_label = QLabel("Default application font")
        font_layout.addWidget(self.font_label)

        self.font_button = QPushButton("Change Font...")
        self.font_button.clicked.connect(self._change_font)
        font_layout.addWidget(self.font_button)

        ui_layout.addRow("Font:", font_layout)

        layout.addWidget(ui_group)

        # Window settings
        window_group = QGroupBox("Window Settings")
        window_layout = QFormLayout(window_group)

        self.remember_layout_check = QCheckBox("Remember window layout")
        window_layout.addRow(self.remember_layout_check)
        self.settings_widgets["window.remember_layout"] = self.remember_layout_check

        self.window_title_edit = QLineEdit()
        window_layout.addRow("Window title template:", self.window_title_edit)
        self.settings_widgets["ui.window_title_template"] = self.window_title_edit

        layout.addWidget(window_group)

        layout.addStretch()
        self.tab_widget.addTab(widget, "Appearance")
        return widget

    def _create_advanced_tab(self) -> QWidget:
        """Create advanced settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Cache settings
        cache_group = QGroupBox("Cache Settings")
        cache_layout = QFormLayout(cache_group)

        self.cache_size_spin = QSpinBox()
        self.cache_size_spin.setRange(50, 5000)
        self.cache_size_spin.setSuffix(" MB")
        cache_layout.addRow("Max cache size:", self.cache_size_spin)
        self.settings_widgets["cache.max_size_mb"] = self.cache_size_spin

        self.cleanup_on_startup_check = QCheckBox("Cleanup cache on startup")
        cache_layout.addRow(self.cleanup_on_startup_check)
        self.settings_widgets["cache.cleanup_on_startup"] = self.cleanup_on_startup_check

        self.max_age_spin = QSpinBox()
        self.max_age_spin.setRange(1, 365)
        self.max_age_spin.setSuffix(" days")
        cache_layout.addRow("Max cache age:", self.max_age_spin)
        self.settings_widgets["cache.max_age_days"] = self.max_age_spin

        # Clear cache button
        clear_cache_button = QPushButton("Clear Cache Now")
        clear_cache_button.clicked.connect(self._clear_cache)
        cache_layout.addRow(clear_cache_button)

        layout.addWidget(cache_group)

        # Logging settings
        logging_group = QGroupBox("Logging Settings")
        logging_layout = QFormLayout(logging_group)

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        logging_layout.addRow("Log level:", self.log_level_combo)
        self.settings_widgets["logging.level"] = self.log_level_combo

        self.log_to_file_check = QCheckBox("Log to file")
        logging_layout.addRow(self.log_to_file_check)
        self.settings_widgets["logging.log_to_file"] = self.log_to_file_check

        self.max_log_files_spin = QSpinBox()
        self.max_log_files_spin.setRange(1, 50)
        logging_layout.addRow("Max log files:", self.max_log_files_spin)
        self.settings_widgets["logging.max_log_files"] = self.max_log_files_spin

        self.max_log_size_spin = QSpinBox()
        self.max_log_size_spin.setRange(1, 100)
        self.max_log_size_spin.setSuffix(" MB")
        logging_layout.addRow("Max log file size:", self.max_log_size_spin)
        self.settings_widgets["logging.max_log_size_mb"] = self.max_log_size_spin

        layout.addWidget(logging_group)

        # Debug settings
        debug_group = QGroupBox("Debug Settings")
        debug_layout = QVBoxLayout(debug_group)

        # Reset settings button
        reset_button = QPushButton("Reset All Settings to Defaults")
        reset_button.clicked.connect(self._confirm_reset_all)
        debug_layout.addWidget(reset_button)

        # Export settings button
        export_button = QPushButton("Export Settings...")
        export_button.clicked.connect(self._export_settings)
        debug_layout.addWidget(export_button)

        # Import settings button
        import_button = QPushButton("Import Settings...")
        import_button.clicked.connect(self._import_settings)
        debug_layout.addWidget(import_button)

        layout.addWidget(debug_group)

        layout.addStretch()
        self.tab_widget.addTab(widget, "Advanced")
        return widget

    def _connect_signals(self):
        """Connect UI signals to track changes."""
        for widget in self.settings_widgets.values():
            if isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self._mark_changed)
            elif isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._mark_changed)
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                widget.valueChanged.connect(self._mark_changed)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._mark_changed)

    def _load_current_settings(self):
        """Load current settings into UI widgets."""
        for setting_key, widget in self.settings_widgets.items():
            try:
                value = self.config_manager.get_setting(setting_key)
                if value is not None:
                    self._set_widget_value(widget, value)
            except Exception as e:
                logging.warning(f"Could not load setting {setting_key}: {e}")

    def _set_widget_value(self, widget, value):
        """Set widget value based on widget type."""
        if isinstance(widget, QComboBox):
            # Try to find by data first, then by text
            index = widget.findData(value)
            if index == -1:
                index = widget.findText(str(value))
            if index != -1:
                widget.setCurrentIndex(index)
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.setValue(value)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))

    def _get_widget_value(self, widget):
        """Get value from widget based on widget type."""
        if isinstance(widget, QComboBox):
            data = widget.currentData()
            return data if data is not None else widget.currentText()
        elif isinstance(widget, QLineEdit):
            return widget.text()
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            return widget.value()
        elif isinstance(widget, QCheckBox):
            return widget.isChecked()
        return None

    def _mark_changed(self):
        """Mark that settings have been changed."""
        self.has_changes = True
        self.apply_button.setEnabled(True)

    def _browse_directory(self, line_edit: QLineEdit, title: str):
        """Browse for a directory and set it in the line edit."""
        current_dir = line_edit.text() or str(Path.home())
        directory = QFileDialog.getExistingDirectory(self, title, current_dir)
        if directory:
            line_edit.setText(directory)

    def _change_font(self):
        """Open font selection dialog."""
        current_font = self.font()
        font, ok = QFontDialog.getFont(current_font, self)
        if ok:
            self.font_label.setText(f"{font.family()}, {font.pointSize()}pt")
            self._mark_changed()

    def _clear_cache(self):
        """Clear application cache."""
        try:
            app_signals.cache_cleared.emit("all")
            self.parent().statusBar().showMessage("Cache cleared successfully", 3000)
        except Exception as e:
            logging.error(f"Failed to clear cache: {e}")

    def _export_settings(self):
        """Export settings to file."""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Settings",
            str(Path.home() / "scanner_extension_settings.json"),
            "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            try:
                self.config_manager.backup_configuration(Path(filename))
                self.parent().statusBar().showMessage("Settings exported successfully", 3000)
            except Exception as e:
                logging.error(f"Failed to export settings: {e}")

    def _import_settings(self):
        """Import settings from file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", str(Path.home()),
            "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            try:
                self.config_manager.restore_configuration(Path(filename))
                self._load_current_settings()
                self.parent().statusBar().showMessage("Settings imported successfully", 3000)
            except Exception as e:
                logging.error(f"Failed to import settings: {e}")

    def _confirm_reset_all(self):
        """Confirm reset all settings to defaults."""
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self, "Reset Settings",
            "Are you sure you want to reset all settings to their default values?\n\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._restore_defaults()

    def _restore_defaults(self):
        """Restore all settings to defaults."""
        try:
            self.config_manager.reset_to_defaults()
            self._load_current_settings()
            self.has_changes = True
            self.apply_button.setEnabled(True)
            self.settings_reset.emit()

        except Exception as e:
            logging.error(f"Failed to restore defaults: {e}")

    def _collect_settings(self) -> Dict[str, Any]:
        """Collect all settings from UI widgets."""
        settings = {}
        for setting_key, widget in self.settings_widgets.items():
            try:
                value = self._get_widget_value(widget)
                if value is not None:
                    settings[setting_key] = value
            except Exception as e:
                logging.warning(f"Could not collect setting {setting_key}: {e}")
        return settings

    def _validate_settings(self) -> List[str]:
        """Validate settings and return any errors."""
        errors = []

        # Validate directories exist
        output_dir = self.output_dir_edit.text()
        if output_dir and not Path(output_dir).parent.exists():
            errors.append("Default output directory parent does not exist")

        watch_dir = self.watch_dir_edit.text()
        if watch_dir and not Path(watch_dir).exists():
            errors.append("Watch directory does not exist")

        # Validate numeric ranges
        if self.auto_save_interval_spin.value() < 30:
            errors.append("Auto-save interval must be at least 30 seconds")

        if self.cache_size_spin.value() < 50:
            errors.append("Cache size must be at least 50 MB")

        return errors

    def _apply_settings(self):
        """Apply settings to configuration manager."""
        # Validate settings
        errors = self._validate_settings()
        if errors:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Invalid Settings",
                                "Please fix the following issues:\n\n" + "\n".join(errors))
            return

        # Collect and save settings
        settings = self._collect_settings()

        try:
            for key, value in settings.items():
                self.config_manager.set_setting(key, value)

            self.config_manager.save_application_config()
            self.settings_applied.emit(settings)

            self.has_changes = False
            self.apply_button.setEnabled(False)

            if self.parent():
                self.parent().statusBar().showMessage("Settings applied successfully", 3000)

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Settings Error", f"Failed to apply settings:\n{e}")
            logging.error(f"Failed to apply settings: {e}")

    def _ok_clicked(self):
        """Handle OK button click."""
        if self.has_changes:
            self._apply_settings()
        self.accept()

    def reject(self):
        """Handle dialog rejection."""
        if self.has_changes:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to discard them?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.No:
                return

        super().reject()

    def get_modified_settings(self) -> Dict[str, Any]:
        """Get dictionary of modified settings."""
        return self.modified_settings.copy()

