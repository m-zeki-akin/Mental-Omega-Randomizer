"""Challenge maps, played the way the client plays them.

A challenge is not a skirmish on a smaller map. Mental Omega's client
describes each one in ``INI/MentalOmegaMaps.ini``: three scripted enemy
houses with the countries, colours and starting points the fight was
designed around, the player alone at the first start, and a game mode --
Challenge Easy, Medium or Hard -- that forces its own match options and
merges an INI of triggers into the map.

Handing those maps three random armies and calling it Standard is a
different game entirely, and a much emptier one: the scripted opposition is
the challenge.

Everything here is read from the installation rather than copied into the
launcher, because it is the installation's own description of its maps.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

from randomizer.core.paths import GAME_ROOT

from .maps import MAPS_DIR


MAPS_INI = GAME_ROOT / 'INI' / 'MentalOmegaMaps.ini'
MAP_CODE_DIR = GAME_ROOT / 'INI' / 'Map Code'

# The client's own three challenge modes, hardest first. CoopDifficultyLevel
# counts the other way from everything else: 0 is Hard.
CHALLENGE_MODES = (
    ('Challenge Hard', 0),
    ('Challenge Medium', 1),
    ('Challenge Easy', 2),
)
CHALLENGE_MODE_BY_LEVEL = {level: name for name, level in CHALLENGE_MODES}

# What a client option is called once it reaches the spawn file. Confirmed
# against a spawn.ini the client wrote beside the settings it wrote it from.
FORCED_OPTION_KEYS = {
    'chkshortgame': 'ShortGame',
    'chkredeplmcv': 'MCVRedeploy',
    'chkcrates': 'Crates',
    'chkingameallying': 'AlliesAllowed',
    'chkbuildoffally': 'BuildOffAlly',
    'chknavalcombat': 'NavalCombat',
    'chkstolentech': 'StolenTech',
    'chkfreeradar': 'FreeRadar',
    'chklimitedmcv': 'LimitedMCV',
    'chkconyardstart': 'ConYardStart',
    'chknospawnpreviews': 'NoSpawnPreviews',
    'chknogarrisons': 'NoGarrisons',
    'chkmentalai': 'MentalAI',
    'chkimmunederricks': 'ImmuneDerricks',
    'chkdevnerfeights': 'NerfEights',
}


@dataclass(frozen=True)
class ChallengeHouse:
    country: int
    color: int
    start: int


@dataclass(frozen=True)
class Challenge:
    map_path: str
    description: str
    houses: tuple[ChallengeHouse, ...]
    modes: tuple[str, ...]
    forced_options: str = ''
    disallowed_colors: tuple[int, ...] = ()
    human_starts: int = 1


def _sections(text):
    parts = re.split(r'^\[(.+?)\]\s*$', text, flags=re.M)
    return {
        name.strip(): body
        for name, body in zip(parts[1::2], parts[2::2])
    }


def _values(body):
    values = {}
    for line in (body or '').splitlines():
        line = line.split(';', 1)[0].strip()
        if '=' not in line or line.startswith('['):
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip()
    return values


@lru_cache(maxsize=1)
def _maps_ini_sections():
    if not MAPS_INI.is_file():
        return {}
    return _sections(MAPS_INI.read_text(encoding='utf-8', errors='ignore'))


@lru_cache(maxsize=1)
def challenges():
    """Return ``{relative map path: Challenge}`` for every challenge map."""
    return parse_challenges(_maps_ini_sections())


def parse_challenges(sections):
    """Read the challenge entries out of the client's map list."""
    result = {}
    for name, body in sections.items():
        if 'Challenge' not in name or not name.lower().startswith('mapsmo'):
            continue
        values = _values(body)
        if not values.get('GameModes', '').startswith('Challenge'):
            continue
        houses = []
        for key in sorted(values):
            if not key.lower().startswith('enemyhouse'):
                continue
            parts = [part.strip() for part in values[key].split(',')]
            if len(parts) < 3:
                continue
            houses.append(ChallengeHouse(
                country=int(parts[0]), color=int(parts[1]), start=int(parts[2])
            ))
        relative = name.replace('\\', '/')
        if relative.lower().startswith('mapsmo/'):
            relative = relative[len('MapsMO/'):]
        result[f'{relative}.map'] = Challenge(
            map_path=f'{relative}.map',
            description=values.get('Description', ''),
            houses=tuple(houses),
            modes=tuple(
                mode.strip()
                for mode in values.get('GameModes', '').split(',')
                if mode.strip()
            ),
            forced_options=values.get('ForcedOptions', ''),
            disallowed_colors=tuple(
                int(color) for color in
                values.get('DisallowedPlayerColors', '').split(',')
                if color.strip().isdigit()
            ),
            human_starts=sum(
                1 for key in values if key.lower().startswith('waypoint')
            ) or 1,
        )
    return result


def challenge_for(map_path):
    return challenges().get(str(map_path or '').replace('\\', '/'))


def forced_options(*names):
    """Return the spawn settings these forced-option sections ask for."""
    return parse_forced_options(_maps_ini_sections(), *names)


def parse_forced_options(sections, *names):
    settings = {}
    for name in names:
        if not name:
            continue
        for key, value in _values(sections.get(name, '')).items():
            spawn_key = FORCED_OPTION_KEYS.get(key.lower())
            if not spawn_key:
                # cmbOreGrowth and its like are not spawn settings; the
                # client applies them as map code instead.
                continue
            settings[spawn_key] = (
                'True' if value.strip().lower() in {'true', 'yes', '1'}
                else 'False'
            )
    return settings


def challenge_mode_for_level(level):
    return CHALLENGE_MODE_BY_LEVEL.get(int(level), 'Challenge Medium')


def map_code_path(mode):
    path = MAP_CODE_DIR / f'{mode}.ini'
    return path if path.is_file() else None


def merge_map_code(map_path, code_path):
    """Merge one of the mode INIs into a copy of the map, as the client does.

    The client consolidates the two files: a key the mode INI names replaces
    the map's, and a section the map does not have is added. Appending the
    file instead would leave the map's own value first, and the reader keeps
    the first it sees -- which is exactly the value the mode meant to change.
    """
    map_path = Path(map_path)
    code = _sections(
        Path(code_path).read_text(encoding='utf-8', errors='ignore')
    )
    if not code:
        return 0
    original = map_path.read_bytes().decode('utf-8', errors='ignore')
    # These maps are written with bare line feeds. Rewriting them as CRLF
    # would change every line of a file the merge has no business reshaping.
    newline = '\r\n' if '\r\n' in original else '\n'
    lines = original.splitlines()
    # Where each section starts and ends, in the order the map has them.
    bounds = {}
    current = None
    start = 0
    for index, line in enumerate(lines):
        header = re.match(r'^\[(.+?)\]\s*$', line.strip())
        if not header:
            continue
        if current is not None:
            bounds.setdefault(current, (start, index))
        current = header.group(1).strip()
        start = index + 1
    if current is not None:
        bounds.setdefault(current, (start, len(lines)))

    applied = 0
    additions = []
    # Rewritten from the bottom up so earlier line numbers stay valid.
    for section in sorted(
        code, key=lambda name: bounds.get(name, (len(lines), 0))[0],
        reverse=True,
    ):
        values = _values(code[section])
        if not values:
            continue
        if section not in bounds:
            additions.append((section, values))
            continue
        begin, end = bounds[section]
        body = lines[begin:end]
        for key, value in values.items():
            replaced = False
            for offset, line in enumerate(body):
                stripped = line.split(';', 1)[0].strip()
                if '=' not in stripped:
                    continue
                if stripped.split('=', 1)[0].strip().lower() == key.lower():
                    body[offset] = f'{key}={value}'
                    replaced = True
                    break
            if not replaced:
                body.append(f'{key}={value}')
            applied += 1
        lines[begin:end] = body
    for section, values in reversed(additions):
        lines.append('')
        lines.append(f'[{section}]')
        for key, value in values.items():
            lines.append(f'{key}={value}')
            applied += 1
    with open(map_path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(newline.join(lines) + newline)
    return applied


def challenge_map_paths():
    """Return the challenge maps this installation both lists and has."""
    return tuple(
        path for path in challenges()
        if (MAPS_DIR / path).is_file()
    )
