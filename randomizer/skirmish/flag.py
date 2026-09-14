"""The flag a seated house shows.

The player sits on a spare country wearing the one they chose, and the map
rewrites the seat's country section into a copy of the chosen one --
``File.Flag`` included. The diplomacy panel showed the seat's own flag
anyway, because the engine loads that image once at startup, by the file
name the *rules* give the seat, before any map is read. The name in the
map is honoured; the picture behind it was loaded long before.

So the picture is what changes. Before a battle the chosen country's flag
image is put in the game root under the seat's file name -- a loose file
is what the engine loads ahead of any archive, which is how a submod ships
one -- and taken away again when the battle is over. A seat is a country
nobody else in the battle plays, so nobody else's flag is touched.

A PCX cannot carry the launcher's comment marker the way the staged AI
file does, so what was written is remembered by its digest instead: a
file that no longer reads the way it was written is somebody else's now,
and a file that was already there was somebody else's to begin with.
"""

import hashlib
import json
from pathlib import Path

from randomizer.core.diagnostics import event as log_event
from randomizer.core.paths import APP_DIR, GAME_ROOT


# The two images a country shows for itself in a match: the diplomacy
# panel's flag, and the observer view's. Both are named on the country.
FLAG_KEYS = ('File.Flag', 'File.ObserverFlag')
STAGED_FLAGS_MANIFEST = APP_DIR / 'staged_flags.json'


def _value(section, key):
    wanted = str(key).lower()
    return next(
        (
            str(value).strip() for name, value in (section or {}).items()
            if str(name).lower() == wanted
        ),
        '',
    )


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def flag_plan(rules, chosen, seat):
    """Return ``((seat's file name, chosen's file name), ...)``.

    One pair per image the two countries name differently. A seat that is
    the chosen country, or a country that names no flag, plans nothing.
    """
    if not chosen or not seat or str(chosen).lower() == str(seat).lower():
        return ()
    theirs = rules.get(seat) or {}
    ours = rules.get(chosen) or {}
    plan = []
    for key in FLAG_KEYS:
        target = Path(_value(theirs, key)).name
        source = Path(_value(ours, key)).name
        if not target or not source or target.lower() == source.lower():
            continue
        pair = (target, source)
        if pair not in plan:
            plan.append(pair)
    return tuple(plan)


def _installed_rules():
    from randomizer.ui.cameos import installed_rules_registry

    _superweapons, rules = installed_rules_registry(synchronous=True)
    return rules or {}


def _extract(source):
    """Return one image's bytes out of the installation, or nothing."""
    from randomizer.ui.cameos import CAMEO_CACHE_DIR, extract_mix_files_sync

    output = Path(CAMEO_CACHE_DIR) / source
    extract_mix_files_sync([(source, output)])
    if output.is_file() and output.stat().st_size > 0:
        return output.read_bytes()
    return None


def stage_seat_flags(chosen, seat, *, rules=None, game_root=GAME_ROOT,
                     manifest=STAGED_FLAGS_MANIFEST, fetch=None):
    """Put the chosen country's images where the seat's names point.

    Returns the file names written. Whatever an earlier battle staged is
    taken away first, so two battles never stack; a file already in the
    root is somebody else's and is left alone.
    """
    rules = _installed_rules() if rules is None else rules
    fetch = _extract if fetch is None else fetch
    manifest = Path(manifest)
    remove_staged_flags(manifest=manifest)
    root = Path(game_root)
    staged = {}
    for target, source in flag_plan(rules, chosen, seat):
        destination = root / target
        if destination.exists():
            log_event('skirmish_flag_left_alone', path=str(destination))
            continue
        data = fetch(source)
        if not data:
            log_event('skirmish_flag_missing', source=source)
            continue
        try:
            destination.write_bytes(data)
        except OSError as exc:
            log_event('skirmish_flag_not_staged', path=str(destination),
                      error=str(exc))
            continue
        staged[target] = _digest(data)
    if staged:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps({'game_root': str(root), 'files': staged}, indent=2),
            encoding='utf-8',
        )
        log_event('skirmish_flags_staged', seat=seat, chosen=chosen,
                  files=sorted(staged))
    return tuple(staged)


def remove_staged_flags(*, manifest=STAGED_FLAGS_MANIFEST):
    """Remove the images this launcher staged, and only those.

    Returns the file names removed. A file that no longer reads the way it
    was written is left where it is: it is somebody else's now.
    """
    manifest = Path(manifest)
    if not manifest.is_file():
        return ()
    try:
        document = json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        document = {}
    root = Path(str(document.get('game_root') or GAME_ROOT))
    removed = []
    for name, digest in (document.get('files') or {}).items():
        path = root / str(name)
        try:
            if path.is_file() and _digest(path.read_bytes()) == digest:
                path.unlink()
                removed.append(str(name))
            elif path.is_file():
                log_event('skirmish_flag_left_alone', path=str(path))
        except OSError as exc:
            log_event('skirmish_flag_not_removed', path=str(path),
                      error=str(exc))
    try:
        manifest.unlink()
    except OSError:
        pass
    return tuple(removed)
