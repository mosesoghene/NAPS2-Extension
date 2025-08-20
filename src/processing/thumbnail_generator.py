"""
Thumbnail generation and caching system.

Manages thumbnail creation, caching, and cleanup for PDF pages
with proper threading and cache management.
"""

import logging
import time
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Set
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timedelta
import hashlib
import shutil

from PySide6.QtCore import QObject, QThread, QMutex, QMutexLocker, Signal
from PySide6.QtGui import QPixmap

from ..core.exceptions import PDFProcessingError, CacheError
from ..core.signals import app_signals
from ..models.enums import ThumbnailSize
from .pdf_utils import PDFProcessor


class ThumbnailGenerationTask:
    """Represents a single thumbnail generation task."""

    def __init__(self, file_id: str, file_path: Path, page_number: int,
                 size: ThumbnailSize, priority: int = 0):
        self.file_id = file_id
        self.file_path = file_path
        self.page_number = page_number
        self.size = size
        self.priority = priority
        self.created_at = datetime.now()
        self.attempts = 0
        self.max_attempts = 3

    @property
    def task_id(self) -> str:
        """Get unique task identifier."""
        return f"{self.file_id}_{self.page_number}_{self.size.name}"

    def __lt__(self, other):
        """Compare tasks for priority queue ordering."""
        return self.priority > other.priority  # Higher priority first


class ThumbnailCache:
    """Manages thumbnail caching with size limits and cleanup."""

    def __init__(self, cache_directory: Path, max_size_mb: int = 100):
        self.cache_directory = Path(cache_directory)
        self.max_size_mb = max_size_mb
        self.max_size_bytes = max_size_mb * 1024 * 1024

        # Cache tracking
        self._cache_index: Dict[str, Dict] = {}  # cache_key -> metadata
        self._access_times: Dict[str, datetime] = {}
        self._cache_lock = QMutex()

        # Ensure cache directory exists
        self.cache_directory.mkdir(parents=True, exist_ok=True)

        # Load existing cache index
        self._load_cache_index()

        logging.debug(f"ThumbnailCache initialized: {cache_directory} ({max_size_mb}MB)")

    def get_thumbnail_path(self, file_id: str, page_number: int, size: ThumbnailSize) -> Optional[Path]:
        """Get path to cached thumbnail if it exists."""
        cache_key = self._get_cache_key(file_id, page_number, size)

        with QMutexLocker(self._cache_lock):
            if cache_key in self._cache_index:
                thumbnail_path = self.cache_directory / self._cache_index[cache_key]['filename']

                if thumbnail_path.exists():
                    # Update access time
                    self._access_times[cache_key] = datetime.now()
                    return thumbnail_path
                else:
                    # Remove invalid cache entry
                    self._remove_cache_entry(cache_key)

        return None

    def add_thumbnail(self, file_id: str, page_number: int, size: ThumbnailSize,
                      thumbnail_path: Path) -> Optional[Path]:
        """Add thumbnail to cache."""
        if not thumbnail_path.exists():
            return None

        cache_key = self._get_cache_key(file_id, page_number, size)
        filename = f"{cache_key}.png"
        cached_path = self.cache_directory / filename

        try:
            # Copy thumbnail to cache
            shutil.copy2(thumbnail_path, cached_path)
            file_size = cached_path.stat().st_size

            with QMutexLocker(self._cache_lock):
                # Add to cache index
                self._cache_index[cache_key] = {
                    'filename': filename,
                    'file_id': file_id,
                    'page_number': page_number,
                    'size': size.name,
                    'file_size': file_size,
                    'created_at': datetime.now().isoformat()
                }
                self._access_times[cache_key] = datetime.now()

            # Check cache size limits
            self._cleanup_if_needed()

            logging.debug(f"Added thumbnail to cache: {cache_key}")
            return cached_path

        except Exception as e:
            logging.error(f"Failed to add thumbnail to cache: {e}")
            return None

    def remove_thumbnails_for_file(self, file_id: str) -> int:
        """Remove all thumbnails for a specific file."""
        removed_count = 0

        with QMutexLocker(self._cache_lock):
            keys_to_remove = [
                key for key, metadata in self._cache_index.items()
                if metadata['file_id'] == file_id
            ]

            for key in keys_to_remove:
                if self._remove_cache_entry(key):
                    removed_count += 1

        logging.debug(f"Removed {removed_count} thumbnails for file {file_id}")
        return removed_count

    def cleanup_old_thumbnails(self, max_age_days: int = 30) -> int:
        """Remove thumbnails older than specified age."""
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        removed_count = 0

        with QMutexLocker(self._cache_lock):
            keys_to_remove = []

            for key, metadata in self._cache_index.items():
                created_at = datetime.fromisoformat(metadata['created_at'])
                if created_at < cutoff_date:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                if self._remove_cache_entry(key):
                    removed_count += 1

        logging.info(f"Cleaned up {removed_count} old thumbnails")
        return removed_count

    def get_cache_stats(self) -> Dict[str, any]:
        """Get cache statistics."""
        with QMutexLocker(self._cache_lock):
            total_size = sum(meta['file_size'] for meta in self._cache_index.values())

            return {
                'total_thumbnails': len(self._cache_index),
                'total_size_bytes': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'max_size_mb': self.max_size_mb,
                'utilization_percent': (total_size / self.max_size_bytes) * 100 if self.max_size_bytes > 0 else 0,
                'cache_directory': str(self.cache_directory)
            }

    def clear_cache(self) -> int:
        """Clear all cached thumbnails."""
        removed_count = 0

        with QMutexLocker(self._cache_lock):
            keys_to_remove = list(self._cache_index.keys())

            for key in keys_to_remove:
                if self._remove_cache_entry(key):
                    removed_count += 1

        logging.info(f"Cleared thumbnail cache: {removed_count} thumbnails removed")
        return removed_count

    def _get_cache_key(self, file_id: str, page_number: int, size: ThumbnailSize) -> str:
        """Generate cache key for thumbnail."""
        return f"{file_id}_{page_number}_{size.width}x{size.height}"

    def _load_cache_index(self):
        """Load existing cache index from disk."""
        try:
            # Scan cache directory for existing thumbnails
            for thumbnail_file in self.cache_directory.glob("*.png"):
                try:
                    parts = thumbnail_file.stem.split('_')
                    if len(parts) >= 3:
                        file_id = '_'.join(parts[:-2])
                        page_number = int(parts[-2])
                        size_parts = parts[-1].split('x')

                        if len(size_parts) == 2:
                            width, height = int(size_parts[0]), int(size_parts[1])
                            size = self._find_thumbnail_size(width, height)

                            if size:
                                cache_key = self._get_cache_key(file_id, page_number, size)
                                file_stat = thumbnail_file.stat()

                                self._cache_index[cache_key] = {
                                    'filename': thumbnail_file.name,
                                    'file_id': file_id,
                                    'page_number': page_number,
                                    'size': size.name,
                                    'file_size': file_stat.st_size,
                                    'created_at': datetime.fromtimestamp(file_stat.st_ctime).isoformat()
                                }
                                self._access_times[cache_key] = datetime.fromtimestamp(file_stat.st_atime)

                except Exception as e:
                    logging.debug(f"Could not index thumbnail {thumbnail_file.name}: {e}")

            logging.debug(f"Loaded {len(self._cache_index)} thumbnails from cache")

        except Exception as e:
            logging.error(f"Error loading cache index: {e}")

    def _find_thumbnail_size(self, width: int, height: int) -> Optional[ThumbnailSize]:
        """Find ThumbnailSize enum matching dimensions."""
        for size in ThumbnailSize:
            if size.width == width and size.height == height:
                return size
        return None

    def _remove_cache_entry(self, cache_key: str) -> bool:
        """Remove cache entry and file."""
        try:
            if cache_key in self._cache_index:
                filename = self._cache_index[cache_key]['filename']
                file_path = self.cache_directory / filename

                if file_path.exists():
                    file_path.unlink()

                del self._cache_index[cache_key]
                self._access_times.pop(cache_key, None)

                return True
        except Exception as e:
            logging.error(f"Error removing cache entry {cache_key}: {e}")

        return False

    def _cleanup_if_needed(self):
        """Clean up cache if size limits are exceeded."""
        try:
            total_size = sum(meta['file_size'] for meta in self._cache_index.values())

            if total_size > self.max_size_bytes:
                # Remove least recently used thumbnails
                sorted_keys = sorted(
                    self._access_times.keys(),
                    key=lambda k: self._access_times[k]
                )

                target_size = int(self.max_size_bytes * 0.8)  # Clean to 80% of limit

                for key in sorted_keys:
                    if total_size <= target_size:
                        break

                    if key in self._cache_index:
                        file_size = self._cache_index[key]['file_size']
                        if self._remove_cache_entry(key):
                            total_size -= file_size

        except Exception as e:
            logging.error(f"Error during cache cleanup: {e}")


class ThumbnailGenerator(QObject):
    """Manages thumbnail generation with threading and caching."""

    # Signals
    thumbnail_generated = Signal(str, int, object)  # file_id, page_number, thumbnail_path
    generation_progress = Signal(int, int)  # current, total
    generation_error = Signal(str, str)  # file_id, error_message
    batch_completed = Signal(int, int)  # successful, failed

    def __init__(self, cache_directory: Path, max_workers: int = 4):
        super().__init__()

        self.cache_directory = Path(cache_directory)
        self.max_workers = max_workers

        # Initialize components
        self.pdf_processor = PDFProcessor()
        self.thumbnail_cache = ThumbnailCache(cache_directory / "thumbnails")

        # Thread pool for thumbnail generation
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)

        # Task tracking
        self.pending_tasks: Dict[str, ThumbnailGenerationTask] = {}
        self.active_futures: Dict[str, Future] = {}
        self.generation_stats = {'successful': 0, 'failed': 0}

        # Thread safety
        self.tasks_lock = QMutex()

        logging.debug(f"ThumbnailGenerator initialized with {max_workers} workers")

    def generate_thumbnail(self, file_id: str, file_path: Path, page_number: int,
                           size: ThumbnailSize = ThumbnailSize.MEDIUM,
                           priority: int = 0) -> bool:
        """
        Request thumbnail generation for a specific page.

        Args:
            file_id: Unique identifier for the file
            file_path: Path to the PDF file
            page_number: Page number (1-based)
            size: Thumbnail size
            priority: Generation priority (higher = more priority)

        Returns:
            bool: True if task was queued, False if already exists
        """
        try:
            # Check if thumbnail already exists in cache
            cached_path = self.thumbnail_cache.get_thumbnail_path(file_id, page_number, size)
            if cached_path:
                self.thumbnail_generated.emit(file_id, page_number, cached_path)
                return True

            # Create generation task
            task = ThumbnailGenerationTask(file_id, file_path, page_number, size, priority)

            with QMutexLocker(self.tasks_lock):
                # Check if task already pending
                if task.task_id in self.pending_tasks or task.task_id in self.active_futures:
                    return False

                # Add to pending tasks
                self.pending_tasks[task.task_id] = task

            # Submit to thread pool
            future = self.thread_pool.submit(self._generate_thumbnail_task, task)

            with QMutexLocker(self.tasks_lock):
                self.active_futures[task.task_id] = future
                del self.pending_tasks[task.task_id]

            logging.debug(f"Queued thumbnail generation: {task.task_id}")
            return True

        except Exception as e:
            logging.error(f"Error queuing thumbnail generation: {e}")
            return False

    def generate_thumbnails_for_file(self, file_id: str, file_path: Path,
                                     page_count: int, size: ThumbnailSize = ThumbnailSize.MEDIUM) -> int:
        """
        Generate thumbnails for all pages in a file.

        Args:
            file_id: Unique identifier for the file
            file_path: Path to the PDF file
            page_count: Number of pages in the file
            size: Thumbnail size

        Returns:
            int: Number of tasks queued
        """
        queued_count = 0

        for page_number in range(1, page_count + 1):
            if self.generate_thumbnail(file_id, file_path, page_number, size):
                queued_count += 1

        logging.info(f"Queued {queued_count} thumbnail generation tasks for {file_id}")
        return queued_count

    def _generate_thumbnail_task(self, task: ThumbnailGenerationTask) -> bool:
        """Execute thumbnail generation task."""
        try:
            logging.debug(f"Generating thumbnail: {task.task_id}")

            # Generate thumbnail using PDF processor
            thumbnail_path = self.pdf_processor.generate_page_thumbnail(
                task.file_path,
                task.page_number,
                task.size.size_tuple
            )

            if thumbnail_path and thumbnail_path.exists():
                # Add to cache
                cached_path = self.thumbnail_cache.add_thumbnail(
                    task.file_id,
                    task.page_number,
                    task.size,
                    thumbnail_path
                )

                if cached_path:
                    # Emit success signal
                    self.thumbnail_generated.emit(task.file_id, task.page_number, cached_path)
                    app_signals.thumbnail_generated.emit(task.file_id, task.page_number, cached_path)

                    with QMutexLocker(self.tasks_lock):
                        self.generation_stats['successful'] += 1

                    return True

            # If we get here, generation failed
            with QMutexLocker(self.tasks_lock):
                self.generation_stats['failed'] += 1

            error_msg = f"Failed to generate thumbnail for page {task.page_number}"
            self.generation_error.emit(task.file_id, error_msg)
            logging.warning(f"Thumbnail generation failed: {task.task_id}")

            return False

        except Exception as e:
            error_msg = f"Thumbnail generation error: {e}"
            logging.error(f"Error in thumbnail task {task.task_id}: {e}")

            with QMutexLocker(self.tasks_lock):
                self.generation_stats['failed'] += 1

            self.generation_error.emit(task.file_id, error_msg)
            return False

        finally:
            # Clean up task tracking
            with QMutexLocker(self.tasks_lock):
                self.active_futures.pop(task.task_id, None)

    def cancel_tasks_for_file(self, file_id: str) -> int:
        """Cancel all pending tasks for a specific file."""
        cancelled_count = 0

        with QMutexLocker(self.tasks_lock):
            # Cancel pending tasks
            tasks_to_remove = [
                task_id for task_id, task in self.pending_tasks.items()
                if task.file_id == file_id
            ]

            for task_id in tasks_to_remove:
                del self.pending_tasks[task_id]
                cancelled_count += 1

            # Cancel active futures (they may still complete)
            futures_to_cancel = [
                (task_id, future) for task_id, future in self.active_futures.items()
                if task_id.startswith(file_id)
            ]

            for task_id, future in futures_to_cancel:
                future.cancel()
                cancelled_count += 1

        logging.info(f"Cancelled {cancelled_count} thumbnail tasks for file {file_id}")
        return cancelled_count

    def get_generation_status(self) -> Dict[str, any]:
        """Get current generation status."""
        with QMutexLocker(self.tasks_lock):
            return {
                'pending_tasks': len(self.pending_tasks),
                'active_tasks': len(self.active_futures),
                'successful_generations': self.generation_stats['successful'],
                'failed_generations': self.generation_stats['failed'],
                'cache_stats': self.thumbnail_cache.get_cache_stats()
            }

    def cleanup_thumbnails_for_file(self, file_id: str) -> int:
        """Remove cached thumbnails for a specific file."""
        return self.thumbnail_cache.remove_thumbnails_for_file(file_id)

    def cleanup_old_thumbnails(self, max_age_days: int = 30) -> int:
        """Clean up old thumbnail cache entries."""
        return self.thumbnail_cache.cleanup_old_thumbnails(max_age_days)

    def clear_cache(self) -> int:
        """Clear entire thumbnail cache."""
        return self.thumbnail_cache.clear_cache()

    def shutdown(self):
        """Shutdown thumbnail generator and cleanup resources."""
        try:
            logging.info("Shutting down thumbnail generator...")

            # Cancel all pending tasks
            with QMutexLocker(self.tasks_lock):
                for task_id in list(self.pending_tasks.keys()):
                    del self.pending_tasks[task_id]

                for future in self.active_futures.values():
                    future.cancel()

            # Shutdown thread pool
            self.thread_pool.shutdown(wait=True, timeout=10)

            logging.info("Thumbnail generator shutdown complete")

        except Exception as e:
            logging.error(f"Error during thumbnail generator shutdown: {e}")

    def __del__(self):
        """Destructor - ensure proper cleanup."""
        self.shutdown()

