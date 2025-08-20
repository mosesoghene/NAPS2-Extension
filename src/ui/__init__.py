"""
UI package for Scanner Extension.

Contains all user interface components including the main window,
panels, widgets, and dialogs.
"""

from .main_window import MainWindow
from .index_panel import IndexPanel

__all__ = [
    'MainWindow',
    'IndexPanel',
]