"""What the installation can be asked to play, and how many it seats.

Mental Omega ships its multiplayer maps as loose files: ``MapsMO/Standard``
for the ordinary pool, ``MapsMO/Challenge`` for the scripted fights, each map
beside a ``.png`` the client shows while choosing. What a launcher needs off
one is small -- a name, how many houses fit, where they start, whether there
is a preview -- but the fields are not at the top of the file: ``[Basic]``
sits after the terrain, three thousand lines into a challenge map. There is
no cheap way to read one, so seven hundred of them are read once and the
answers kept in a cache keyed on each file's size and timestamp.
"""

from dataclasses import dataclass
from pathlib import Path
import json
import logging
import re

from randomizer.core.diagnostics import event as log_event
from randomizer.core.paths import APP_DIR, GAME_ROOT


MAPS_DIR = GAME_ROOT / 'MapsMO'
STANDARD_POOL_DIR = MAPS_DIR / 'Standard'
CHALLENGE_POOL_DIR = MAPS_DIR / 'Challenge'
COOPERATIVE_POOL_DIR = MAPS_DIR / 'Cooperative'
MAP_CACHE_PATH = APP_DIR / 'skirmish_maps_cache.json'
MAP_CACHE_VERSION = 3

# The mode an ordinary battle is fought under. A map that does not offer it
# is a different game -- king of the hill, oil control, a map with no ore on
# it at all -- and the shop's economy assumes the ordinary one.
STANDARD_MODE = 'standard'

# How many starting points the engine reads. Waypoints past these are
# scenery: reinforcement drops, camera moves, script markers.
MAX_STARTS = 8

_NAME = re.compile(r'^Name=(.*)$', re.M)
_MAX_PLAYER = re.compile(r'^MaxPlayer=(\d+)', re.M)
_MIN_PLAYER = re.compile(r'^MinPlayer=(\d+)', re.M)
_GAME_MODE = re.compile(r'^GameMode=(.*)$', re.M)
_WAYPOINT = re.compile(r'^Waypoint(\d+)=(\d+),(\d+)', re.M)
_STARTING_POINTS = re.compile(r'^NumberStartingPoints=(\d+)', re.M)
_SPAWN_CELL = re.compile(r'^(\d+)=(\d+)\s*$', re.M)


def _section(text, name):
    """Return one INI section's body.

    Read from the section rather than from the file: a challenge map carries
    unit overrides with ``Name=`` keys of their own, and the first of those
    is three thousand lines above the ``[Basic]`` the map is described in.
    """
    header = re.search(rf'^\[{name}\]\s*$', text, re.M)
    if not header:
        return ''
    rest = text[header.end():]
    following = re.search(r'^\[', rest, re.M)
    return rest[:following.start()] if following else rest


def _spawn_cells(text):
    """Return the starting cells, in the order the engine numbers them.

    ``[Waypoints]`` is what the engine places houses on, and it stores a
    cell as one number: ``211133`` is row 211, column 133. The ``[Header]``
    carries the same points transformed for the client's preview picture,
    which is why they look different and why they are not read here.

    Numbering starts at zero and has to be unbroken, because a spawn file
    names a starting point by that index. A map that skips one is left
    without coordinates rather than described wrongly.
    """
    found = {}
    for index, cell in _SPAWN_CELL.findall(text):
        index, cell = int(index), int(cell)
        if 0 <= index < MAX_STARTS:
            found[index] = (cell % 1000, cell // 1000)
    ordered = []
    for index in range(MAX_STARTS):
        if index not in found:
            break
        ordered.append(found[index])
    return tuple(ordered)


@dataclass(frozen=True)
class SkirmishMap:
    path: Path
    name: str
    players: int
    minimum_players: int
    starts: int
    game_modes: tuple[str, ...]
    preview: Path | None
    spawns: tuple[tuple[int, int], ...] = ()

    @property
    def standard(self):
        """Whether this map offers the mode an ordinary battle is fought in."""
        return any(
            str(mode).strip().lower() == STANDARD_MODE
            for mode in self.game_modes
        )

    @property
    def seats(self):
        """How many houses this map can actually place.

        ``MaxPlayer`` is what the map claims and the starting waypoints are
        what it has; a house with nowhere to start is placed by the engine
        wherever it likes, which on a two-start map means inside someone.
        """
        return min(self.players, self.starts)

    def to_dict(self):
        return {
            'name': self.name,
            'players': self.players,
            'minimum_players': self.minimum_players,
            'starts': self.starts,
            'game_modes': list(self.game_modes),
            'preview': self.preview.name if self.preview else None,
            'spawns': [[x, y] for x, y in self.spawns],
        }


def _read_map(path):
    whole = path.read_text(encoding='utf-8', errors='ignore')
    text = _section(whole, 'Basic')
    header = _section(whole, 'Header') or whole
    name = _NAME.search(text)
    players = _MAX_PLAYER.search(text)
    minimum = _MIN_PLAYER.search(text)
    modes = _GAME_MODE.search(text)
    # The header states how many starting points the map has. Where it does
    # not, its first eight waypoints are the starting positions -- listed
    # from one, and ``0,0`` for a slot the map does not use.
    declared = _STARTING_POINTS.search(header)
    starts = int(declared.group(1)) if declared else sum(
        1 for index, x, y in _WAYPOINT.findall(header)
        if 1 <= int(index) <= 8 and (int(x) or int(y))
    )
    preview = path.with_suffix('.png')
    return SkirmishMap(
        path=path,
        name=((name.group(1).strip() if name else '') or path.stem),
        players=int(players.group(1)) if players else 0,
        minimum_players=int(minimum.group(1)) if minimum else 0,
        starts=starts,
        game_modes=tuple(
            mode.strip() for mode in (
                modes.group(1) if modes else ''
            ).split(',') if mode.strip()
        ),
        preview=preview if preview.is_file() else None,
        spawns=_spawn_cells(_section(whole, 'Waypoints')),
    )


def _cache_key(path):
    stat = path.stat()
    return f'{stat.st_size}:{int(stat.st_mtime)}'


def _load_cache():
    if not MAP_CACHE_PATH.is_file():
        return {}
    try:
        document = json.loads(MAP_CACHE_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if document.get('version') != MAP_CACHE_VERSION:
        return {}
    entries = document.get('maps')
    return entries if isinstance(entries, dict) else {}


def _save_cache(entries):
    try:
        MAP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        MAP_CACHE_PATH.write_text(
            json.dumps(
                {'version': MAP_CACHE_VERSION, 'maps': entries},
                indent=None,
            ),
            encoding='utf-8',
        )
    except OSError as exc:
        # The cache is an optimisation. Losing it costs one slow scan.
        log_event(
            'skirmish_map_cache_write_failed',
            level=logging.WARNING,
            error=str(exc),
        )


def read_map_pool(directory, *, cache=True):
    """Return every map in one folder, reading only what has changed."""
    directory = Path(directory)
    if not directory.is_dir():
        return ()
    stored = _load_cache() if cache else {}
    entries = {}
    maps = []
    changed = False
    for path in sorted(directory.glob('*.map')):
        key = str(path)
        try:
            stamp = _cache_key(path)
        except OSError:
            continue
        cached = stored.get(key)
        if cached and cached.get('stamp') == stamp:
            preview = path.with_suffix('.png')
            maps.append(SkirmishMap(
                path=path,
                name=str(cached.get('name') or path.stem),
                players=int(cached.get('players') or 0),
                minimum_players=int(cached.get('minimum_players') or 0),
                starts=int(cached.get('starts') or 0),
                game_modes=tuple(cached.get('game_modes') or ()),
                preview=preview if cached.get('preview') else None,
                spawns=tuple(
                    (int(x), int(y)) for x, y in (cached.get('spawns') or ())
                ),
            ))
            entries[key] = cached
            continue
        try:
            parsed = _read_map(path)
        except OSError:
            continue
        changed = True
        maps.append(parsed)
        entries[key] = {'stamp': stamp, **parsed.to_dict()}
    if cache and (changed or entries != stored):
        merged = dict(stored)
        merged.update(entries)
        # Maps the player deleted stop being described.
        for key in tuple(merged):
            if key.startswith(str(directory)) and key not in entries:
                merged.pop(key)
        _save_cache(merged)
    return tuple(maps)


def standard_maps(pool):
    """Return the maps of a pool that declare the ordinary game mode.

    The Standard folder is a folder, not a mode: eighty of the maps in it
    are king of the hill, fortress, islands, oil control or land grab, and
    a few of those carry no ore at all. Fought as an ordinary battle they
    are a run with nothing to earn, so they are not offered.
    """
    return tuple(entry for entry in pool if entry.standard)


def skirmish_map_pool(*, cache=True):
    """The ordinary multiplayer pool: what a normal battle is played on."""
    return standard_maps(read_map_pool(STANDARD_POOL_DIR, cache=cache))


def challenge_map_pool(*, cache=True):
    """The scripted fights a run meets every fifth battle."""
    return read_map_pool(CHALLENGE_POOL_DIR, cache=cache)


def maps_for_players(pool, players):
    """Return the maps that seat exactly this many houses or more."""
    players = int(players)
    return tuple(
        entry for entry in pool
        if entry.seats >= players and entry.minimum_players <= players
    )


def summarize_map_pools(*, cache=True):
    """Report the pools for the self-check."""
    summary = {}
    for label, pool in (
        ('standard', skirmish_map_pool(cache=cache)),
        ('challenge', challenge_map_pool(cache=cache)),
    ):
        summary[label] = {
            'maps': len(pool),
            'with_preview': sum(1 for entry in pool if entry.preview),
            'seats': {
                players: len(maps_for_players(pool, players))
                for players in (2, 3, 4, 5, 6, 8)
            },
        }
    return summary


def map_by_relative_path(relative, *, cache=True):
    """Return the map a run stored, or ``None`` if it is not installed.

    Runs store ``Standard/northsea.map`` rather than a full path, so a run
    survives the game being moved. Nothing is raised for a map that has
    since been deleted: the offer holding it simply cannot be played.
    """
    wanted = str(relative or '').strip().replace('\\', '/')
    if not wanted:
        return None
    path = MAPS_DIR / wanted
    # Read the whole folder, not the pool battles are dealt from. A run
    # already holding an offer on a map the pool has since stopped dealing
    # should still be able to play it; refusing here would read as the map
    # having been uninstalled.
    for pool in (
        read_map_pool(STANDARD_POOL_DIR, cache=cache),
        challenge_map_pool(cache=cache),
    ):
        for entry in pool:
            if entry.path == path:
                return entry
    return None
