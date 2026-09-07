"""The named lists a campaign setting picks its entries out of.

Three settings name things rather than hold a value: which units a run
leaves out, which powers it leaves out, and which rewards it starts with.
What they may name comes from the installed rules, so it is a few hundred
entries long and it changes when a submod does -- which makes it a list to
be searched rather than a catalogue to be drawn.

A screen asks for one by name and filters it itself, because filtering as
somebody types is not something to ask the launcher once per letter. The
lists are built once and kept: the rules they come from do not change
while the launcher is open.
"""

from randomizer.rewards.catalogue import (
    BUFF_TARGETS,
    REWARD_POOL,
    canonical_reward,
    linked_buff_variant_ids,
    reward_display_name,
    unit_display_label,
)
from randomizer.rewards.rules import tech_ids_for_rewards


# The categories a unit has to be one of to be worth excluding. The rest
# of what a reward can carry is not a unit anybody builds.
UNIT_CATEGORIES = {
    'infantry': 'Infantry',
    'units': 'Vehicles / Naval',
    'aircraft': 'Aircraft',
    'defenses': 'Defences',
    'special_buildings': 'Special buildings',
}
POWER_CATEGORIES = {
    'offensive': 'Superweapons',
    'secondary': 'Secondary powers',
    'aid': 'Support powers',
}
# What order the factions read in, which is the order the launcher has
# always listed them in.
FACTION_ORDER = {
    'Allies': 0, 'Soviets': 1, 'Epsilon': 2, 'Foehn': 3,
    'Neutral': 4, 'Other': 5,
}

UNIT_ACCESS = 'unit_access'
SUPERWEAPON = 'superweapon'
REWARD_NAME = 'reward_name'
CATALOGUE_NAMES = (UNIT_ACCESS, SUPERWEAPON, REWARD_NAME)

_built = {}


def _entry(item_id, label, group):
    return {'id': str(item_id), 'label': str(label), 'group': str(group)}


def _sorted(entries):
    return tuple(sorted(
        entries,
        key=lambda entry: (
            FACTION_ORDER.get(entry['group'].split(' - ')[0], 4),
            entry['label'].casefold(),
            entry['id'],
        ),
    ))


def _unit_access_entries():
    """Every unit an access reward can hand over, by its own id.

    Built the way the classic window builds its exclusion pool: a reward
    names tech ids, a linked variant answers for the unit it is a variant
    of, and what is not a unit anybody builds is left out.
    """
    entries = {}
    for reward in REWARD_POOL:
        if reward.get('kind') in {'buff', 'superweapon'}:
            continue
        factions = tuple(reward.get('factions') or ('Other',))
        for tech_id in tech_ids_for_rewards([reward]):
            linked = linked_buff_variant_ids(tech_id)
            unit_id = next(
                (
                    candidate for candidate in linked
                    if not BUFF_TARGETS.get(candidate, {}).get(
                        'linked_buff_source'
                    )
                ),
                tech_id,
            )
            category = BUFF_TARGETS.get(unit_id, {}).get('category')
            if category not in UNIT_CATEGORIES:
                continue
            entries.setdefault(unit_id, _entry(
                unit_id,
                unit_display_label(unit_id),
                f'{factions[0]} - {UNIT_CATEGORIES[category]}',
            ))
    return _sorted(entries.values())


def _superweapon_entries():
    """Every power a run can unlock, by the id the rules give it."""
    entries = {}
    for reward in REWARD_POOL:
        if reward.get('kind') != 'superweapon' or not reward.get('superweapon'):
            continue
        factions = tuple(reward.get('factions') or ('Other',))
        # A power several factions share is not one faction's to exclude,
        # which is the rule the classic window follows too.
        if len(factions) != 1:
            continue
        category = reward.get('power_category', 'offensive')
        power_id = str(reward['superweapon']).upper()
        entries.setdefault(power_id, _entry(
            power_id,
            reward_display_name(reward),
            f'{factions[0]} - '
            f'{POWER_CATEGORIES.get(category, "Other powers")}',
        ))
    return _sorted(entries.values())


def _reward_name_entries():
    """Every reward a run can be handed before it starts.

    A starting unlock is named rather than pointed at, because what it
    hands over is the reward itself. Buffs are not among them: a run
    cannot start with an upgrade to something it does not have.
    """
    entries = []
    seen = set()
    for source in REWARD_POOL:
        reward = canonical_reward(source)
        name = reward.get('name')
        if not name or name in seen:
            continue
        if reward.get('kind') in {'buff', 'message', 'retired'}:
            continue
        if reward.get('retired_reward'):
            continue
        if not (
            reward.get('kind') == 'superweapon'
            or tech_ids_for_rewards([reward])
        ):
            continue
        seen.add(name)
        factions = tuple(reward.get('factions') or ('Other',))
        entries.append(_entry(
            name,
            reward_display_name(reward) or name,
            f'{factions[0]} - '
            f'{"Powers" if reward.get("kind") == "superweapon" else "Units"}',
        ))
    return _sorted(entries)


_BUILDERS = {
    UNIT_ACCESS: _unit_access_entries,
    SUPERWEAPON: _superweapon_entries,
    REWARD_NAME: _reward_name_entries,
}


def catalogue(name):
    """Return one named list, built the first time it is asked for."""
    wanted = str(name or '')
    if wanted not in _BUILDERS:
        return ()
    held = _built.get(wanted)
    if held is None:
        held = _BUILDERS[wanted]()
        _built[wanted] = held
    return held


def labels(name, ids):
    """Name what has been chosen, in the order it was chosen.

    An id the installed rules no longer know is kept and shown as itself:
    a submod that renames a unit should not quietly empty a list somebody
    built, and an entry nobody recognises is one they can see to remove.
    """
    known = {entry['id']: entry['label'] for entry in catalogue(name)}
    chosen = []
    seen = set()
    for item in ids or ():
        item_id = str(item)
        if item_id in seen:
            continue
        seen.add(item_id)
        chosen.append({'id': item_id, 'label': known.get(item_id, item_id)})
    return chosen
