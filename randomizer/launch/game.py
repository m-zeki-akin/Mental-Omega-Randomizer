"""Starting the game, and the folder it has to be started in.

Three things happen around every launch that have nothing to do with which
battle or mission it is: a ruleset the launcher generated is cleared so the
client cannot load it, the maps it hooked are cleared with it, and the
game's own option file is told the pace and the difficulty.

They lived in the window that used to be the only thing that launched. They
are here now because they are not a window's opinions -- they say nothing,
they return what they did, and whoever asked decides whether that is worth
writing down.
"""

import os
import shutil
import subprocess
import sys

from randomizer.core.paths import (
    GAME_EXE,
    GAME_LAUNCHER_EXE,
    GAME_ROOT,
    OPTIONS_INI,
    RULESMO_INI,
    DISABLED_RULESMO_INI,
    YR_OPTIONS_INI,
)
from randomizer.maps.assets import remove_generated_unit_art
from randomizer.maps.base import is_generated_hooked_map, is_generated_rules_file
from randomizer.maps.ini import read_text, set_ini_value_lines

from .options import patch_large_ini_key


# Beyond this an option file is not rewritten but patched in place. Some
# installations carry an option file far larger than one, and what is in
# the rest of it is not the launcher's to rewrite.
MAX_OPTION_INI_BYTES = 2 * 1024 * 1024


def game_command():
    """Return the command line that starts Mental Omega, spawned.

    -SPEEDCONTROL is the client's own flag and it is passed for that
    reason. Taking it away was an attempt to stop the speed being changed
    mid-match; it changed nothing, the slider is still there, and a command
    line the client never uses is a risk for no gain. What locks the speed
    is the speed table written into the map.
    """
    command = [
        str(GAME_LAUNCHER_EXE),
        GAME_EXE.name,
        '-SPAWN',
        '-CD',
        '-SPEEDCONTROL',
        '-LOG',
    ]
    if sys.platform == 'win32':
        return command
    wine = shutil.which('wine')
    if not wine:
        raise FileNotFoundError(
            'Wine is required to launch Mental Omega on this platform.'
        )
    winepath = shutil.which('winepath')
    if not winepath:
        raise FileNotFoundError(
            'winepath is required to resolve the Mental Omega executable.'
        )
    environment = os.environ.copy()
    environment['WINEDEBUG'] = '-all'
    resolved_path = subprocess.run(
        [winepath, '-w', str(GAME_EXE)],
        cwd=GAME_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not resolved_path:
        raise RuntimeError('Wine could not resolve the Mental Omega executable.')
    command[1] = resolved_path
    return [wine, *command]


def clear_generated_rules():
    """Take away the ruleset the launcher wrote, so the client loads none."""
    for path in (RULESMO_INI, DISABLED_RULESMO_INI):
        if path.exists() and is_generated_rules_file(path):
            path.unlink()
    remove_generated_unit_art()


def clear_generated_root_maps():
    """Take away the maps the launcher hooked. Returns what would not go."""
    failed = []
    # Both spellings, and each file once. Windows matches a glob without
    # regard to case, so the two patterns name the same file twice there,
    # and the second removal of it used to be reported as a failure.
    found = {
        path.name: path
        for pattern in ('*.MAP', '*.map')
        for path in GAME_ROOT.glob(pattern)
    }
    for path in found.values():
        if not is_generated_hooked_map(path):
            continue
        try:
            path.unlink()
        except OSError as exc:
            failed.append((path.name, str(exc)))
    return failed


def patch_large_options(path, values):
    """Patch one-digit values in an oversized option file, in place.

    Returns the keys that could not be patched, so the caller can say so.
    """
    with path.open('r+b') as handle:
        patched = [
            key for key, value in values.items()
            if patch_large_ini_key(handle, key, value)
        ]
    return sorted(set(values) - set(patched))


def write_game_options(difficulty_value, game_speed_value):
    """Write the pace and the difficulty into the game's own option files.

    Returns the files written and the ones too large to rewrite, which are
    patched in place instead. Option files the installation does not
    already use are not created: RA2MO.ini is Mental Omega's own, RA2MD.INI
    is optional, and one written needlessly was a bug once.
    """
    written = []
    skipped = []
    values = {
        'GameSpeed': game_speed_value,
        'Difficulty': difficulty_value,
        'CampDifficulty': difficulty_value,
    }
    for path in (OPTIONS_INI, YR_OPTIONS_INI):
        if not path.exists():
            continue
        if path.stat().st_size > MAX_OPTION_INI_BYTES:
            try:
                missing = patch_large_options(path, values)
            except OSError as exc:
                skipped.append((path.name, str(exc)))
                continue
            if missing:
                skipped.append((path.name, ', '.join(missing)))
            else:
                written.append(f'{path.name} (in-place)')
            continue
        text = read_text(path)
        for key, value in values.items():
            text = set_ini_value_lines(text, 'Options', key, value)
        path.write_bytes(text.encode('utf-8'))
        written.append(path.name)
    return written, skipped
