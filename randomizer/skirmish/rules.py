"""What one upgrade does to one unit, on this installation.

The values come from the same code the campaign buffs use, applied to the
unit as this installation actually has it, so an upgrade adds to what the
unit is rather than to what stock Mental Omega says it was.

Where the answer goes is ``clones``' business, and it is not the unit's own
section: a TechnoType is global, so ``[GGI] Speed=8`` is Guardian GI's speed
for the enemy too. That is what this module used to write, and what the
private copies replaced. What is left here is the arithmetic, which the shop
also asks in order not to sell an upgrade this installation would not
notice.
"""

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
