"""How far a buff reward actually reaches on this installation.

A stack limit is a promise: buy thirteen and the unit gets thirteen steps
better. On stock Mental Omega the promise holds. On a submod it can stop
early, or never start -- the mod already moved the unit to the speed ceiling,
already opened the transport, already gave it the armour the reward would
grant. The reward is still offered, still priced, and does nothing.

That is not a fault in the reward definitions, which are authored against
stock rules, and it is not something to fail a launch over: a modded game must
still run. What it is, is something the shop should stop selling. So this
computes the stack at which each reward stops changing anything, and the
offers clamp to it.

Two things this deliberately does not do. It does not touch ``BUFF_TARGETS``
or ``UNIT_BUFF_REWARDS`` -- the Archipelago catalogue checksum is taken over
those, and a multiworld host without the game installed must arrive at the
same catalogue as a player with it. And it does not treat one flat stack as
the end: self-healing at 90 hit points steps 1, 2, 3, 4, 4, 5, 6, and a
reward is only finished once it never moves again.
"""

from functools import lru_cache


def dead_from(sequence):
    """Return the first stack after which nothing changes again.

    ``sequence[0]`` is the unbuffed state, so a return of 1 means the reward
    does nothing at all. ``None`` means it works to the end.
    """
    for index in range(1, len(sequence)):
        if all(later == sequence[index - 1] for later in sequence[index:]):
            return index
    return None


def _normalized(values):
    return {
        str(key).lower(): str(value)
        for key, value in (values or {}).items()
    }


def direct_weapon_ids(values):
    """Return the weapon ids a TechnoType body actually fires."""
    result = set()
    for key, value in (values or {}).items():
        lowered = str(key).lower()
        direct = lowered in {
            'primary', 'secondary', 'eliteprimary', 'elitesecondary',
        }
        direct = direct or (
            lowered.startswith('weapon')
            and lowered.removeprefix('weapon').isdigit()
        ) or (
            lowered.startswith('eliteweapon')
            and lowered.removeprefix('eliteweapon').isdigit()
        )
        weapon_id = str(value or '').strip()
        if direct and weapon_id.lower() not in {'', 'none', '<none>'}:
            result.add(weapon_id.upper())
    return result


def _installed_number(section, key):
    for name, value in (section or {}).items():
        if str(name).lower() == key:
            try:
                return float(str(value).strip())
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def fielded_weapon_stats(template, target, installed):
    """Return the weapons a clone fires, with the stats it fires them at.

    The catalogue records stock Mental Omega's weapon names and a submod
    renames them -- this is why a Bomb Buggy damage reward looked dead: the
    catalogue says ``Demobomb`` and the mod's buggy fires ``DemobombBuggy``.
    Map generation already resolves that in ``maps/clone_builder``, pulling
    every direct weapon off the clone body and skipping any catalogue weapon
    the clone does not reference. Asking a different question here would
    report a working reward as dead.
    """
    referenced = direct_weapon_ids(template)
    if target.get('power_payload_only'):
        # Payload-only identities are cloned from live rules at launch and
        # have no production template to read weapons off.
        referenced.update(
            str(weapon_id).upper()
            for weapon_id in target.get('weapons', {})
        )
    stats = {}
    for weapon_id, base_stats in (target.get('weapons') or {}).items():
        if str(weapon_id).upper() in referenced:
            stats[str(weapon_id).upper()] = base_stats
    for weapon_id in sorted(referenced - set(stats)):
        section = installed.get(weapon_id)
        if not section:
            continue
        stats[weapon_id] = {
            'damage': _installed_number(section, 'damage'),
            'rof': _installed_number(section, 'rof'),
            'range': _installed_number(section, 'range'),
        }
    return stats


def unit_buff_sequence(unit_id, buff_type, count, templates, targets):
    """Return the per-stack results of a direct TechnoType buff.

    ``None`` when a stack refuses to apply at all, which is a different
    condition from applying and changing nothing.
    """
    from randomizer.maps.buff_values import apply_unit_buff_value

    target = targets.get(unit_id, {})
    before = dict(templates.get(unit_id, {}))
    sequence = [_normalized(before)]
    for stack in range(1, count + 1):
        after = dict(before)
        try:
            applied = apply_unit_buff_value(after, target, buff_type, stack)
        except (KeyError, TypeError, ValueError):
            return None
        if not applied:
            return None
        sequence.append(_normalized(after))
    return sequence


def weapon_buff_sequence(unit_id, buff_type, count, templates, targets, installed):
    """Return the per-stack results of a WeaponType buff, peers included."""
    from randomizer.maps.buff_values import apply_weapon_buff_value
    from randomizer.maps.weapon_buffs import spawned_missile_range_guard_rules
    from randomizer.rewards.catalogue import linked_buff_variant_ids

    sequence = [()]
    for stack in range(1, count + 1):
        current = []
        for peer_id in sorted(linked_buff_variant_ids(unit_id) or {unit_id}):
            peer_target = targets.get(peer_id, targets.get(unit_id, {}))
            peer_template = templates.get(peer_id, {})
            for weapon_id, stats in sorted(
                fielded_weapon_stats(peer_template, peer_target, installed).items()
            ):
                changed = {}
                if not apply_weapon_buff_value(changed, stats, buff_type, stack):
                    continue
                changed_values = _normalized(changed)
                stat_field = 'rof' if buff_type == 'reload' else buff_type
                if changed_values.get(stat_field) == str(stats.get(stat_field)):
                    continue
                current.append((
                    peer_id,
                    str(weapon_id).upper(),
                    tuple(sorted(changed_values.items())),
                ))
            if buff_type == 'range':
                for missile_id, values in sorted(
                    spawned_missile_range_guard_rules(peer_target, stack).items()
                ):
                    current.append((
                        peer_id,
                        str(missile_id).upper(),
                        tuple(sorted(_normalized(values).items())),
                    ))
        sequence.append(tuple(current))
    return sequence


@lru_cache(maxsize=1)
def inert_buff_stacks():
    """Return ``{(UNIT, buff_type): first dead stack}`` for this installation.

    Absent means the reward works to its full limit. A value of 1 means it
    does nothing at all.
    """
    from randomizer.rewards.catalogue import (
        BUFF_TARGETS,
        UNIT_BUFF_REWARDS,
        buff_stack_limit,
    )
    from randomizer.rewards.roster import (
        _installed_sections,
        randomizer_unit_roster,
    )

    try:
        _paths, _clone_ids, templates = randomizer_unit_roster()
    except (FileNotFoundError, ValueError):
        # No readable rules means no way to tell, and no reason to withhold
        # anything: the launcher will fail on the roster before it sells.
        return {}
    installed = _installed_sections()
    reach = {}
    for reward in UNIT_BUFF_REWARDS:
        unit_id = str(reward.get('unit') or '').upper()
        buff_type = str(reward.get('buff_type') or '')
        if not unit_id or not buff_type:
            continue
        target = BUFF_TARGETS.get(unit_id, {})
        count = max(1, int(buff_stack_limit(reward) or 1))
        if buff_type in {'damage', 'range', 'reload'}:
            sequence = weapon_buff_sequence(
                unit_id, buff_type, count, templates, BUFF_TARGETS, installed
            )
        elif buff_type in {'build_limit', 'building_limit'}:
            # A reviewed limit, not a value read off the unit.
            continue
        elif buff_type == 'veteran' or (
            target.get('global_production') and buff_type == 'production'
        ):
            continue
        else:
            sequence = unit_buff_sequence(
                unit_id, buff_type, count, templates, BUFF_TARGETS
            )
            if sequence is None:
                reach[(unit_id, buff_type)] = 1
                continue
        stops = dead_from(sequence)
        if stops is not None:
            reach[(unit_id, buff_type)] = stops
    return reach


def effective_stack_limit(unit_id, buff_type, limit):
    """Return the stacks worth selling: ``0`` when the reward does nothing.

    Offer sites use this instead of ``buff_stack_limit``. The catalogue's own
    limit is left alone, because it is what the Archipelago contract and every
    saved profile were written against.
    """
    try:
        limit = int(limit or 0)
    except (TypeError, ValueError):
        return 0
    stops = inert_buff_stacks().get(
        (str(unit_id or '').upper(), str(buff_type or ''))
    )
    if stops is None:
        return limit
    return max(0, min(limit, int(stops) - 1))


def summary():
    """Return what the clamp is doing, for the self-check report."""
    from randomizer.rewards.catalogue import (
        UNIT_BUFF_REWARDS,
        buff_stack_limit,
    )

    reach = inert_buff_stacks()
    if not reach:
        return {'clamped_rewards': 0, 'withdrawn_rewards': [], 'lost_stacks': 0}
    withdrawn = []
    lost = 0
    clamped = 0
    for reward in UNIT_BUFF_REWARDS:
        unit_id = str(reward.get('unit') or '').upper()
        buff_type = str(reward.get('buff_type') or '')
        limit = max(1, int(buff_stack_limit(reward) or 1))
        offered = effective_stack_limit(unit_id, buff_type, limit)
        if offered >= limit:
            continue
        clamped += 1
        lost += limit - offered
        if offered == 0:
            withdrawn.append(f'{unit_id}/{buff_type}')
    return {
        'clamped_rewards': clamped,
        'withdrawn_rewards': sorted(set(withdrawn)),
        'lost_stacks': lost,
    }
