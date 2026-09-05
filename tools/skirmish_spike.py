"""Start one hand-built skirmish, to find out whether the launcher can.

Everything in the proposed Skirmish Shop mode rests on one thing the launcher
has never done: begin a skirmish rather than a campaign mission. The spawn.ini
it writes today says ``IsSinglePlayer=Yes`` with a single ``Side`` and no other
players at all. A skirmish needs a player, an ally and several computer
opponents, each with a country, a colour, a start position and an alliance.

So this is that and nothing else -- no mode, no economy, no interface. One
fixed map, one fixed line-up, launched the way the launcher launches. If the
match opens with the ally fighting beside you and the enemies against you, the
rest of the mode is engineering. If it does not, there is no mode.

The format comes from the CnCNet client's own spawn writer, and the game
folder corroborates it: the 320 KB spawnmap.ini sitting there is
MapsMO/Standard/northsea.map, staged under that name by the client the last
time a skirmish was played. So a skirmish is: copy the chosen map to
spawnmap.ini, and point Scenario at it.

Computer players are not ``[OtherN]`` sections -- those are for remote humans.
They are rows in ``[HouseCountries]``, ``[HouseColors]``, ``[HouseHandicaps]``
and ``[SpawnLocations]``, keyed ``MultiN``, numbered after the humans.

    python tools/skirmish_spike.py --dry-run     # show the files, write nothing
    python tools/skirmish_spike.py               # write and launch
    python tools/skirmish_spike.py --alliance-offset 11
    python tools/skirmish_spike.py --game-root "D:/.../Red Alert II MO"

The game folder is found on its own: the installed launcher records it in the
install.txt beside its player data. Only pass --game-root for an installation
it has never run against.

The last flag is the one genuinely uncertain value. The client writes an ally
id as ``id - 1`` for most games and ``id + 11`` for Red Alert, and which of
those Mental Omega counts as is not something to guess: a wrong alliance is
visible in the first ten seconds, because the ally shoots at you.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Nothing under randomizer is imported at module level: core.paths reads the
# game folder once, at import, and this script has to choose that folder
# first. Every such import happens inside a function, after main() sets it.


def is_installation(path):
    return bool(path) and (Path(path) / 'MapsMO' / 'Standard').is_dir()


def resolve_game_root(override=None):
    """Return the installation to launch, without needing to be told.

    Run from a source checkout, the launcher's own GAME_ROOT is the checkout's
    parent: it only means the game folder when it is running inside one. The
    installed launcher already records where its game is, in the install.txt
    beside its player data, so ask that before asking a person.

    An explicit ``--game-root`` is authoritative. A path that turns out to be
    wrong is a mistake to report, not one to quietly route around.
    """
    if override:
        if not is_installation(override):
            raise SystemExit(f'--game-root has no MapsMO/Standard: {override}')
        return Path(override)
    candidates = []
    configured = os.environ.get('MO_RANDOMIZER_GAME_ROOT', '').strip()
    if configured:
        candidates.append(Path(configured))
    local = os.environ.get('LOCALAPPDATA', '')
    if local:
        for marker in sorted(
            (Path(local) / 'MentalOmegaRandomizer').glob('*/install.txt')
        ):
            try:
                recorded = marker.read_text(encoding='utf-8').strip()
            except OSError:
                continue
            if recorded:
                candidates.append(Path(recorded))
    candidates.append(Path(__file__).resolve().parents[2])
    for candidate in candidates:
        if is_installation(candidate):
            return candidate
    looked = '\n'.join(f'  {candidate}' for candidate in candidates)
    raise SystemExit(
        'No Mental Omega installation with MapsMO/Standard found.\n'
        f'Looked in:\n{looked}\n'
        'Pass --game-root "<game folder>".'
    )

# [Countries] order in the installed rules, which is what HouseCountries
# indexes. Read from the game at runtime rather than trusted from here; this
# is the expected shape, and the script checks it.
EXPECTED_COUNTRIES = (
    'UnitedStates', 'Europeans', 'Pacific',      # Allies
    'USSR', 'Latin', 'Chinese',                  # Soviets
    'PsiCorps', 'ScorpionCell', 'Headquaters',   # Epsilon
    'Guild1', 'Guild2', 'Guild3',                # Foehn
)

# The line-up under test: a four-player map, the player and one ally against
# two computer opponents, each faction represented once so a mistake in the
# country index is obvious on screen rather than subtle.
PLAYER_COUNTRY = 0    # UnitedStates, Allies
ALLY_COUNTRY = 3      # USSR, Soviets
ENEMY_COUNTRIES = (6, 9)  # PsiCorps and Guild1: Epsilon and Foehn
COLORS = (0, 2, 4, 6)
AI_HANDICAP = 2       # the client's own SkirmishSettings.ini uses 2 for Hard


def installed_countries():
    """Return the country list the game will index, in its own order."""
    from randomizer.ui.cameos import installed_rules_registry

    _superweapons, sections = installed_rules_registry(synchronous=True)
    countries = sections.get('Countries') or {}
    return [
        str(countries[key])
        for key in sorted(countries, key=lambda item: int(item))
    ]


def pick_map(pool, wanted_players):
    """Return a map with room for everyone, and its preview if it has one."""
    import re

    for path in sorted(pool.glob('*.map')):
        text = path.read_text(encoding='utf-8', errors='ignore')
        match = re.search(r'^MaxPlayer=(\d+)', text, re.M)
        if not match or int(match.group(1)) < wanted_players:
            continue
        waypoints = re.findall(r'^Waypoint(\d+)=', text, re.M)
        if len(waypoints) < wanted_players:
            continue
        name = re.search(r'^Name=(.*)$', text, re.M)
        return {
            'path': path,
            'name': name.group(1).strip() if name else path.stem,
            'players': int(match.group(1)),
            'preview': (
                path.with_suffix('.png')
                if path.with_suffix('.png').is_file() else None
            ),
        }
    return None


def spawn_ini_text(chosen, alliance_offset, seed):
    """Return a complete skirmish spawn.ini.

    Multi numbering runs over every house in one sequence: the player is
    Multi1, the ally Multi2, the computers follow. Alliances are written from
    each house's point of view, which is why the player and the ally each get
    a section naming the other.
    """
    houses = [
        {'multi': 1, 'country': PLAYER_COUNTRY, 'color': COLORS[0], 'ai': False},
        {'multi': 2, 'country': ALLY_COUNTRY, 'color': COLORS[1], 'ai': True},
    ]
    for index, country in enumerate(ENEMY_COUNTRIES):
        houses.append({
            'multi': 3 + index,
            'country': country,
            'color': COLORS[2 + index],
            'ai': True,
        })
    teams = {'friendly': [1, 2], 'hostile': [house['multi'] for house in houses[2:]]}

    lines = [
        '[Settings]',
        'Scenario=spawnmap.ini',
        'Name=Commander',
        f'Side={PLAYER_COUNTRY}',
        f'Color={COLORS[0]}',
        'IsSpectator=No',
        'PlayerCount=1',
        f'AIPlayers={sum(1 for house in houses if house["ai"])}',
        f'Seed={seed}',
        'GameSpeed=4',
        'Credits=10000',
        'UnitCount=10',
        'ShortGame=True',
        'Superweapons=True',
        'BuildOffAlly=True',
        'MCVRedeploy=True',
        'Bases=True',
        'Crates=False',
        'GameMode=1',
        'IsSinglePlayer=Yes',
        'Firestorm=False',
        'SidebarHack=False',
        'Difficulty=1',
        'CampDifficulty=1',
        'DifficultyModeHuman=1',
        'DifficultyModeComputer=1',
    ]

    def table(section, value_for):
        lines.append('')
        lines.append(f'[{section}]')
        for house in houses:
            value = value_for(house)
            if value is not None:
                lines.append(f'Multi{house["multi"]}={value}')

    table('HouseCountries', lambda house: house['country'])
    table('HouseColors', lambda house: house['color'])
    # Only computer players take a handicap; a row for the human confuses it.
    table('HouseHandicaps', lambda house: AI_HANDICAP if house['ai'] else None)
    # Start positions are waypoint indexes, one per house, all distinct.
    table('SpawnLocations', lambda house: house['multi'] - 1)

    ordinals = ('One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven')
    for team in teams.values():
        for multi in team:
            allies = [other for other in team if other != multi]
            if not allies:
                continue
            lines.append('')
            lines.append(f'[Multi{multi}_Alliances]')
            for index, ally in enumerate(allies):
                lines.append(f'HouseAlly{ordinals[index]}={ally + alliance_offset}')
    return '\r\n'.join(lines) + '\r\n'


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument(
        '--alliance-offset', type=int, default=-1,
        help='ally id offset: -1 for most games, 11 for Red Alert.',
    )
    parser.add_argument('--seed', type=int, default=12345)
    parser.add_argument('--map', type=Path, default=None)
    parser.add_argument('--game-root', default=None)
    args = parser.parse_args(argv)

    game_root = resolve_game_root(args.game_root)
    print(f'game folder: {game_root}')
    # randomizer.core.paths reads this once, and every rules lookup follows
    # from it, so it has to be set before anything under randomizer is
    # imported -- which is why installed_countries() imports lazily.
    os.environ['MO_RANDOMIZER_GAME_ROOT'] = str(game_root)
    pool = game_root / 'MapsMO' / 'Standard'

    countries = installed_countries()
    print(f'installed countries: {len(countries)}')
    for index in (PLAYER_COUNTRY, ALLY_COUNTRY, *ENEMY_COUNTRIES):
        actual = countries[index] if index < len(countries) else '(missing)'
        expected = EXPECTED_COUNTRIES[index]
        flag = 'ok' if actual == expected else f'MISMATCH, expected {expected}'
        print(f'   {index:2} {actual:14} {flag}')

    wanted = 2 + len(ENEMY_COUNTRIES)
    if args.map:
        chosen = {'path': args.map, 'name': args.map.stem, 'players': wanted,
                  'preview': args.map.with_suffix('.png')}
    else:
        chosen = pick_map(pool, wanted)
    if not chosen:
        raise SystemExit(f'No map in {pool} seats {wanted} players.')
    print(f'map: {chosen["name"]} ({chosen["players"]} players) {chosen["path"].name}')
    print(f'preview: {chosen["preview"].name if chosen["preview"] else "(none)"}')

    text = spawn_ini_text(chosen, args.alliance_offset, args.seed)
    spawnmap = game_root / 'spawnmap.ini'
    spawn = game_root / 'spawn.ini'
    if args.dry_run:
        print('\n--- spawn.ini (not written) ---')
        print(text)
        return 0

    # The launcher's own campaign spawn.ini is about to be replaced. Keep it:
    # this is someone's machine, and a spike is not a reason to lose a
    # half-finished mission launch.
    for path in (spawn, spawnmap):
        if path.is_file():
            shutil.copy2(path, path.with_suffix(path.suffix + '.pre-spike'))
    shutil.copy2(chosen['path'], spawnmap)
    spawn.write_text(text, encoding='utf-8')
    print(f'wrote {spawnmap.name} from {chosen["path"].name}')
    print(f'wrote {spawn.name} ({len(text.splitlines())} lines)')

    # Syringe parses its own raw command line and refuses to run unless the
    # host executable is quoted -- "Syringe cannot be run just like that."
    # Handing Popen a list loses those quotes whenever the name has no spaces,
    # so the launcher keeps a builder for exactly this boundary and this uses
    # it rather than growing a second answer that can drift from the first.
    from randomizer.application.launch_controller import (
        windows_syringe_command_line,
    )

    launcher = game_root / 'Syringe.exe'
    argv = [str(launcher), 'gamemd.exe', '-SPAWN', '-CD', '-SPEEDCONTROL', '-LOG']
    command = windows_syringe_command_line(argv)
    print('launching:', command)
    subprocess.Popen(command, cwd=str(game_root))
    print()
    print('Watch for three things:')
    print('  1. the match opens at all')
    print('  2. the Soviet ally fights beside you, not against you')
    print('  3. two enemies, one Epsilon and one Foehn')
    print('If the ally is hostile, rerun with --alliance-offset 11.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
