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
from randomizer.core.storage import atomic_write_opaque, read_opaque_object

from .model import ShopRunCollection
from .state import (
    normalize_shop_profile,
    normalize_shop_run,
    normalize_shop_run_collection,
)


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
        self._adopt_legacy_files()
        # A failed signature on the run or the journal has to reach the
        # profile, which is where the flag lives and where it is signed.
        # Reads are ordered profile-first, so it is remembered here until a
        # profile passes through.
        self._integrity_breach = False

    def _adopt_legacy_files(self):
        """Rename state written under the old readable names, once.

        Only the name moves. The reader accepts plain JSON, so the file is
        still loaded exactly as it was and converts on its next write; doing
        it this way means a failed rename costs nothing and a half-converted
        profile cannot exist.
        """
        for path in (
            self.paths.profile, self.paths.run, self.paths.transaction,
        ):
            legacy = path.with_suffix('.json')
            if legacy == path or path.exists() or not legacy.is_file():
                continue
            try:
                legacy.replace(path)
            except OSError:
                continue

    def _write_signed(self, path, document):
        atomic_write_opaque(path, sign(document))

    def _read_signed(self, path, label):
        """Read one document, noting whether its signature held.

        A bad signature is not a corrupt file and must not take the corruption
        path: that one moves the file aside and raises, which would destroy the
        progress of a player whose disk went bad rather than a cheat. Tamper is
        loaded, played, and flagged.
        """
        document = read_opaque_object(path)
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

    def _keep_pre_multirun_copy(self):
        """Copy the one-run file aside, once, before it becomes a list.

        Nothing about the conversion is lossy, but it rewrites the only file
        holding a run in progress, and a player who hits a bug in it has no
        other copy. The backup is written before the first rewrite and never
        overwritten afterwards, so it stays the save as it was on the last
        version that could not read a list.
        """
        backup = self.paths.backup_dir / f'{self.paths.run.name}.pre-multirun'
        if backup.exists() or not self.paths.run.is_file():
            return
        try:
            self.paths.backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.paths.run, backup)
        except OSError as exc:
            # A backup that cannot be written is worth saying so, but it is
            # not worth refusing to load a run the player can still play.
            log_event(
                'shop_run_backup_failed',
                level=logging.WARNING,
                error=str(exc),
            )

    def _read_run_collection(self):
        if not self.paths.run.is_file():
            return ShopRunCollection()
        try:
            raw = self._read_signed(self.paths.run, 'run')
            legacy_shape = isinstance(raw, dict) and 'runs' not in raw
            collection = normalize_shop_run_collection(raw)
        except Exception as exc:
            self._raise_invalid('Shop run', self.paths.run, exc)
        normalized = collection.to_dict()
        if raw != sign(normalized):
            if legacy_shape:
                self._keep_pre_multirun_copy()
            self._write_signed(self.paths.run, normalized)
        return collection

    def _write_run_collection(self, collection):
        """Write the run list, or remove the file once it holds nothing."""
        if not collection.runs:
            self.paths.run.unlink(missing_ok=True)
            return
        self._write_signed(self.paths.run, collection.to_dict())

    def _read_run(self):
        return self._read_run_collection().active()

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
        """Store one run and make it the active one.

        Callers hold a run they loaded and hand it back changed, so this
        writes over the stored run of the same id and leaves every other run
        exactly as it was.
        """
        with self._lock:
            self.recover_pending_transaction()
            normalized = normalize_shop_run(run.to_dict())
            self._write_run_collection(
                self._read_run_collection().with_run(normalized)
            )

    def list_runs(self):
        """Return every stored run, and which id is active."""
        with self._lock:
            self.recover_pending_transaction()
            collection = self._read_run_collection()
            return collection.runs, collection.active_run_id

    def select_run(self, run_id):
        """Make one stored run the one ``load_run`` returns."""
        with self._lock:
            self.recover_pending_transaction()
            collection = self._read_run_collection()
            try:
                selected = collection.selecting(run_id)
            except KeyError:
                raise ShopPersistenceError(
                    f'No stored Shop run {run_id!r}'
                ) from None
            self._write_run_collection(selected)
            return selected.active()

    def delete_run(self, run_id):
        """Forget one stored run. Deleting the active one leaves none active."""
        with self._lock:
            self.recover_pending_transaction()
            collection = self._read_run_collection()
            if collection.run(run_id) is None:
                raise ShopPersistenceError(f'No stored Shop run {run_id!r}')
            self._write_run_collection(collection.without_run(run_id))

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
            # The journal names the exact file contents to restore, and the
            # run file holds every run -- so a commit that touches one run
            # carries the others through unchanged rather than replaying a
            # file with only the committed run left in it. ``run=None`` still
            # means what it always meant: no runs at all, which is how a
            # profile reset clears the file.
            collection = (
                ShopRunCollection() if normalized_run is None
                else self._read_run_collection().with_run(normalized_run)
            )
            document = {
                'schema_version': SHOP_TRANSACTION_SCHEMA_VERSION,
                'transaction_id': transaction_id,
                'profile': normalized_profile.to_dict(),
                'runs': collection.to_dict(),
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
            journal_state = verify(read_opaque_object(self.paths.transaction))
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
                document = read_opaque_object(self.paths.transaction)
                if document.get('schema_version') != SHOP_TRANSACTION_SCHEMA_VERSION:
                    raise ValueError(
                        'Unsupported Shop transaction schema_version '
                        f'{document.get("schema_version")!r}'
                    )
                if not isinstance(document.get('transaction_id'), str) or not document[
                    'transaction_id'
                ]:
                    raise ValueError('Shop transaction_id must be non-empty')
                profile = normalize_shop_profile(document.get('profile'))
                if 'runs' in document:
                    collection = normalize_shop_run_collection(
                        document['runs']
                    )
                elif 'run' in document:
                    # A journal left behind by a version that wrote one run.
                    # Its target is that run, merged into whatever else the
                    # run file has since grown to hold.
                    run_document = document['run']
                    collection = (
                        ShopRunCollection() if run_document is None
                        else self._read_run_collection().with_run(
                            normalize_shop_run(run_document)
                        )
                    )
                else:
                    raise ValueError('Shop transaction has no run target')
            except Exception as exc:
                self._raise_invalid(
                    'Shop transaction', self.paths.transaction, exc
                )
            self._write_signed(
                self.paths.profile, self._flag_integrity(profile).to_dict()
            )
            self._write_run_collection(collection)
            self.paths.transaction.unlink(missing_ok=True)
            return True

    def commit(self, profile, run, transaction_id):
        with self._lock:
            self.prepare_commit(profile, run, transaction_id)
            self.recover_pending_transaction()
