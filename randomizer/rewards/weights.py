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
            'Starting credits, faction-wide production speed, unit cost and '
            'build time, refinery income, and harvester capacity.'
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
# Credits has somewhere to live that is not a group of one.
ECONOMY_BUFF_TYPES = frozenset({
    'starting_credits', 'cost', 'production', 'income', 'storage',
})

UNIT_BUFF_WEIGHT_TYPES = (
    ('speed', 'Movement'),
    ('health', 'Health'),
    ('damage', 'Damage'),
    ('range', 'Range'),
    ('reload', 'Fire rate'),
    ('armor', 'Armor'),
    ('cost', 'Cost'),
    ('production', 'Production time'),
    ('self_healing', 'Healing'),
    ('sight', 'Vision'),
    ('ammo', 'Ammo'),
    ('storage', 'Harvester storage'),
    ('passenger_capacity', 'Passenger capacity'),
    ('open_topped', 'Passenger firing'),
    ('cloak', 'Cloaking'),
    ('sensors', 'Sensors'),
    ('veteran', 'Veterancy'),
    ('build_limit', 'Unique / hero unit limit'),
    ('building_limit', 'Special building limit'),
    ('income', 'Special building income'),
    ('starting_credits', 'Starting credits'),
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

_MAIN_IDS = tuple(item['id'] for item in MAIN_REWARD_WEIGHT_TYPES)
_UNIT_BUFF_IDS = tuple(item[0] for item in UNIT_BUFF_WEIGHT_TYPES)
_POWER_BUFF_IDS = tuple(item[0] for item in POWER_BUFF_WEIGHT_TYPES)

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

DEFAULT_REWARD_WEIGHTS = {
    'main': dict(DEFAULT_MAIN_WEIGHTS),
    'unit_buffs': {
        item_id: DEFAULT_UNIT_BUFF_WEIGHTS.get(
            item_id, DEFAULT_REWARD_WEIGHT
        )
        for item_id in _UNIT_BUFF_IDS
    },
    'power_buffs': {
        item_id: DEFAULT_REWARD_WEIGHT for item_id in _POWER_BUFF_IDS
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
    for section, item_ids in (
        ('main', _MAIN_IDS),
        ('unit_buffs', _UNIT_BUFF_IDS),
        ('power_buffs', _POWER_BUFF_IDS),
    ):
        section_source = source.get(section)
        if not isinstance(section_source, dict):
            section_source = {}
        fallbacks = {
            'main': DEFAULT_MAIN_WEIGHTS,
            'unit_buffs': DEFAULT_UNIT_BUFF_WEIGHTS,
        }.get(section, {})
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
    if main_type in {'unit_buffs', 'economy'}:
        # Economy shares the unit-buff sub-weights: they are the same buff
        # types, only grouped by what they do rather than where they apply,
        # so a player who turned Cost down keeps it down.
        sub_type = unit_buff_weight_type(reward.get('buff_type'))
        weight *= unit_weights[sub_type]
    elif main_type == 'power_buffs':
        sub_type = power_buff_weight_type(reward.get('power_buff_type'))
        weight *= power_weights[sub_type]
    return weight
