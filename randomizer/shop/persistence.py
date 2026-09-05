"""Atomic Shop profile/run persistence with write-ahead recovery."""

from dataclasses import dataclass, replace
from pathlib import Path
import logging
import shutil
import threading

from randomizer.core.diagnostics import event as log_event

from randomizer.core.paths import (
    BACKUP_DIR,
    SHOP_PROFILE_PATH,
    SHOP_RUN_PATH,
    SHOP_TRANSACTION_PATH,
)
from randomizer.core.integrity import MODIFIED, SIGNED, sign, verify
from randomizer.core.storage import atomic_write_json, read_json_object

from .state import normalize_shop_profile, normalize_shop_run


SHOP_TRANSACTION_SCHEMA_VERSION = 1


class ShopPersistenceError(RuntimeError):
    """Raised when durable Shop state cannot be read or recovered safely."""


@dataclass(frozen=True)
class ShopPersistencePaths:
    profile: Path
    run: Path
    transaction: Path
    backup_dir: Path


DEFAULT_SHOP_PATHS = ShopPersistencePaths(
    profile=SHOP_PROFILE_PATH,
    run=SHOP_RUN_PATH,
    transaction=SHOP_TRANSACTION_PATH,
    backup_dir=BACKUP_DIR / 'shop',
)


def _next_backup_path(path, backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)
    base = backup_dir / f'{path.name}.invalid-backup'
    candidate = base
    suffix = 2
    while candidate.exists():
        candidate = backup_dir / f'{base.name}.{suffix}'
        suffix += 1
    return candidate


def _backup_invalid(path, backup_dir):
    if not path.is_file():
        return None
    backup = _next_backup_path(path, backup_dir)
    shutil.copy2(path, backup)
    return backup


class ShopRepository:
    """Own Shop files and replay interrupted two-file commits exactly."""

    def __init__(self, paths=DEFAULT_SHOP_PATHS):
        self.paths = paths
        self._lock = threading.RLock()
        # A failed signature on the run or the journal has to reach the
        # profile, which is where the flag lives and where it is signed.
        # Reads are ordered profile-first, so it is remembered here until a
        # profile passes through.
        self._integrity_breach = False

    def _write_signed(self, path, document):
        atomic_write_json(path, sign(document), indent=None)

    def _read_signed(self, path, label):
        """Read one document, noting whether its signature held.

        A bad signature is not a corrupt file and must not take the corruption
        path: that one moves the file aside and raises, which would destroy the
        progress of a player whose disk went bad rather than a cheat. Tamper is
        loaded, played, and flagged.
        """
        document = read_json_object(path)
        if verify(document) is MODIFIED:
            self._integrity_breach = True
            log_event(
                'shop_state_signature_failed',
                level=logging.WARNING,
                label=label,
            )
        return document

    def _flag_integrity(self, profile):
        """Carry a detected breach onto the profile, and make it stick."""
        if not self._integrity_breach or profile.integrity_modified:
            return profile
        flagged = replace(profile, integrity_modified=True)
        self._write_signed(self.paths.profile, flagged.to_dict())
        return flagged

    def _raise_invalid(self, label, path, error):
        try:
            backup = _backup_invalid(path, self.paths.backup_dir)
        except OSError as backup_error:
            raise ShopPersistenceError(
                f'Cannot load {label} {path}: {error}. '
                f'Backup also failed: {backup_error}'
            ) from error
        backup_text = f' Backup preserved at {backup}.' if backup else ''
        raise ShopPersistenceError(
            f'Cannot load {label} {path}: {error}.{backup_text}'
        ) from error

    def _read_profile(self):
        if not self.paths.profile.is_file():
            return normalize_shop_profile()
        try:
            raw = self._read_signed(self.paths.profile, 'profile')
            profile = normalize_shop_profile(raw)
        except Exception as exc:
            self._raise_invalid('Shop profile', self.paths.profile, exc)
        profile = self._flag_integrity(profile)
        normalized = profile.to_dict()
        # Re-signed rather than rewritten as-is: this rewrite is also what
        # gives a profile written before signing existed its first signature.
        if raw != sign(normalized):
            self._write_signed(self.paths.profile, normalized)
        return profile

    def _read_run(self):
        if not self.paths.run.is_file():
            return None
        try:
            raw = self._read_signed(self.paths.run, 'run')
            run = normalize_shop_run(raw)
        except Exception as exc:
            self._raise_invalid('Shop run', self.paths.run, exc)
        normalized = run.to_dict()
        if raw != sign(normalized):
            self._write_signed(self.paths.run, normalized)
        return run

    def load_profile(self):
        with self._lock:
            self.recover_pending_transaction()
            return self._read_profile()

    def load_run(self):
        with self._lock:
            self.recover_pending_transaction()
            return self._read_run()

    def load(self):
        with self._lock:
            self.recover_pending_transaction()
            profile = self._read_profile()
            run = self._read_run()
            # The run is read second, so a breach found in it lands on the
            # profile here rather than one load later.
            return self._flag_integrity(profile), run

    def save_profile(self, profile):
        with self._lock:
            self.recover_pending_transaction()
            normalized = normalize_shop_profile(profile.to_dict())
            self._write_signed(self.paths.profile, normalized.to_dict())

    def save_run(self, run):
        with self._lock:
            self.recover_pending_transaction()
            normalized = normalize_shop_run(run.to_dict())
            self._write_signed(self.paths.run, normalized.to_dict())

    def prepare_commit(self, profile, run, transaction_id):
        """Durably record exact targets before either state file changes."""
        with self._lock:
            self.recover_pending_transaction()
            transaction_id = str(transaction_id or '')
            if not transaction_id:
                raise ValueError('Shop transaction_id must be non-empty')
            normalized_profile = normalize_shop_profile(profile.to_dict())
            normalized_run = (
                None if run is None else normalize_shop_run(run.to_dict())
            )
            document = {
                'schema_version': SHOP_TRANSACTION_SCHEMA_VERSION,
                'transaction_id': transaction_id,
                'profile': normalized_profile.to_dict(),
                'run': (
                    None if normalized_run is None else normalized_run.to_dict()
                ),
            }
            self._write_signed(self.paths.transaction, document)

    def recover_pending_transaction(self):
        """Replay one journal until both exact target documents are durable."""
        with self._lock:
            if not self.paths.transaction.is_file():
                return False
            # The journal is the one document that is not grandfathered.
            # It writes straight into the profile, so accepting an unsigned
            # one because older versions wrote unsigned ones would hand a
            # forger the exact bypass the signatures exist to close. A
            # journal that is not correctly signed is discarded rather than
            # replayed: it is written before either state file changes, so
            # both are still consistent at their pre-commit values, and the
            # cost is one interrupted transaction.
            journal_state = verify(read_json_object(self.paths.transaction))
            if journal_state is not SIGNED:
                if journal_state is MODIFIED:
                    self._integrity_breach = True
                log_event(
                    'shop_transaction_discarded',
                    level=logging.WARNING,
                    signature=journal_state,
                )
                self.paths.transaction.unlink(missing_ok=True)
                return False
            try:
                document = read_json_object(self.paths.transaction)
                if document.get('schema_version') != SHOP_TRANSACTION_SCHEMA_VERSION:
                    raise ValueError(
                        'Unsupported Shop transaction schema_version '
                        f'{document.get("schema_version")!r}'
                    )
                if not isinstance(document.get('transaction_id'), str) or not document[
                    'transaction_id'
                ]:
                    raise ValueError('Shop transaction_id must be non-empty')
                if 'run' not in document:
                    raise ValueError('Shop transaction has no run target')
                profile = normalize_shop_profile(document.get('profile'))
                run_document = document['run']
                run = (
                    None
                    if run_document is None
                    else normalize_shop_run(run_document)
                )
            except Exception as exc:
                self._raise_invalid(
                    'Shop transaction', self.paths.transaction, exc
                )
            self._write_signed(
                self.paths.profile, self._flag_integrity(profile).to_dict()
            )
            if run is None:
                self.paths.run.unlink(missing_ok=True)
            else:
                self._write_signed(self.paths.run, run.to_dict())
            self.paths.transaction.unlink(missing_ok=True)
            return True

    def commit(self, profile, run, transaction_id):
        with self._lock:
            self.prepare_commit(profile, run, transaction_id)
            self.recover_pending_transaction()
