"""Turning what a run has bought into what the battle is played with.

The campaign builds clone units and grants access to them. A skirmish needs
none of that: both armies already field their whole country, and what an
upgrade changes is how well. So a purchase is written straight onto the
unit's own section in the map the battle is fought on -- ``[GGI] Speed=`` --
and the engine reads it from there.

The values come from the same code the campaign buffs use, applied to the
unit as this installation actually has it, so an upgrade adds to what the
unit is rather than to what stock Mental Omega says it was.

One consequence worth stating: a TechnoType is global. Buffing a Soviet tank
buffs it for everyone fielding that tank, which is why the enemies a battle
draws never share a side with the player or their ally.
"""

from randomizer.core.diagnostics import event as log_event

from .mapfile import merge_into_map


WEAPON_BUFF_TYPES = frozenset({'damage', 'range', 'reload'})


def _normalized(values):
    return {str(key): str(value) for key, value in (values or {}).items()}


def unit_rules(unit, buff_type, stacks, installed, targets):
    """Return the section edits one purchase makes, or ``{}`` if it makes none."""
    from randomizer.maps.buff_values import (
        apply_unit_buff_value,
        apply_weapon_buff_value,
    )
    from randomizer.rewards.buff_reach import fielded_weapon_stats

    target = dict(targets.get(unit) or {})
    if not target:
        return {}
    if buff_type in WEAPON_BUFF_TYPES:
        rules = {}
        template = installed.get(unit) or {}
        for weapon_id, stats in fielded_weapon_stats(
            template, target, installed
        ).items():
            changed = {}
            if not apply_weapon_buff_value(changed, stats, buff_type, stacks):
                continue
            if changed:
                rules.setdefault(weapon_id, {}).update(_normalized(changed))
        return rules
    body = dict(installed.get(unit) or {})
    if not body:
        return {}
    before = _normalized(body)
    try:
        applied = apply_unit_buff_value(body, target, buff_type, stacks)
    except (KeyError, TypeError, ValueError):
        return {}
    if not applied:
        return {}
    after = _normalized(body)
    changed = {
        key: value for key, value in after.items()
        if before.get(key) != value
    }
    return {unit: changed} if changed else {}


def upgrade_rules(purchases):
    """Return ``{section: {key: value}}`` for everything a run has bought."""
    from randomizer.rewards.catalogue import BUFF_TARGETS
    from randomizer.rewards.roster import _installed_sections

    installed = _installed_sections()
    if not installed:
        return {}
    rules = {}
    for purchase in purchases or ():
        for section, values in unit_rules(
            purchase.unit,
            purchase.buff_type,
            purchase.stacks,
            installed,
            BUFF_TARGETS,
        ).items():
            rules.setdefault(section, {}).update(values)
    return rules


def apply_upgrades_to_map(map_path, purchases):
    """Write a run's upgrades into the map the battle will be played on."""
    rules = upgrade_rules(purchases)
    if not rules:
        return 0
    applied = merge_into_map(map_path, rules)
    log_event(
        'skirmish_upgrades_applied',
        purchases=len(tuple(purchases or ())),
        sections=len(rules),
        keys=applied,
    )
    return applied
