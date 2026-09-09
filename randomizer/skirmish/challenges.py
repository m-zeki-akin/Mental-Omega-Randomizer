"""Challenge maps, played the way the client plays them.

A challenge is not a skirmish on a smaller map. Mental Omega's client
describes each one in ``INI/MentalOmegaMaps.ini``: three scripted enemy
houses with the countries, colours and starting points the fight was
designed around, the player at the first start, a second start held for a
co-op partner, and a game mode -- Challenge Easy, Medium or Hard -- that
forces its own match options and merges an INI of triggers into the map.

It also numbers them, ``CHAL01`` to ``CHAL22`` under ``[MultiMaps]``, and
that ordering is a difficulty curve: the later ones are a different game
from the early ones, so a run meets them only once it has been through
once.

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

from .mapfile import merge_into_map
from .maps import MAPS_DIR


MAPS_INI = GAME_ROOT / 'INI' / 'MentalOmegaMaps.ini'
MAP_CODE_DIR = GAME_ROOT / 'INI' / 'Map Code'

# Where the client keeps its own numbering: ``CHAL13 = MapsMO\Challenge\
# c_aberration`` under [MultiMaps]. That is what "Challenge XIII" means, and
# reading it beats reading the description, which a submod may rename.
MULTI_MAPS = 'MultiMaps'
CHALLENGE_NUMBER = re.compile(r'^CHAL(\d+)$', re.I)
# The numeral in "Challenge XIII: Aberration", for a map the list above
# does not carry.
DESCRIBED_NUMBER = re.compile(r'challenge\s+([ivxl]+)\b', re.I)
ROMAN = {'i': 1, 'v': 5, 'x': 10, 'l': 50}

# How far a first walk goes. The challenges past this one were built for
# players who have already finished the run once, so they wait for
# nightmare rather than closing a tier of the first attempt.
FIRST_WALK_CHALLENGES = 12

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
    # Which challenge this is in the client's own order. Zero for a map the
    # installation lists without numbering, which is then treated as one of
    # the early ones rather than held back.
    number: int = 0


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


def _relative_path(name):
    """Turn ``MapsMO\\Challenge\\c_freedom`` into ``Challenge/c_freedom.map``."""
    relative = str(name).strip().replace('\\', '/')
    if relative.lower().startswith('mapsmo/'):
        relative = relative[len('MapsMO/'):]
    return f'{relative}.map'


def _roman(numeral):
    """Read a numeral the way the descriptions write them, or zero."""
    total = 0
    values = [ROMAN.get(letter, 0) for letter in numeral.lower()]
    for index, value in enumerate(values):
        after = values[index + 1:]
        total += -value if after and value < max(after) else value
    return total


def parse_challenge_numbers(sections):
    """Return ``{relative map path: number}`` from the client's own list."""
    numbers = {}
    for key, value in _values(sections.get(MULTI_MAPS, '')).items():
        found = CHALLENGE_NUMBER.match(key.strip())
        if found and value.strip():
            numbers[_relative_path(value)] = int(found.group(1))
    return numbers


def parse_challenges(sections):
    """Read the challenge entries out of the client's map list."""
    numbers = parse_challenge_numbers(sections)
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
        relative = _relative_path(name)
        described = values.get('Description', '')
        numeral = DESCRIBED_NUMBER.search(described)
        result[relative] = Challenge(
            map_path=relative,
            description=described,
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
            number=numbers.get(
                relative, _roman(numeral.group(1)) if numeral else 0
            ),
        )
    return result


def in_first_walk(challenge):
    """Whether a run that has not been through once may be dealt this one."""
    return challenge is None or challenge.number <= FIRST_WALK_CHALLENGES


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
    """Merge one of the mode INIs into the map copied into place."""
    code = _sections(
        Path(code_path).read_text(encoding='utf-8', errors='ignore')
    )
    return merge_into_map(
        map_path, {name: _values(body) for name, body in code.items()}
    )


def challenge_map_paths():
    """Return the challenge maps this installation both lists and has."""
    return tuple(
        path for path in challenges()
        if (MAPS_DIR / path).is_file()
    )
