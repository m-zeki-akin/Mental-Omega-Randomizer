"""Giving one house a private copy of the units it has paid to improve.

A TechnoType is global. ``[GGI] Speed=8`` is Guardian GI's speed for every
house that fields one, so an upgrade written that way is an upgrade the
enemy gets for free. What a house can own privately is a *different type*:
a copy of the unit under its own ID, gated to that house's country, with the
original shut out so the sidebar shows one cameo rather than two.

Mental Omega does exactly this for its own country-unique units -- ``[SHOCK]
RequiredHouses=USSR`` -- so the gate is the mod's own, not an invention. The
copy keeps ``Image`` pointing at the source, so no art file is needed.

Weapon buffs need the same treatment one level down: damage, range and
reload are the weapon's stats, and weapons are shared between units and
between factions. So a buffed weapon is copied too, and only the clone's own
weapon keys are repointed at the copy.

Nothing here decides *who* may build a type beyond the house that bought it;
seating a house on a country nobody else uses is ``seats``'s job, and this
module is only correct when that has been done.
"""

from randomizer.core.diagnostics import event as log_event

from .mapfile import merge_into_map


# Ares refuses a type ID longer than this, and the launcher's campaign path
# has always kept to it.
MAX_TYPE_ID_LENGTH = 24
# Registered from here upwards. A script's argument can be an index into a
# type list, so a clone is appended and nothing is renumbered.
TYPE_LIST_KEY_START = 20000
TYPE_LIST_BY_CATEGORY = {
    'infantry': 'InfantryTypes',
    'units': 'VehicleTypes',
    'aircraft': 'AircraftTypes',
    'defenses': 'BuildingTypes',
    'special_buildings': 'BuildingTypes',
}
WEAPON_BUFF_TYPES = frozenset({'damage', 'range', 'reload'})
# Every key on a TechnoType body that names a weapon it fires directly.
WEAPON_KEYS = ('primary', 'secondary', 'eliteprimary', 'elitesecondary')
OWNERSHIP_KEYS = ('owner', 'requiredhouses', 'forbiddenhouses')


def _items(value):
    return [item.strip() for item in str(value or '').split(',') if item.strip()]


def _value(values, key):
    for name, value in (values or {}).items():
        if str(name).lower() == key.lower():
            return value
    return ''


def _drop(values, *keys):
    lowered = {key.lower() for key in keys}
    for name in [name for name in values if str(name).lower() in lowered]:
        values.pop(name)


def _weapon_keys(body):
    """Return ``{key: weapon_id}`` for every weapon this body fires itself."""
    found = {}
    for key, value in (body or {}).items():
        lowered = str(key).lower()
        direct = lowered in WEAPON_KEYS or (
            lowered.startswith('weapon')
            and lowered.removeprefix('weapon').isdigit()
        ) or (
            lowered.startswith('eliteweapon')
            and lowered.removeprefix('eliteweapon').isdigit()
        )
        weapon = str(value or '').strip()
        if direct and weapon.lower() not in {'', 'none', '<none>'}:
            found[key] = weapon.upper()
    return found


def clone_id(prefix, unit, taken):
    """Return an ID for this house's copy of a unit, short enough for Ares."""
    stem = f'{prefix}{unit}'[:MAX_TYPE_ID_LENGTH]
    candidate = stem
    suffix = 1
    while candidate.lower() in taken:
        tail = str(suffix)
        candidate = f'{stem[:MAX_TYPE_ID_LENGTH - len(tail)]}{tail}'
        suffix += 1
    taken.add(candidate.lower())
    return candidate


def unit_clone(unit, purchases, country, *, prefix, installed, targets, taken):
    """Return the sections one house's copy of one unit needs.

    ``purchases`` are that unit's, in any order: stat buffs are applied to
    the copied body and weapon buffs to copies of the weapons it fires.
    """
    from randomizer.maps.buff_values import (
        apply_unit_buff_value,
        apply_weapon_buff_value,
    )
    from randomizer.rewards.buff_reach import fielded_weapon_stats

    template = installed.get(unit) or {}
    target = dict(targets.get(unit) or {})
    if not template or not target:
        return {}, None
    body = dict(template)
    changed = False
    for purchase in purchases:
        if purchase.buff_type in WEAPON_BUFF_TYPES:
            continue
        try:
            if apply_unit_buff_value(
                body, target, purchase.buff_type, purchase.stacks
            ):
                changed = True
        except (KeyError, TypeError, ValueError):
            continue

    sections = {}
    weapon_buffs = [
        purchase for purchase in purchases
        if purchase.buff_type in WEAPON_BUFF_TYPES
    ]
    if weapon_buffs:
        stats = fielded_weapon_stats(template, target, installed)
        fired = _weapon_keys(body)
        replacements = {}
        for weapon_id, base_stats in stats.items():
            edits = {}
            for purchase in weapon_buffs:
                apply_weapon_buff_value(
                    edits, base_stats, purchase.buff_type, purchase.stacks
                )
            if not edits:
                continue
            weapon_body = dict(installed.get(weapon_id) or {})
            if not weapon_body:
                continue
            weapon_body.update(
                {key: str(value) for key, value in edits.items()}
            )
            replacements[weapon_id] = clone_id(prefix, weapon_id, taken)
            sections[replacements[weapon_id]] = weapon_body
            changed = True
        # Only this copy fires the copied weapons. The original keeps firing
        # the shared ones, which is what stops the buff reaching everyone.
        for key, weapon_id in fired.items():
            if weapon_id in replacements:
                body[key] = replacements[weapon_id]

    if not changed:
        return {}, None

    identifier = clone_id(prefix, unit, taken)
    if not any(str(key).lower() == 'image' for key in body):
        body['Image'] = unit
    owners = _items(_value(template, 'Owner'))
    if country not in owners:
        owners.append(country)
    _drop(body, *OWNERSHIP_KEYS)
    body['Owner'] = ','.join(owners)
    # The positive gate. Everything else about the copy is the unit's own.
    body['RequiredHouses'] = country
    sections[identifier] = body
    return sections, identifier


def house_clone_code(purchases, country, *, prefix, forbid_source=True):
    """Return the map code that gives one house its own upgraded units.

    ``forbid_source`` shuts the original out of that country, which is what
    keeps a human's sidebar to one cameo per unit. It is wrong for a house
    whose production comes from AI task forces naming the original.
    """
    from randomizer.rewards.catalogue import BUFF_TARGETS
    from randomizer.rewards.roster import _installed_sections

    installed = _installed_sections()
    if not installed or not purchases:
        return {}, {}
    by_unit = {}
    for purchase in purchases:
        by_unit.setdefault(purchase.unit, []).append(purchase)

    taken = {str(name).lower() for name in installed}
    sections = {}
    built = {}
    for unit, unit_purchases in sorted(by_unit.items()):
        made, identifier = unit_clone(
            unit,
            unit_purchases,
            country,
            prefix=prefix,
            installed=installed,
            targets=BUFF_TARGETS,
            taken=taken,
        )
        if not identifier:
            continue
        sections.update(made)
        built[unit] = identifier
        category = str((BUFF_TARGETS.get(unit) or {}).get('category') or '')
        list_section = TYPE_LIST_BY_CATEGORY.get(category)
        if list_section:
            registered = sections.setdefault(list_section, {})
            key = TYPE_LIST_KEY_START + len(registered)
            while str(key) in registered:
                key += 1
            registered[str(key)] = identifier
        if forbid_source:
            forbidden = [
                name for name in _items(
                    _value(installed.get(unit), 'ForbiddenHouses')
                )
                if name.lower() not in {'none', '<none>'}
            ]
            if country not in forbidden:
                forbidden.append(country)
            sections.setdefault(unit, {})['ForbiddenHouses'] = (
                ','.join(forbidden)
            )
    return sections, built


def apply_house_clones(map_path, purchases, country, *, prefix, forbid_source=True):
    """Write one house's private copies into the map, and say what was made."""
    sections, built = house_clone_code(
        purchases, country, prefix=prefix, forbid_source=forbid_source
    )
    if not sections:
        return {}
    keys = merge_into_map(map_path, sections)
    log_event(
        'skirmish_house_clones_applied',
        country=country,
        units=len(built),
        sections=len(sections),
        keys=keys,
    )
    return built
