"""Reward-weight defaults, validation, and reward classification."""

from math import isfinite


DEFAULT_REWARD_WEIGHT = 100
MAX_REWARD_WEIGHT = 100

MAIN_REWARD_WEIGHT_TYPES = (
    {
        'id': 'unit_unlocks',
        'label': 'Unit unlocks',
        'description': 'Normal unit and building access rewards.',
    },
    {
        'id': 'power_unlocks',
        'label': 'Superweapon / aid unlocks',
        'description': 'Offensive, secondary, aid, and Special power unlocks.',
    },
    {
        'id': 'special_unlocks',
        'label': 'Special unit unlocks',
        'description': 'Campaign/map-only Special unit and building access rewards.',
    },
    {
        'id': 'economy',
        'label': 'Economy',
        'description': (
            'Starting credits, unit cost and build time, refinery income, '
            'and harvester capacity.'
        ),
    },
    {
        'id': 'unit_buffs',
        'label': 'Unit buffs',
        'description': 'Unit and building stat upgrades.',
    },
    {
        'id': 'power_buffs',
        'label': 'Superweapon buffs',
        'description': 'Upgrades for already-unlocked superweapons and aid powers.',
    },
)

# Buff types that are about the economy rather than a unit's fighting stats.
# They classify into the Economy main group, which exists so that Starting
# Credits has somewhere to live that is not a group of one. Every one of them
# still reaches exactly one unit; the faction-wide production reward that used
# to sit here was retired for being the only upgrade in the catalogue that
# did not.
ECONOMY_BUFF_TYPES = frozenset({
    'starting_credits', 'cost', 'production', 'income', 'storage',
})

# Sub-weights for the access groups. A player who wants tanks and not
# infantry could say so about upgrades but not about the unlocks themselves,
# which is the half of the catalogue they actually care about.
ACCESS_WEIGHT_TYPES = (
    ('infantry', 'Infantry'),
    ('units', 'Vehicles / naval'),
    ('aircraft', 'Aircraft'),
    ('defense', 'Defenses'),
    ('special_building', 'Special buildings'),
    ('other', 'Other unlocks'),
)

POWER_ACCESS_WEIGHT_TYPES = (
    ('offensive', 'Offensive superweapons'),
    ('secondary', 'Secondary superweapons'),
    ('aid', 'Aid powers'),
    ('other', 'Other powers'),
)

ECONOMY_WEIGHT_TYPES = (
    ('cost', 'Unit cost'),
    ('production', 'Build time'),
    ('income', 'Refinery income'),
    ('storage', 'Harvester capacity'),
    ('starting_credits', 'Starting credits'),
)

UNIT_BUFF_WEIGHT_TYPES = (
    ('speed', 'Movement'),
    ('health', 'Health'),
    ('damage', 'Damage'),
    ('range', 'Range'),
    ('reload', 'Fire rate'),
    ('armor', 'Armor'),
    ('self_healing', 'Healing'),
    ('sight', 'Vision'),
    ('ammo', 'Ammo'),
    ('passenger_capacity', 'Passenger capacity'),
    ('open_topped', 'Passenger firing'),
    ('cloak', 'Cloaking'),
    ('sensors', 'Sensors'),
    ('veteran', 'Veterancy'),
    ('build_limit', 'Unique / hero unit limit'),
    ('building_limit', 'Special building limit'),
    ('other', 'Other existing buffs'),
)

POWER_BUFF_WEIGHT_TYPES = (
    ('recharge', 'Recharge'),
    ('cost', 'Cost'),
    ('area', 'Area'),
    ('damage', 'Damage'),
    ('duration', 'Duration'),
    ('vision', 'Vision'),
    ('payload', 'Extra unit'),
    ('other', 'Other existing buffs'),
)

# Every main group that has sub-weights, and the table behind each. The UI,
# the saved settings and the planner all walk this rather than naming the
# sections one at a time, so adding a group is one edit here.
SUB_WEIGHT_SECTIONS = (
    {
        'id': 'unit_unlocks',
        'title': 'Unit unlock weights',
        'types': ACCESS_WEIGHT_TYPES,
    },
    {
        'id': 'power_unlocks',
        'title': 'Power unlock weights',
        'types': POWER_ACCESS_WEIGHT_TYPES,
    },
    {
        'id': 'economy',
        'title': 'Economy weights',
        'types': ECONOMY_WEIGHT_TYPES,
    },
    {
        'id': 'unit_buffs',
        'title': 'Unit buff weights',
        'types': UNIT_BUFF_WEIGHT_TYPES,
    },
    {
        'id': 'power_buffs',
        'title': 'Superweapon buff weights',
        'types': POWER_BUFF_WEIGHT_TYPES,
    },
)
# Special unlocks deliberately have none: 69 of the 70 share one category, so
# a table would be five sliders that all do the same thing.
SUB_WEIGHT_SECTION_BY_ID = {
    section['id']: section for section in SUB_WEIGHT_SECTIONS
}

_MAIN_IDS = tuple(item['id'] for item in MAIN_REWARD_WEIGHT_TYPES)
_SECTION_IDS = {
    section['id']: tuple(item[0] for item in section['types'])
    for section in SUB_WEIGHT_SECTIONS
}
_UNIT_BUFF_IDS = _SECTION_IDS['unit_buffs']
_POWER_BUFF_IDS = _SECTION_IDS['power_buffs']

# Not uniform, because the pool is not uniform and never was. There are 3,402
# unit buffs against 225 unit unlocks, and a buff restacks where an unlock is
# spent once, so equal weights do not mean an equal mix -- they mean buffs.
# These are what the launcher considers a normal run: unlocking things is the
# point, upgrading them is the texture, and the economy is seasoning.
DEFAULT_MAIN_WEIGHTS = {
    'unit_unlocks': 100,
    'power_unlocks': 55,
    'special_unlocks': 35,
    'unit_buffs': 45,
    'power_buffs': 20,
    'economy': 15,
}

# Starting Credits is one reward with a stack limit, so at an equal weight it
# reappears far more often than any single unit's upgrade line. It reads as
# filler at that rate, which is what it looked like when it turned up four
# times on one mission.
DEFAULT_UNIT_BUFF_WEIGHTS = {'starting_credits': 25}

DEFAULT_SECTION_WEIGHTS = {'economy': DEFAULT_UNIT_BUFF_WEIGHTS}

DEFAULT_REWARD_WEIGHTS = {
    'main': dict(DEFAULT_MAIN_WEIGHTS),
    **{
        section: {
            item_id: DEFAULT_SECTION_WEIGHTS.get(section, {}).get(
                item_id, DEFAULT_REWARD_WEIGHT
            )
            for item_id in item_ids
        }
        for section, item_ids in _SECTION_IDS.items()
    },
}


def clamp_reward_weight(value, default=DEFAULT_REWARD_WEIGHT):
    """Return one safe integer weight."""
    try:
        numeric = float(value)
        number = int(round(numeric)) if isfinite(numeric) else int(default)
    except (TypeError, ValueError):
        number = int(default)
    return max(0, min(MAX_REWARD_WEIGHT, number))


def normalize_reward_weights(value):
    """Return complete safe weights; absent legacy settings use defaults."""
    source = value if isinstance(value, dict) else {}
    normalized = {}
    legacy_unit_buffs = source.get('unit_buffs')
    legacy_unit_buffs = (
        legacy_unit_buffs if isinstance(legacy_unit_buffs, dict) else {}
    )
    for section, item_ids in (('main', _MAIN_IDS), *_SECTION_IDS.items()):
        section_source = source.get(section)
        if not isinstance(section_source, dict):
            section_source = {}
        if section == 'economy':
            # These five used to be unit-buff sub-weights before Economy
            # became a group of its own. Inherit whatever the player set
            # there rather than resetting their tuning to the default.
            section_source = {
                item_id: section_source.get(
                    item_id, legacy_unit_buffs.get(item_id)
                )
                for item_id in item_ids
                if section_source.get(item_id) is not None
                or legacy_unit_buffs.get(item_id) is not None
            }
        fallbacks = (
            DEFAULT_MAIN_WEIGHTS if section == 'main'
            else DEFAULT_SECTION_WEIGHTS.get(section, {})
        )
        normalized[section] = {
            item_id: clamp_reward_weight(
                section_source.get(
                    item_id,
                    fallbacks.get(item_id, DEFAULT_REWARD_WEIGHT),
                )
            )
            for item_id in item_ids
        }
    # A settings file written before the Economy group named it 'production'.
    # Carry that choice over rather than silently resetting it.
    if isinstance(source.get('main'), dict) and 'economy' not in source['main']:
        legacy = source['main'].get('production')
        if legacy is not None:
            normalized['main']['economy'] = clamp_reward_weight(legacy)
    return normalized


def reward_weights_are_default(value):
    return normalize_reward_weights(value) == DEFAULT_REWARD_WEIGHTS


def unit_buff_weight_type(buff_type):
    buff_type = str(buff_type or '')
    return buff_type if buff_type in _UNIT_BUFF_IDS else 'other'


def economy_weight_type(buff_type):
    buff_type = str(buff_type or '')
    return buff_type if buff_type in _SECTION_IDS['economy'] else 'cost'


def unit_unlock_weight_type(reward):
    """Return which kind of thing an access reward unlocks."""
    category = str(reward.get('access_category') or '')
    return category if category in _SECTION_IDS['unit_unlocks'] else 'other'


def power_unlock_weight_type(reward):
    """Return which kind of power an unlock reward grants."""
    category = str(reward.get('power_category') or '')
    return category if category in _SECTION_IDS['power_unlocks'] else 'other'


def sub_weight_type(main_type, reward):
    """Return the sub-weight id one reward uses, or ``None``."""
    if main_type == 'unit_buffs':
        return unit_buff_weight_type(reward.get('buff_type'))
    if main_type == 'power_buffs':
        return power_buff_weight_type(reward.get('power_buff_type'))
    if main_type == 'economy':
        return economy_weight_type(reward.get('buff_type'))
    if main_type == 'unit_unlocks':
        return unit_unlock_weight_type(reward)
    if main_type == 'power_unlocks':
        return power_unlock_weight_type(reward)
    return None


def power_buff_weight_type(buff_type):
    buff_type = str(buff_type or '')
    return buff_type if buff_type in _POWER_BUFF_IDS else 'other'


def main_reward_weight_type(reward):
    """Classify one canonical reward into a user-facing main weight."""
    if reward.get('enemy_reward'):
        return 'enemy_buffs'
    if reward.get('kind') == 'buff':
        if reward.get('power_buff_type'):
            return 'power_buffs'
        if str(reward.get('buff_type') or '') in ECONOMY_BUFF_TYPES:
            return 'economy'
        return 'unit_buffs'
    if reward.get('kind') == 'superweapon':
        return 'power_unlocks'
    if reward.get('special_reward') or reward.get('access_category') == 'special':
        return 'special_unlocks'
    return 'unit_unlocks'


def reward_selection_weight(reward, weights):
    """Return combined main/sub-weight; zero means never selectable."""
    if reward.get('enemy_reward'):
        return 0
    main_type = main_reward_weight_type(reward)
    try:
        weight = weights['main'][main_type]
        unit_weights = weights['unit_buffs']
        power_weights = weights['power_buffs']
    except (KeyError, TypeError):
        weights = normalize_reward_weights(weights)
        weight = weights['main'][main_type]
        unit_weights = weights['unit_buffs']
        power_weights = weights['power_buffs']
    del unit_weights, power_weights
    sub_type = sub_weight_type(main_type, reward)
    if sub_type is not None:
        section = weights.get(main_type) or {}
        weight *= section.get(sub_type, DEFAULT_REWARD_WEIGHT)
    return weight
