"""Remove PyInstaller extraction folders left behind by earlier launches.

A one-file build unpacks its whole payload -- Python, Tcl/Tk, configs, assets,
about 33 MB -- into a ``_MEI*`` folder before any of this code runs, and the
bootloader deletes it again only when the process exits cleanly. A launcher
that is killed, crashes, or dies with the machine leaves its copy behind, and
nothing else will ever clean it up.

Telling a leftover from the folder a second launcher is using right now is the
whole problem. Renaming is not the test it looks like: Windows happily renames
both the folder and the loaded Python DLL inside it while the owning process
runs, so a rename that succeeds proves nothing. Deleting is the only operation
the operating system actually refuses, which is too late to be a probe. So the
process id in the folder name is the gate, and deletion only ever starts once
the owner is known to be gone.
"""

import os
import shutil
import sys
from pathlib import Path

PREFIX = '_MEI'
# GetExitCodeProcess reports this for a handle whose process is still running.
_STILL_ACTIVE = 259
_SYNCHRONIZE = 0x00100000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
# How many trailing digits of a folder name may belong to the counter
# rather than the process id.
MAXIMUM_COUNTER_DIGITS = 3


def _process_is_running(pid):
    """Return whether a process id belongs to a live process.

    Deliberately not ``os.kill(pid, 0)``: on Windows that is implemented with
    TerminateProcess, so the liveness check would kill the very launcher it is
    asking about.
    """
    if pid <= 0:
        return False
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    handle = kernel32.OpenProcess(
        _SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        # No handle means either no such process or one we may not inspect.
        # Access denied still means something is there, so treat it as live.
        return ctypes.get_last_error() == 5
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _candidate_pids(name):
    """Return every process id a ``_MEI`` folder name could encode.

    The bootloader names the folder ``_MEI`` followed by the process id and a
    small counter, with no separator, so ``_MEI296482`` is process 29648 with
    counter 2. Where the id ends cannot be read off the name, so every
    plausible split is checked and any live match keeps the folder -- erring
    towards leaving a folder behind rather than deleting one still in use.

    Only the counter is allowed to be short. Splitting all the way down would
    offer single-digit candidates that collide with the always-running system
    processes, and a folder blocked by those would never be cleaned at all.
    """
    digits = name[len(PREFIX):]
    if not digits.isdigit():
        return ()
    return tuple(dict.fromkeys(
        int(digits[:length])
        for length in range(max(1, len(digits) - MAXIMUM_COUNTER_DIGITS),
                            len(digits) + 1)
    ))


def _is_in_use(directory):
    return any(
        _process_is_running(pid) for pid in _candidate_pids(directory.name)
    )


LEGACY_RUNTIME_DIRECTORY = 'RandomizerLauncherRuntime'


def _search_roots(bundle_root):
    """Return the folders that can hold extraction leftovers.

    Normally just the system temporary folder this build unpacks into. Two
    older layouts still have to be swept, because an upgraded installation
    keeps whatever they left and nothing else will ever look there again:
    the earliest builds extracted straight beside the executable, and later
    ones into a RandomizerLauncherRuntime folder of their own in the game
    folder.
    """
    roots = [bundle_root.parent]
    try:
        beside_executable = Path(sys.executable).resolve().parent
    except OSError:
        return tuple(roots)
    for root in (beside_executable, beside_executable / LEGACY_RUNTIME_DIRECTORY):
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def _remove_empty_legacy_runtime_directory():
    """Delete the old runtime folder once the sweep has emptied it.

    Only when empty: a folder that still holds a live extraction belongs to a
    launcher that is running right now.
    """
    try:
        legacy = Path(sys.executable).resolve().parent / LEGACY_RUNTIME_DIRECTORY
    except OSError:
        return None
    try:
        legacy.rmdir()
    except OSError:
        return None
    return legacy


def _runtime_directories(bundle_root):
    """Return extraction folders that are not the one we are running from."""
    found = []
    for root in _search_roots(bundle_root):
        try:
            candidates = sorted(root.glob(PREFIX + '*'))
        except OSError:
            continue
        found.extend(
            candidate for candidate in candidates
            if candidate != bundle_root and candidate.is_dir()
        )
    return tuple(found)


def sweep_stale_runtime_directories(bundle_root=None):
    """Delete extraction folders from launcher runs that never exited.

    Returns the folders actually removed. A source run extracts nothing and
    has nothing to sweep, so it returns empty without touching the disk.
    """
    if bundle_root is None:
        bundle_path = getattr(sys, '_MEIPASS', None)
        if not bundle_path:
            return ()
        bundle_root = Path(bundle_path)
    bundle_root = Path(bundle_root)
    removed = []
    for directory in _runtime_directories(bundle_root):
        if _is_in_use(directory):
            continue
        # Only past this gate, where the owning process is gone, is a partial
        # delete harmless: there is nothing left running to break.
        shutil.rmtree(directory, ignore_errors=True)
        if not directory.exists():
            removed.append(directory)
    legacy = _remove_empty_legacy_runtime_directory()
    if legacy is not None:
        removed.append(legacy)
    return tuple(removed)
