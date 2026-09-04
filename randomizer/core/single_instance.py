"""One launcher per game folder.

Nothing stopped several launchers running against the same installation. Each
one rebuilds caches, extracts MIX members, and clears the same runtime asset
staging directory, so a handful of accidental double-clicks turns into a heavy
CPU and memory load and instances start failing on each other's open files.

The lock is an OS-level exclusive lock on a file in the launcher's own data
directory, so it is released even if the process is killed. A stale lock left
by a crash therefore never blocks the next start.
"""

import os
import re
import sys
from pathlib import Path

from randomizer.core.paths import APP_DIR

LOCK_PATH = APP_DIR / 'launcher.lock'


class AlreadyRunningError(RuntimeError):
    """Raised when another launcher already owns this game folder."""


def _lock_exclusive(handle):
    """Take a non-blocking exclusive lock; False when another holder exists."""
    if os.name == 'nt':
        import msvcrt

        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def acquire_single_instance_lock(path=None):
    """Return the held lock handle, or raise when another launcher has it.

    The caller keeps the returned handle for the process lifetime; closing it
    or exiting releases the lock.
    """
    path = Path(path or LOCK_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Not append mode: writes must land at a known offset so the PID can
    # be read back from outside the locked byte.
    try:
        handle = open(path, 'r+b')
    except FileNotFoundError:
        handle = open(path, 'w+b')
    try:
        handle.seek(0)
        if not _lock_exclusive(handle):
            raise AlreadyRunningError(
                f'Another Mental Omega Randomizer is already running for '
                f'{path.parent.parent}.'
            )
    except AlreadyRunningError:
        handle.close()
        raise
    except OSError:
        # A filesystem that cannot lock must not stop the launcher from
        # starting; the guard is a safety net, not a requirement.
        handle.close()
        return None
    try:
        # Byte 0 is the locked region and other processes cannot read it
        # while the lock is held, so keep it as filler and record the PID
        # after it where the already-running message can read it.
        handle.seek(0)
        handle.write(b'#' + str(os.getpid()).encode('ascii'))
        handle.truncate()
        handle.flush()
    except OSError:
        pass
    return handle


def running_instance_pid(path=None):
    """Return the PID recorded by the lock holder, or None."""
    path = Path(path or LOCK_PATH)
    try:
        with open(path, 'rb') as handle:
            # Skip the locked byte: a read spanning it is denied while
            # the holder has the lock.
            handle.seek(1)
            recorded = handle.read(64)
    except OSError:
        return None
    # Scan for the digits rather than trusting an offset: the lock byte and
    # platform buffering both shift where the PID lands.
    digits = re.search(rb'\d+', recorded)
    return int(digits.group()) if digits else None


def focus_running_instance():
    """Raise the launcher that already owns this folder. True when focused."""
    if os.name != 'nt':
        return False
    try:
        import ctypes

        from randomizer.core.version import APP_VERSION

        user32 = ctypes.windll.user32
        handle = user32.FindWindowW(
            None, f'Mental Omega Randomizer Launcher v{APP_VERSION}'
        )
        if not handle:
            return False
        user32.ShowWindow(handle, 9)  # SW_RESTORE
        user32.SetForegroundWindow(handle)
        return True
    except Exception:
        return False


def report_already_running():
    """Point the player at the launcher that is already open, then leave.

    Deliberately not a message box. The case this guard exists for is many
    instances starting at once, and a modal dialog per instance would keep
    every one of them alive waiting for a click -- the pile-up it is meant to
    prevent. Raising the existing window is the feedback instead.
    """
    focus_running_instance()
