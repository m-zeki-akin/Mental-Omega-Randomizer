"""Where skirmish runs live.

One file holding a list of runs, signed as a whole and written atomically.
There is no second document to stay consistent with -- no profile, no meta
progression, nothing a run leaves behind for the next one -- so the
write-ahead journal the Shop mode needs has nothing to protect here, and the
atomic write is the whole durability story.

A modified file is loaded and played, not refused: the signature is a
doorstep, and a player whose disk went bad must not lose their runs to it.
"""

from dataclasses import dataclass
from pathlib import Path
import logging
import shutil
import threading

from randomizer.core.diagnostics import event as log_event
from randomizer.core.integrity import MODIFIED, sign, verify
from randomizer.core.paths import BACKUP_DIR, SKIRMISH_RUNS_PATH
from randomizer.core.storage import atomic_write_opaque, read_opaque_object

from .model import SkirmishRunCollection
from .state import normalize_skirmish_run, normalize_skirmish_run_collection


class SkirmishPersistenceError(RuntimeError):
    """Raised when stored skirmish runs cannot be read safely."""


@dataclass(frozen=True)
class SkirmishPersistencePaths:
    runs: Path
    backup_dir: Path


DEFAULT_SKIRMISH_PATHS = SkirmishPersistencePaths(
    runs=SKIRMISH_RUNS_PATH,
    backup_dir=BACKUP_DIR / 'skirmish',
)


class SkirmishRepository:
    def __init__(self, paths=DEFAULT_SKIRMISH_PATHS):
        self.paths = paths
        self._lock = threading.RLock()
        self.integrity_modified = False

    def _read_collection(self):
        if not self.paths.runs.is_file():
            return SkirmishRunCollection()
        try:
            raw = read_opaque_object(self.paths.runs)
            if verify(raw) is MODIFIED:
                self.integrity_modified = True
                log_event(
                    'skirmish_state_signature_failed',
                    level=logging.WARNING,
                )
            collection = normalize_skirmish_run_collection(raw)
        except Exception as exc:
            self._raise_invalid(exc)
        normalized = collection.to_dict()
        if raw != sign(normalized):
            self._write(collection)
        return collection

    def _write(self, collection):
        if not collection.runs:
            self.paths.runs.unlink(missing_ok=True)
            return
        atomic_write_opaque(self.paths.runs, sign(collection.to_dict()))

    def _raise_invalid(self, error):
        backup = None
        try:
            if self.paths.runs.is_file():
                self.paths.backup_dir.mkdir(parents=True, exist_ok=True)
                backup = self.paths.backup_dir / (
                    f'{self.paths.runs.name}.invalid-backup'
                )
                suffix = 2
                while backup.exists():
                    backup = self.paths.backup_dir / (
                        f'{self.paths.runs.name}.invalid-backup.{suffix}'
                    )
                    suffix += 1
                shutil.copy2(self.paths.runs, backup)
        except OSError as backup_error:
            raise SkirmishPersistenceError(
                f'Cannot load Skirmish runs {self.paths.runs}: {error}. '
                f'Backup also failed: {backup_error}'
            ) from error
        preserved = f' Backup preserved at {backup}.' if backup else ''
        raise SkirmishPersistenceError(
            f'Cannot load Skirmish runs {self.paths.runs}: {error}.{preserved}'
        ) from error

    def load_run(self):
        """Return the run being played, or ``None`` between runs."""
        with self._lock:
            return self._read_collection().active()

    def list_runs(self):
        with self._lock:
            collection = self._read_collection()
            return collection.runs, collection.active_run_id

    def save_run(self, run, *, activate=True):
        """Store one run, leaving every other run exactly as it was."""
        with self._lock:
            normalized = normalize_skirmish_run(run.to_dict())
            self._write(
                self._read_collection().with_run(
                    normalized, activate=activate
                )
            )
            return normalized

    def select_run(self, run_id):
        with self._lock:
            collection = self._read_collection()
            try:
                selected = collection.selecting(run_id)
            except KeyError:
                raise SkirmishPersistenceError(
                    f'No stored Skirmish run {run_id!r}'
                ) from None
            self._write(selected)
            return selected.active()

    def delete_run(self, run_id):
        with self._lock:
            collection = self._read_collection()
            if collection.run(run_id) is None:
                raise SkirmishPersistenceError(
                    f'No stored Skirmish run {run_id!r}'
                )
            self._write(collection.without_run(run_id))
