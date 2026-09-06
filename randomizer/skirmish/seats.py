"""Seating a house on a country nobody else in the battle is using.

A private copy of a unit is gated by ``RequiredHouses=<country>``, so the
gate is only private while no other house plays that country. Reserving one
is cheaper and safer than inventing a fifteenth country: the spawner's
country index stays what the installed rules say it is, and Mental Omega's
own campaign maps already rewrite country sections from inside a map --
ABMIND.MAP sets ``[Europeans] ParentCountry=UnitedStates``.

So the player is seated on a spare country whose section is overwritten to
be a copy of the country they chose, and every list of countries in the
rules is taught to treat the seat exactly as it treats the country it stands
for. What the player fields is the army they picked; what the engine sees is
a country only they are playing.

Two things this pays for: the ally may now play the very country the player
chose, and a challenge's fixed armies can no longer collide with the gate.
"""

from randomizer.core.diagnostics import event as log_event

from .mapfile import merge_into_map


# A country list is positive or negative, and emptying one is safe only for
# the negative kind: ``ForbiddenHouses=none`` is Mental Omega's own idiom,
# while ``Owner=none`` names a country that does not exist.
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


def _items(value):
    return [item.strip() for item in str(value or '').split(',') if item.strip()]


def _installed_rules():
    from randomizer.ui.cameos import installed_rules_registry

    _superweapons, sections = installed_rules_registry(synchronous=True)
    return sections or {}


def seat_country_section(rules, chosen, seat):
    """Return the seat's country section, rewritten as a copy of the chosen.

    Everything the country *is* comes from the country the player asked for:
    its side, its colour, the prefix and suffix that pick art and voices,
    the Ares multipliers, the AI power plant, the paradrop. What stays the
    seat's own is its place in the list -- ``ListIndex`` is what the spawner
    counts with.
    """
    values = dict(rules.get(chosen) or {})
    if not values:
        return {}
    for key, value in (rules.get(seat) or {}).items():
        if str(key).lower() == 'listindex':
            values[key] = value
    return values


def sides_section(rules, chosen, seat):
    """Return the whole of ``[Sides]``, with the seat moved to its new side.

    Every side is written, not only the two that change: the engine rebuilds
    its side list from what the map says rather than merging the rest back
    in. A map naming two sides leaves the game with two sides, and the debug
    log says so at "Processing sides" -- which is how this was found, after
    a match where the allied AI stopped building and Epsilon went quiet.
    """
    sides = dict(rules.get('Sides') or {})
    if not sides:
        return {}
    updated = {}
    for side, value in sides.items():
        members = [
            item for item in _items(value) if item.lower() != seat.lower()
        ]
        if any(item.lower() == chosen.lower() for item in members):
            members.append(seat)
        updated[side] = ','.join(members)
    return updated


def ownership_pass(rules, chosen, seat):
    """Return the edits that make the seat a stand-in for the chosen country.

    One rule: in every list of countries, the seat appears exactly where the
    country it stands for appears. Both directions matter -- without the
    removals the player could build the faction whose slot the seat came
    from, which is not the army they chose.
    """
    edits = {}
    counts = {'added': 0, 'removed': 0, 'forbidden': 0}
    for section, values in rules.items():
        forbid_instead = False
        for key in HOUSE_LIST_KEYS:
            actual = next(
                (name for name in values if name.lower() == key.lower()), None
            )
            if actual is None:
                continue
            names = _items(values[actual])
            lowered = [name.lower() for name in names]
            has_chosen = chosen.lower() in lowered
            has_seat = seat.lower() in lowered
            if has_chosen == has_seat:
                continue
            if has_chosen:
                names.append(seat)
                counts['added'] += 1
            elif key in POSITIVE_HOUSE_KEYS and len(names) == 1:
                # The seat is this type's only owner: a unit belonging to
                # the faction whose slot it came from. Removing it would
                # leave a list naming nobody, so the seat is shut out
                # instead -- the pairing Mental Omega itself uses.
                forbid_instead = True
                continue
            else:
                names = [
                    name for name in names if name.lower() != seat.lower()
                ]
                counts['removed'] += 1
            edits.setdefault(section, {})[actual] = (
                ','.join(names) if names else 'none'
            )
        if not forbid_instead:
            continue
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
            name for name in _items(existing)
            if name.lower() not in {'none', '<none>'}
        ]
        if seat not in names:
            names.append(seat)
        edits.setdefault(section, {})['ForbiddenHouses'] = ','.join(names)
        counts['forbidden'] += 1
    return edits, counts


def seat_map_code(chosen, seat, *, rules=None):
    """Return everything the map needs for one house to sit on a spare seat."""
    rules = rules if rules is not None else _installed_rules()
    if not rules or chosen.lower() == seat.lower():
        return {}, {'added': 0, 'removed': 0, 'forbidden': 0}
    code = {}
    country = seat_country_section(rules, chosen, seat)
    if not country:
        return {}, {'added': 0, 'removed': 0, 'forbidden': 0}
    code[seat] = country
    sides = sides_section(rules, chosen, seat)
    if sides:
        code['Sides'] = sides
    edits, counts = ownership_pass(rules, chosen, seat)
    for section, values in edits.items():
        code.setdefault(section, {}).update(values)
    return code, counts


def pick_seat(chosen, taken, countries, *, salt=''):
    """Return a country nobody else is playing, for one house to sit on.

    Deterministic in ``salt`` so the same battle seats the same way twice.
    Falls back to the chosen country when a battle somehow uses them all,
    which leaves the gate shared rather than leaving the battle unplayable.
    """
    import random

    unavailable = {str(name).lower() for name in taken}
    unavailable.add(str(chosen).lower())
    free = [
        country for country in countries
        if str(country).lower() not in unavailable
    ]
    if not free:
        return chosen
    return random.Random(f'{salt}:{chosen}').choice(sorted(free))


def apply_seat(map_path, chosen, seat, *, rules=None):
    """Write the seat into the map, and say how much of the rules it touched."""
    code, counts = seat_map_code(chosen, seat, rules=rules)
    if not code:
        return counts
    keys = merge_into_map(map_path, code)
    log_event(
        'skirmish_seat_applied',
        chosen=chosen,
        seat=seat,
        sections=len(code),
        keys=keys,
        **counts,
    )
    return counts
