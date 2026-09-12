"""The superweapons a run can buy upgrades for, and how one is delivered.

A skirmish grants nobody a superweapon: the player builds a Nuclear Missile
Silo and gets the Tactical Nuke the way anybody does. So an upgrade here is
not an unlock with a buff folded into it, which is what the campaign sells.
It is a *private copy of the power itself*, granted by the same building
and gated to the buyer.

Three facts about Mental Omega make that work, all read out of the
installed rules rather than assumed:

1. Buffs land on the superweapon's own section. Swept across all 136
   powers, every buff that produces anything writes ``RechargeTime``,
   ``Money.Amount``, ``SW.Damage``, ``SW.Range``, a paradrop or delivery
   list, or a duration -- all keys of the power. The only two that ask
   for anything else ask for the armour table and a warhead, and want
   nothing of the power itself, so they produce nothing here and are not
   sold: a copy is a different power, not a private warhead.
2. ``SW.RequiredHouses`` and ``SW.ForbiddenHouses`` are the mod's own
   tags, already used on four powers and two.
3. ``SuperWeapons=`` on a building *adds to* ``SuperWeapon=`` and
   ``SuperWeapon2=`` rather than replacing them. Thirteen buildings carry
   all three and grant all of them -- the Allied Battle Lab grants three
   powers off three keys. So a copy is handed over by appending to that
   one key, and the two the mod wrote are never touched.
"""

import re

from randomizer.core.diagnostics import event as log_event


# The list the engine reads its powers from, and the keys a building
# grants them by. The first two are vanilla and hold one power each; the
# third is Ares' list, and it is the only one this module writes.
POWER_LIST = 'SuperWeaponTypes'
GRANT_KEYS = ('SuperWeapon', 'SuperWeapon2')
GRANT_LIST_KEY = 'SuperWeapons'
# What a copy of a power is called. Distinct from the unit prefixes so
# nothing can collide with a TechnoType of the same name.
POWER_CLONE_PREFIX = 'MOW'
# The section the IQ thresholds live in, which carries a ``SuperWeapons``
# key that is a number rather than a list of powers.
NOT_A_BUILDING = 'IQ'
_LIST_KEY = re.compile(r'^\d+$')


def _rules():
    from randomizer.ui.cameos import installed_rules_registry

    _superweapons, rules = installed_rules_registry(synchronous=True)
    return rules or {}


def superweapon_ids(rules=None):
    """Return every power the installed rules list, upper-cased."""
    rules = _rules() if rules is None else rules
    listed = (rules.get(POWER_LIST) or {}).values()
    return frozenset(
        str(one).strip().upper() for one in listed if str(one).strip()
    )


def granting_buildings(rules=None):
    """Return ``{power id: (building id, ...)}`` for what grants what.

    All three keys are read, because a power a run can buy an upgrade for
    is one the player can build the granting structure for, and which of
    the three keys the mod happened to use says nothing about that.
    """
    rules = _rules() if rules is None else rules
    powers = superweapon_ids(rules)
    granted = {}
    for name, body in rules.items():
        if str(name) == NOT_A_BUILDING:
            continue
        named = []
        for key, value in (body or {}).items():
            key = str(key)
            if key in GRANT_KEYS:
                named.append(str(value))
            elif key == GRANT_LIST_KEY:
                named.extend(str(value).split(','))
        for one in named:
            one = one.strip().upper()
            if one and one in powers:
                granted.setdefault(one, []).append(str(name).upper())
    return {power: tuple(sorted(set(who))) for power, who in granted.items()}


def country_powers(country, rules=None):
    """Return the powers this country can put on the field, and by what.

    A power is only worth an upgrade if the country can build something
    that grants it: a Soviet run has no Chronosphere to make recharge
    faster.
    """
    from .ownership import buildable_units

    rules = _rules() if rules is None else rules
    fielded = buildable_units(str(country or ''))
    if not fielded:
        return {}
    found = {}
    for power, buildings in granting_buildings(rules).items():
        theirs = tuple(one for one in buildings if one in fielded)
        if theirs:
            found[power] = theirs
    return found


def canonical_power(power_id, rules=None):
    """Return a power's id spelled the way the rules spell it.

    Sections are named in the mod's own casing -- ``NukeSpecial``, not
    ``NUKESPECIAL`` -- and the campaign's folding pass looks the power up
    by that name. Everything here compares upper-cased and writes back the
    spelling the file uses.
    """
    rules = _rules() if rules is None else rules
    wanted = str(power_id or '').upper()
    for name in rules:
        if str(name).upper() == wanted:
            return str(name)
    return str(power_id or '')


def power_buff_rules(power_id, buff_type, stacks=1, rules=None):
    """Return what one power upgrade writes onto the power's own section.

    Computed by handing the campaign's own folding pass a power beside the
    buffs bought for it, and taking the rules it folded in. Empty when the
    buff has nothing to bite on -- a power with no money to give has no
    cost to improve -- and empty when what it writes is shared, because a
    copy cannot make a global table private.
    """
    from randomizer.maps.power_buffs import apply_power_buffs_to_unlock_rewards

    rules = _rules() if rules is None else rules
    power_id = canonical_power(power_id, rules)
    if not power_id or not buff_type:
        return {}
    unlock = {
        'kind': 'superweapon',
        'superweapon': power_id,
        'name': power_id,
        'factions': [],
    }
    bought = [
        {
            'kind': 'buff',
            'superweapon': power_id,
            'power_buff_type': str(buff_type),
            'power_name': power_id,
            'name': f'{power_id} {buff_type}',
            'rules': {},
        }
        for _ in range(max(1, int(stacks)))
    ]
    folded = apply_power_buffs_to_unlock_rewards([unlock, *bought], rules)
    if not folded:
        return {}
    reward = folded[0]
    # Only what belongs to the power itself. A buff may also ask for a
    # change to the armour table or to a warhead, and those are read by
    # every house on the map: a copy is a different power, not a private
    # warhead. A buff that has nothing left after that is not sold at
    # all, which is what the empty answer here means.
    return {
        str(key): str(value)
        for key, value in (reward.get('superweapon_rules') or {}).items()
    }


def sellable_buffs(power_id, rules=None):
    """Return the buff types worth selling for one power."""
    from randomizer.rewards.power_buff_definitions import power_buff_type_ids

    rules = _rules() if rules is None else rules
    installed = {
        str(key).lower(): str(value)
        for key, value in (
            rules.get(canonical_power(power_id, rules)) or {}
        ).items()
    }
    sellable = []
    for buff in (power_buff_type_ids(power_id) or ()):
        written = power_buff_rules(power_id, buff, 1, rules)
        # A row whose every key already reads what it would write is Ore
        # for nothing on this installation, and is not offered.
        if written and any(
            str(value) != installed.get(str(key).lower())
            for key, value in written.items()
        ):
            sellable.append(buff)
    return tuple(sellable)


def _next_key(existing):
    """Return the first free numbered slot in a list section."""
    used = {int(key) for key in existing or {} if _LIST_KEY.match(str(key))}
    candidate = 1
    while candidate in used:
        candidate += 1
    return str(candidate)


def power_clone_code(purchases, seat, *, prefix=POWER_CLONE_PREFIX,
                     existing=None, rules=None):
    """Return the map code that gives one house its own copies of powers.

    The copy carries the buffed keys and ``SW.RequiredHouses`` naming the
    seat; the original gains the seat in ``SW.ForbiddenHouses``, so the
    buyer is handed one power rather than two. The building that granted
    the original is told to grant the copy as well, by appending to the
    one key that adds rather than replaces.
    """
    rules = _rules() if rules is None else rules
    existing = existing or {}
    upper = {str(name).upper(): body for name, body in rules.items()}
    granted = granting_buildings(rules)
    powers = superweapon_ids(rules)
    sections = {}
    built = {}
    by_power = {}
    for purchase in purchases or ():
        power = str(getattr(purchase, 'unit', '') or '').upper()
        if power not in powers:
            continue
        by_power.setdefault(power, []).append(purchase)
    if not by_power:
        return {}, {}

    for power, bought in sorted(by_power.items()):
        body = dict(upper.get(power) or {})
        if not body:
            continue
        copy = f'{prefix}{power}'[:24]
        for purchase in bought:
            body.update(power_buff_rules(
                power,
                getattr(purchase, 'buff_type', ''),
                max(1, int(getattr(purchase, 'stacks', 1))),
                rules,
            ))
        body['SW.RequiredHouses'] = seat
        sections[copy] = body
        built[power] = copy
        # The original is taken away from the buyer, or they would build
        # the silo and be handed the power twice -- and it is taken away
        # under the name the rules spell it by. A map section called
        # [IRONCURTAINSPECIAL] is a new section as far as the engine is
        # concerned, not the one it already has as [IronCurtainSpecial];
        # a ban written there reached nothing, and the buyer was handed
        # the power twice, once plain and once improved.
        spelled = canonical_power(power, rules)
        forbidden = [
            item.strip() for item
            in str((upper.get(power) or {}).get('SW.ForbiddenHouses') or '')
            .split(',') if item.strip()
        ]
        if seat not in forbidden:
            forbidden.append(seat)
        sections.setdefault(spelled, {})['SW.ForbiddenHouses'] = ','.join(
            forbidden
        )
        # And whatever granted the original grants the copy too.
        for building in granted.get(power, ()):  # noqa: PLR1702
            listed = dict(
                existing.get(building) or upper.get(building) or {}
            )
            names = [
                item.strip()
                for item in str(listed.get(GRANT_LIST_KEY) or '').split(',')
                if item.strip()
            ]
            if copy not in names:
                names.append(copy)
            sections.setdefault(building, {})[GRANT_LIST_KEY] = ','.join(names)

    # And the copies are listed, or the engine never reads their sections.
    listing = dict(existing.get(POWER_LIST) or rules.get(POWER_LIST) or {})
    added = {}
    for copy in sorted(built.values()):
        if copy in listing.values():
            continue
        key = _next_key({**listing, **added})
        added[key] = copy
        listing[key] = copy
    if added:
        sections[POWER_LIST] = added
    return sections, built


def apply_power_clones(map_path, purchases, seat, *,
                       prefix=POWER_CLONE_PREFIX):
    """Write one house's private copies of the powers it bought."""
    from .mapfile import merge_into_map
    from .options import read_ini_sections

    sections, built = power_clone_code(
        purchases, seat, prefix=prefix, existing=read_ini_sections(map_path),
    )
    if not sections:
        return {}
    keys = merge_into_map(map_path, sections)
    log_event(
        'skirmish_power_clones_applied',
        seat=seat,
        powers=len(built),
        sections=len(sections),
        keys=keys,
    )
    return built
