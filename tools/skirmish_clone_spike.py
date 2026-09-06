"""Find out whether a skirmish can give one house its own private units.

A unit upgrade written the obvious way -- ``[GGI] Speed=8`` in the map --
reaches every house fielding that unit, because a TechnoType is global. This
asks the one question the whole per-house design rests on: can a skirmish
seat a player on a country nobody else uses, and give that country a private
copy of a unit that only it can build?

Three things are under test at once, because they only fail together:

1. **The private seat.** The player picks a country; the game seats them on a
   different one whose section is overwritten in the map to be a copy of the
   chosen country. Mental Omega's own campaign maps rewrite country sections
   this way -- ABMIND.MAP sets ``[Europeans] ParentCountry=UnitedStates`` --
   so this is a thing the engine already does, not an invention. No new
   country is added, which keeps the spawner's country index untouched.
2. **The ownership pass.** A seat country only works if every buildable type
   treats it exactly as it treats the country it stands for: present in the
   same ``Owner``/``RequiredHouses``/``FactoryOwners`` lists, absent from the
   ones it is not in. Around 215 sections, generated.
3. **The clone.** One unit, copied under a new ID with a buff applied,
   ``RequiredHouses`` set to the seat country, and the original forbidden to
   that seat so the sidebar shows one cameo rather than two.

The line-up is deliberately the case the current mode forbids: **the ally
plays the same country the player chose.** If that works, "oyuncu ile
muttefik ayni ulkeyi secemez" is gone.

    python tools/skirmish_clone_spike.py --dry-run   # build it, write nothing
    python tools/skirmish_clone_spike.py             # write and launch

What to watch for is printed at the end of a real run.
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

from skirmish_spike import pick_map, resolve_game_root  # noqa: E402


# What the player picked, and the seat they are given. The seat is a country
# no other house in this battle uses; its section becomes a copy of the
# chosen one, so the player fields the army they asked for.
CHOSEN_COUNTRY = 'UnitedStates'
SEAT_COUNTRY = 'Guild3'
# The same country the player chose, on purpose: this is the case the
# unique-country rule would have forbidden.
ALLY_COUNTRY = 'UnitedStates'
ENEMY_COUNTRIES = ('PsiCorps', 'Guild1')
COLORS = (0, 2, 4, 6)
AI_HANDICAP = 1  # Medium: the spike is about production, not about winning.

# One unit, one buff, large enough to see without a stopwatch.
CLONE_SOURCE = 'GGI'
CLONE_ID = 'GGIRZ'
CLONE_BUFF = 'speed'
CLONE_STACKS = 5

# Every key whose value is a list of countries. A seat country belongs in
# each one exactly where the country it stands for belongs. The two kinds
# are kept apart because emptying one is safe and emptying the other is not:
# ``ForbiddenHouses=none`` is Mental Omega's own idiom, ``Owner=none`` names
# a country that does not exist.
POSITIVE_HOUSE_KEYS = (
    'Owner',
    'RequiredHouses',
    'FactoryOwners',
    'SW.RequiredHouses',
)
NEGATIVE_HOUSE_KEYS = (
    'ForbiddenHouses',
    'FactoryOwners.Forbidden',
)
HOUSE_LIST_KEYS = POSITIVE_HOUSE_KEYS + NEGATIVE_HOUSE_KEYS
TYPE_LIST_BY_CATEGORY = {
    'infantry': 'InfantryTypes',
    'units': 'VehicleTypes',
    'aircraft': 'AircraftTypes',
    'defenses': 'BuildingTypes',
    'special_buildings': 'BuildingTypes',
}
# Clones are registered from here upwards, never renumbering what the rules
# already list: a script argument can be an index into these lists.
TYPE_LIST_KEY_START = 20000


def items(value):
    return [item.strip() for item in str(value or '').split(',') if item.strip()]


def country_index(countries, name):
    for index, country in enumerate(countries):
        if country.lower() == name.lower():
            return index
    raise SystemExit(f'{name} is not an installed country')


def seat_country_section(rules, chosen, seat):
    """Return the seat's country section, rewritten as a copy of the chosen.

    Everything the country is -- side, colour, prefix and suffix for art and
    voices, the Ares multipliers, the AI's power plant, the paradrop -- comes
    from the country the player asked for. What stays the seat's own is its
    place in the list: ``ListIndex`` is what the spawner counts with.
    """
    values = dict(rules.get(chosen) or {})
    if not values:
        raise SystemExit(f'No [{chosen}] section in the installed rules')
    seat_values = rules.get(seat) or {}
    for key in seat_values:
        if key.lower() == 'listindex':
            values[key] = seat_values[key]
    return values


def sides_section(rules, chosen, seat):
    """Return the whole of ``[Sides]``, with the seat moved to its new side.

    Every side is written, not only the two that change. The engine rebuilds
    its side list from what the map says and does not merge the rest back in:
    a map naming two sides leaves the game with two sides, which the debug
    log states plainly at "Processing sides".
    """
    sides = dict(rules.get('Sides') or {})
    updated = {}
    for side, value in sides.items():
        members = [
            item for item in items(value)
            if item.lower() != seat.lower()
        ]
        if any(item.lower() == chosen.lower() for item in members):
            members.append(seat)
        updated[side] = ','.join(members)
    return updated


def ownership_pass(rules, chosen, seat):
    """Return the edits that make the seat country a stand-in for the chosen.

    The rule is one line: in every list of countries, the seat is present
    exactly where the country it stands for is present. Both directions
    matter -- without the removals the player could build the seat's old
    faction, which is a different army from the one they chose.
    """
    edits = {}
    added = removed = forbidden = 0
    for section, values in rules.items():
        forbid_instead = False
        for key in HOUSE_LIST_KEYS:
            actual = next(
                (name for name in values if name.lower() == key.lower()), None
            )
            if actual is None:
                continue
            names = items(values[actual])
            lowered = [name.lower() for name in names]
            has_chosen = chosen.lower() in lowered
            has_seat = seat.lower() in lowered
            if has_chosen == has_seat:
                continue
            if has_chosen:
                names.append(seat)
                added += 1
            elif key in POSITIVE_HOUSE_KEYS and len(names) == 1:
                # The seat is this type's only owner -- a unit belonging to
                # the faction whose slot the seat came from. Removing it
                # would leave a list naming nobody, so the seat is shut out
                # the way Mental Omega shuts a country out of a type it
                # otherwise qualifies for.
                forbid_instead = True
                continue
            else:
                names = [
                    name for name in names if name.lower() != seat.lower()
                ]
                removed += 1
            edits.setdefault(section, {})[actual] = (
                ','.join(names) if names else 'none'
            )
        if forbid_instead:
            existing = edits.get(section, {}).get('ForbiddenHouses')
            if existing is None:
                existing = next(
                    (
                        values[name] for name in values
                        if name.lower() == 'forbiddenhouses'
                    ),
                    '',
                )
            names = [
                name for name in items(existing)
                if name.lower() not in {'none', '<none>'}
            ]
            if seat not in names:
                names.append(seat)
            edits.setdefault(section, {})['ForbiddenHouses'] = ','.join(names)
            forbidden += 1
    return edits, added, removed, forbidden


def clone_sections(rules, seat, source, clone_id, buff_type, stacks):
    """Return the private copy of one unit, and the original's new gate."""
    from randomizer.maps.buff_values import apply_unit_buff_value
    from randomizer.rewards.catalogue import BUFF_TARGETS

    body = dict(rules.get(source) or {})
    if not body:
        raise SystemExit(f'No [{source}] section in the installed rules')
    target = BUFF_TARGETS.get(source) or {}
    if not target:
        raise SystemExit(f'{source} is not in the buff catalogue')
    before = dict(body)
    if not apply_unit_buff_value(body, target, buff_type, stacks):
        raise SystemExit(f'{buff_type} does nothing to {source} here')
    changed = {
        key: value for key, value in body.items() if before.get(key) != value
    }
    # Art follows the source. A clone with no Image of its own would send the
    # engine looking for art under an ID no art file has.
    if not any(key.lower() == 'image' for key in body):
        body['Image'] = source
    owners = items(next(
        (body[key] for key in list(body) if key.lower() == 'owner'), ''
    ))
    if seat not in owners:
        owners.append(seat)
    for key in list(body):
        if key.lower() in {'owner', 'requiredhouses', 'forbiddenhouses'}:
            body.pop(key)
    body['Owner'] = ','.join(owners)
    # The positive gate: this type belongs to the seat and to nobody else.
    body['RequiredHouses'] = seat

    original_forbidden = items(next(
        (
            rules[source][key] for key in rules.get(source, {})
            if key.lower() == 'forbiddenhouses'
        ),
        '',
    ))
    original_forbidden = [
        name for name in original_forbidden if name.lower() not in {'none'}
    ]
    if seat not in original_forbidden:
        original_forbidden.append(seat)

    category = str(target.get('category') or '')
    list_section = TYPE_LIST_BY_CATEGORY.get(category)
    if not list_section:
        raise SystemExit(f'{source} has no type list ({category})')
    registered = set(rules.get(list_section, {}))
    key = TYPE_LIST_KEY_START
    while str(key) in registered:
        key += 1
    return (
        {
            clone_id: body,
            source: {'ForbiddenHouses': ','.join(original_forbidden)},
            list_section: {str(key): clone_id},
        },
        changed,
    )


def build_map_code(
    rules, *, rewrite_sides=True, own_units=True, clone=True,
):
    """Return everything this battle writes into the map, section by section."""
    code = {}
    code[SEAT_COUNTRY] = seat_country_section(
        rules, CHOSEN_COUNTRY, SEAT_COUNTRY
    )
    # Whether [Sides] needs rewriting at all is under test: the country's
    # own Side= key may already be what seats the player, and a map-level
    # [Sides] replaces the engine's whole list rather than adding to it.
    sides = sides_section(rules, CHOSEN_COUNTRY, SEAT_COUNTRY)
    if sides and rewrite_sides:
        code['Sides'] = sides
    # Each of the three parts can be left out on its own, which is how a
    # match that misbehaves says which part misbehaved.
    ownership, added, removed, forbidden = (
        ownership_pass(rules, CHOSEN_COUNTRY, SEAT_COUNTRY) if own_units
        else ({}, 0, 0, 0)
    )
    for section, values in ownership.items():
        code.setdefault(section, {}).update(values)
    changed = {}
    if clone:
        clones, changed = clone_sections(
            rules, SEAT_COUNTRY, CLONE_SOURCE, CLONE_ID, CLONE_BUFF,
            CLONE_STACKS,
        )
        for section, values in clones.items():
            code.setdefault(section, {}).update(values)
    return code, {
        'rewrote_sides': bool(sides and rewrite_sides),
        'ownership_sections': len(ownership),
        'added': added,
        'removed': removed,
        'forbidden': forbidden,
        'clone_changed': changed,
        'sides': sides,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--seed', type=int, default=24680)
    parser.add_argument('--map', type=Path, default=None)
    parser.add_argument('--game-root', default=None)
    parser.add_argument(
        '--no-sides', action='store_true',
        help='leave [Sides] alone and let the country section seat the player',
    )
    parser.add_argument(
        '--no-ownership', action='store_true',
        help='skip the 215-section ownership pass',
    )
    parser.add_argument(
        '--no-clone', action='store_true',
        help='skip the cloned unit and its type registration',
    )
    args = parser.parse_args(argv)

    game_root = resolve_game_root(args.game_root)
    os.environ['MO_RANDOMIZER_GAME_ROOT'] = str(game_root)
    print(f'game folder: {game_root}')

    from randomizer.ui.cameos import installed_rules_registry

    _superweapons, rules = installed_rules_registry(synchronous=True)
    countries = [
        str(value) for _key, value in sorted(
            (rules.get('Countries') or {}).items(), key=lambda kv: int(kv[0])
        )
    ]
    seat_index = country_index(countries, SEAT_COUNTRY)
    print(
        f'seat: {SEAT_COUNTRY} (index {seat_index}) '
        f'rewritten as a copy of {CHOSEN_COUNTRY}'
    )
    print(f'ally: {ALLY_COUNTRY}   enemies: {", ".join(ENEMY_COUNTRIES)}')

    code, report = build_map_code(
        rules,
        rewrite_sides=not args.no_sides,
        own_units=not args.no_ownership,
        clone=not args.no_clone,
    )
    print()
    print(f'ownership pass: {report["ownership_sections"]} sections, '
          f'{report["added"]} added, {report["removed"]} removed, '
          f'{report["forbidden"]} shut out')
    print(
        f'[Sides]: '
        + (str(report['sides']) if report['rewrote_sides'] else 'left alone')
    )
    if CLONE_ID in code:
        print(f'clone: [{CLONE_ID}] from {CLONE_SOURCE} '
              f'{CLONE_BUFF} x{CLONE_STACKS} -> {report["clone_changed"]}')
        print(f'      Owner={code[CLONE_ID]["Owner"]}')
        print(f'      RequiredHouses={code[CLONE_ID]["RequiredHouses"]}')
        print(f'      {CLONE_SOURCE} ForbiddenHouses='
              f'{code[CLONE_SOURCE]["ForbiddenHouses"]}')
    else:
        print('clone: none')
    print(f'map code: {len(code)} sections, '
          f'{sum(len(values) for values in code.values())} keys')

    wanted = 2 + len(ENEMY_COUNTRIES)
    pool = game_root / 'MapsMO' / 'Standard'
    chosen_map = (
        {'path': args.map, 'name': args.map.stem, 'players': wanted}
        if args.map else pick_map(pool, wanted)
    )
    if not chosen_map:
        raise SystemExit(f'No map in {pool} seats {wanted} players.')
    print(f'map: {chosen_map["name"]} ({chosen_map["path"].name})')

    if args.dry_run:
        scratch = Path(
            os.environ.get('TEMP', '.')
        ) / 'skirmish_clone_spike_map.ini'
        shutil.copy2(chosen_map['path'], scratch)
        from randomizer.skirmish.mapfile import merge_into_map

        from randomizer.skirmish.options import merge_game_options
        from randomizer.skirmish.spawn import DEFAULT_MATCH_OPTIONS

        applied = merge_into_map(scratch, code)
        files, option_keys = merge_game_options(scratch, DEFAULT_MATCH_OPTIONS)
        print(f'\ndry run: {applied} keys merged into {scratch}')
        print(f'game options: {files} files, {option_keys} keys')
        return 0

    from randomizer.skirmish.mapfile import merge_into_map
    from randomizer.skirmish.spawn import (
        SkirmishHouse,
        skirmish_spawn_ini_text,
        write_skirmish_spawn_ini,
    )

    spawnmap = game_root / 'spawnmap.ini'
    spawn = game_root / 'spawn.ini'
    for path in (spawn, spawnmap):
        if path.is_file():
            shutil.copy2(path, path.with_suffix(path.suffix + '.pre-spike'))
    shutil.copy2(chosen_map['path'], spawnmap)
    applied = merge_into_map(spawnmap, code)
    # What the client merges for the options this match declares. Writing
    # StolenTech=True without this is a match whose spies cannot infiltrate.
    from randomizer.skirmish.options import merge_game_options
    from randomizer.skirmish.spawn import DEFAULT_MATCH_OPTIONS

    files, option_keys = merge_game_options(spawnmap, DEFAULT_MATCH_OPTIONS)
    print(f'wrote {spawnmap.name} with {applied} merged keys')
    print(f'game options: {files} files, {option_keys} keys')

    houses = [SkirmishHouse(
        country=country_index(countries, ALLY_COUNTRY), color=COLORS[1],
        friendly=True, handicap=AI_HANDICAP,
    )]
    for index, enemy in enumerate(ENEMY_COUNTRIES):
        houses.append(SkirmishHouse(
            country=country_index(countries, enemy), color=COLORS[2 + index],
            friendly=False, handicap=AI_HANDICAP,
        ))
    text = skirmish_spawn_ini_text(
        map_name=chosen_map['name'],
        player_country=seat_index,
        player_color=COLORS[0],
        houses=houses,
        seed=args.seed,
    )
    write_skirmish_spawn_ini(spawn, text)
    print(f'wrote {spawn.name} ({len(text.splitlines())} lines)')

    from randomizer.application.launch_controller import (
        windows_syringe_command_line,
    )

    command = windows_syringe_command_line([
        str(game_root / 'Syringe.exe'),
        'gamemd.exe', '-SPAWN', '-CD', '-LOG',
    ])
    print('launching:', command)
    subprocess.Popen(command, cwd=str(game_root))
    print()
    print('Watch for five things:')
    print('  1. the match opens and your MCV arrives and deploys')
    print(f'  2. the sidebar shows ONE {CLONE_SOURCE} cameo, not two')
    print(f'  3. the one you build is the fast one ({CLONE_BUFF} x{CLONE_STACKS})')
    print('  4. your ally plays the same country you did, and builds normally')
    print('  5. both enemies build and attack normally')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
