"""The half of a match setting that lives in the map, not in spawn.ini.

A game option is two things at once. ``spawn.ini`` carries the flag the
spawner reads, and for most options the client also merges a small INI into
the map: ``Stolen Tech.ini`` is what actually sets ``Spyable=yes`` on every
Construction Yard and Tech Centre, ``Mental AI.ini`` is what actually raises
the AI's build counts. Writing the flag without merging the file leaves a
match that says one thing and plays another -- a spy that cannot infiltrate
anything, in a game whose settings say stolen tech is on.

Which file belongs to which flag is not knowledge to keep here: the client
states it in ``Resources/GameOptions.ini``, one ``SpawnIniOption`` and
``CustomIniPath`` per checkbox, so that file is read and followed. The three
dropdowns that write map code rather than a flag (ore growth, tech defence,
superweapons) are followed the same way, from their ``DefaultIndex``.
"""

from pathlib import Path
import re

from randomizer.core.paths import GAME_ROOT

from .mapfile import merge_into_map


GAME_OPTIONS_PATH = GAME_ROOT / 'Resources' / 'GameOptions.ini'
TRUE_VALUES = frozenset({'true', 'yes', '1', 'on'})


def read_ini_sections(path):
    """Return ``{section: {key: value}}`` for a small INI, keys in order."""
    try:
        text = Path(path).read_bytes().decode('utf-8', errors='ignore')
    except OSError:
        return {}
    sections = {}
    current = None
    for line in text.splitlines():
        line = line.split(';', 1)[0].strip()
        if not line:
            continue
        header = re.match(r'^\[(.+?)\]$', line)
        if header:
            current = sections.setdefault(header.group(1).strip(), {})
            continue
        if current is None or '=' not in line:
            continue
        key, value = line.split('=', 1)
        current[key.strip()] = value.strip()
    return sections


def _is_on(value):
    return str(value).strip().lower() in TRUE_VALUES


def parse_game_options(sections):
    """Return what the client says each option merges into the map.

    ``checkboxes`` maps a spawn.ini flag to the INI merged when it is on;
    ``dropdowns`` are the ones whose whole answer is a map code path, given
    as ``(items, default_index)``.
    """
    checkboxes = {}
    dropdowns = []
    for values in sections.values():
        custom = values.get('CustomIniPath')
        option = values.get('SpawnIniOption')
        if custom and option:
            checkboxes[option] = custom
            continue
        if str(values.get('DataWriteMode', '')).strip().lower() != 'mapcode':
            continue
        items = [
            item.strip() for item in str(values.get('Items', '')).split(',')
            if item.strip()
        ]
        if not items:
            continue
        try:
            default = int(values.get('DefaultIndex', 0))
        except (TypeError, ValueError):
            default = 0
        dropdowns.append((tuple(items), default))
    return checkboxes, dropdowns


def option_map_code_paths(settings, *, game_root=None, selections=None):
    """Return the INIs this match's settings put into the map, in client order.

    ``selections`` names a dropdown's chosen item by index, for the three
    that write map code; anything unnamed takes the client's own default.
    """
    root = Path(game_root) if game_root else GAME_ROOT
    options_path = (
        root / 'Resources' / 'GameOptions.ini' if game_root
        else GAME_OPTIONS_PATH
    )
    checkboxes, dropdowns = parse_game_options(read_ini_sections(options_path))
    paths = []
    for option, custom in checkboxes.items():
        if not _is_on((settings or {}).get(option, 'False')):
            continue
        paths.append(root / Path(str(custom).replace('\\', '/')))
    for index, (items, default) in enumerate(dropdowns):
        chosen = (selections or {}).get(index, default)
        if not 0 <= chosen < len(items):
            chosen = default
        paths.append(root / Path(str(items[chosen]).replace('\\', '/')))
    return tuple(path for path in paths if path.is_file())


def option_ini_path(option, *, game_root=None):
    """Return the INI one named game option merges, on or off.

    Some of what an option turns on is only described in its own file --
    the stolen-tech units carry their country lists and their
    ``Prerequisite.StolenTechs`` there and nowhere else -- so a reader that
    needs those has to be able to ask for the file by the flag's name.
    """
    root = Path(game_root) if game_root else GAME_ROOT
    options_path = (
        root / 'Resources' / 'GameOptions.ini' if game_root
        else GAME_OPTIONS_PATH
    )
    checkboxes, _dropdowns = parse_game_options(read_ini_sections(options_path))
    custom = checkboxes.get(str(option))
    if not custom:
        return None
    path = root / Path(str(custom).replace('\\', '/'))
    return path if path.is_file() else None


def merge_game_options(map_path, settings, *, game_root=None, selections=None):
    """Write every option's map code into the map, and say what it cost.

    Returns ``(files, keys)``. A file the installation does not have is not
    an error: a submod may ship fewer options than the stock client lists.
    """
    files = keys = 0
    for path in option_map_code_paths(
        settings, game_root=game_root, selections=selections
    ):
        sections = read_ini_sections(path)
        if not sections:
            continue
        keys += merge_into_map(map_path, sections)
        files += 1
    return files, keys
