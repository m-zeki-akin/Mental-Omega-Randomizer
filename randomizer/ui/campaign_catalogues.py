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

They are handed over in the order the installed rules list them, which is
not an order anybody chose -- it is the order the game itself reads, so a
player who knows where a unit sits in Mental Omega finds it in the same
place here. Alphabetical was worse than it sounds: it split every faction
apart and put the answer to "which of these two is the newer one" nowhere
in particular. What the rules do not name is listed after what they do,
by faction and then by name, so a submod renaming something moves it to
the end rather than losing it.
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
MISSION = 'mission'
CATALOGUE_NAMES = (UNIT_ACCESS, SUPERWEAPON, REWARD_NAME, MISSION)

# The rules sections that are lists of things, in the order the game
# reads them. Their order inside the file is the order of the catalogue.
TYPE_LISTS = (
    'INFANTRYTYPES', 'VEHICLETYPES', 'AIRCRAFTTYPES', 'BUILDINGTYPES',
    'SUPERWEAPONTYPES',
)

_built = {}
_ORDER = None


def _entry(item_id, label, group, cameo=None):
    """Return one thing a setting may name.

    ``cameo`` says what picture stands for it and is not always the id: a
    starting unlock is named by its reward, and a reward is not something
    the rules have art for. It carries the unit or power the picture
    belongs to instead -- the first one, for a reward that hands over
    several, because a row has room for one picture.
    """
    return {
        'id': str(item_id),
        'label': str(label),
        'group': str(group),
        'cameo': dict(cameo) if cameo else {},
    }


def _rules_order():
    """Return each type id and where the installed rules list it.

    Read once and kept. An installation the launcher cannot read the
    rules of answers with nothing, and everything falls back to the order
    it had before -- which is the right failure: a list in the wrong
    order is still a list, and an empty one is not.
    """
    global _ORDER
    if _ORDER is not None:
        return _ORDER
    try:
        from randomizer.ui.cameos import installed_rules_registry

        _superweapons, sections = installed_rules_registry(synchronous=True)
    except (OSError, ValueError):
        sections = {}
    order = {}
    for name, values in (sections or {}).items():
        if str(name).upper() not in TYPE_LISTS:
            continue
        for value in values.values():
            type_id = str(value).strip().upper()
            if type_id and type_id not in order:
                order[type_id] = len(order)
    if not order:
        # Not kept: an installation whose rules are not readable yet is
        # one that may be readable on the next ask, and an order cached
        # from nothing would never be asked for again.
        return {}
    _ORDER = order
    return _ORDER


def _ordering_id(entry):
    """Return the id the rules would know this entry by."""
    cameo = entry.get('cameo') or {}
    return str(
        cameo.get('unit') or cameo.get('power') or entry['id']
    ).upper()


def _in_rules_order(entries):
    """Return the entries as the installed rules list them.

    What the rules do not name keeps the order it was built in -- by
    faction, then by name -- and follows everything they do.
    """
    order = _rules_order()
    if not order:
        return tuple(entries)
    listed = len(order)
    return tuple(sorted(
        entries,
        key=lambda entry: order.get(_ordering_id(entry), listed),
    ))


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
                {'unit': unit_id},
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
            {'power': power_id},
        ))
    return _sorted(entries.values())


def _mission_entries():
    """Every mission this install has, in the order the game lists them.

    Not sorted, and not put through the rules order either: a mission is
    not a type the rules name, and the campaign already has an order of
    its own -- the one in ``BattleClient.ini``, which is the order the
    game itself offers them in and the order a player has seen them in
    for as long as they have played it.

    An install the launcher cannot read the campaign of answers with
    nothing, which is the honest answer: the alternative is a list of
    missions that are not there.
    """
    from randomizer.campaign.generator import installed_missions

    return tuple(
        _entry(
            mission['code'],
            mission.get('title') or mission['code'],
            str(mission.get('side') or 'Other'),
        )
        for mission in installed_missions()
        if mission.get('code')
    )


def _first_in_rules(tech_ids):
    """Return the one of these the installed rules name first.

    A reward that hands over several units has one row and room for one
    picture, so one of them has to stand for the rest. Which one is not
    obvious and must not be arbitrary: the ids arrive as a set, so
    picking whichever came out first would draw a different picture on
    different days. The rules decide, and where they say nothing the
    name does.
    """
    listed = sorted(str(tech_id).upper() for tech_id in tech_ids or ())
    if not listed:
        return ''
    order = _rules_order()
    return min(listed, key=lambda tech_id: order.get(tech_id, len(order)))


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
        power = str(reward.get('superweapon') or '').upper()
        handed = _first_in_rules(tech_ids_for_rewards([reward]))
        entries.append(_entry(
            name,
            reward_display_name(reward) or name,
            f'{factions[0]} - '
            f'{"Powers" if reward.get("kind") == "superweapon" else "Units"}',
            {'power': power} if power
            else ({'unit': handed} if handed else None),
        ))
    return _sorted(entries)


_BUILDERS = {
    UNIT_ACCESS: _unit_access_entries,
    SUPERWEAPON: _superweapon_entries,
    REWARD_NAME: _reward_name_entries,
    MISSION: _mission_entries,
}
# The lists whose order the installed rules decide. The campaign is not
# one of them: it has an order of its own and the rules have never named
# a mission.
RULES_ORDERED = frozenset({UNIT_ACCESS, SUPERWEAPON, REWARD_NAME})


def catalogue(name):
    """Return one named list, built the first time it is asked for."""
    wanted = str(name or '')
    if wanted not in _BUILDERS:
        return ()
    held = _built.get(wanted)
    if held is None:
        held = _BUILDERS[wanted]()
        _built[wanted] = held
    # Ordered here rather than when it was built: the rules may not have
    # been readable then, and a list built once would keep whatever order
    # that moment could manage for the rest of the launcher's life.
    return _in_rules_order(held) if wanted in RULES_ORDERED else held


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
