"""What a campaign run is set up with, as one table both windows can read.

The three campaign modes -- Classic, Mission List and Grid -- are the same
game in a different order, so almost every setting belongs to all three.
Three belong to Grid alone. That is the whole of the grouping, and it is
written here rather than in a window, because there are two windows now
and a setting described differently in each is a setting a player cannot
ask a question about.

Each row says where the value lives, what it is called, what kind of thing
it is, and what it may be. Nothing here draws anything: a screen turns a
row into a control, and the boundary turns one into a reply.
"""

from randomizer.rewards.arsenal import (
    ARSENAL_COUNT_MAXIMUM,
    ARSENAL_FACTIONS,
    ARSENAL_MODE,
    ARSENAL_POWER_TYPES,
    ARSENAL_TIERS,
    ARSENAL_UNIT_TYPES,
)
from randomizer.rewards.definitions import BUFF_TYPES, MAX_REWARDS_PER_CHECK
from randomizer.rewards.enemy_scaling import (
    ENEMY_BUFF_DEFINITIONS,
    ENEMY_BUFF_GROUP_DEFINITIONS,
    enemy_buff_capacity,
)
from randomizer.rewards.power_buff_definitions import POWER_BUFF_TYPES
from randomizer.rewards.starting import STARTING_REWARD_TYPE_DEFINITIONS
from randomizer.rewards.weights import (
    DEFAULT_REWARD_WEIGHTS,
    MAIN_REWARD_WEIGHT_TYPES,
    MAX_REWARD_WEIGHT,
    SUB_WEIGHT_SECTIONS,
)

from .campaign_catalogues import REWARD_NAME, SUPERWEAPON, UNIT_ACCESS

from .config import CAMPAIGN_FILTERS, DIFFICULTIES, GAME_SPEEDS, REWARD_MODES
from .settings_rows import (  # noqa: F401  (the table's own vocabulary)
    CHOICE,
    GROUPS,
    KINDS,
    LIMITS,
    MAP,
    NUMBER,
    SEARCH,
    SET,
    SWITCH,
    TEXT,
    TOP,
    WEIGHTS,
    by_key,
    full_key,
    hidden,
    row as _row,
)
from .settings_rows import rows_for as _rows_for


# A run cannot ask for more missions than the campaign has. The launcher
# counts them per filter; this is the ceiling a control offers, and the
# generator is what refuses an order it cannot fill.
MAXIMUM_MISSION_GOAL = 97

# Long enough for any name a player would type, short enough that a
# settings file cannot be filled with one.
MAXIMUM_SEED_LENGTH = 64

# The block of the settings that describes how a seed is made. The rest
# of the vocabulary -- the kinds, what a row is, where a value lives --
# is shared with the other table, in settings_rows.
GENERATION = 'generation'
# A block inside the generation block. Written as a path because that is
# what it is; nothing here needs a deeper one yet.
ACCESS_LIMITS = 'generation.access_limits'
ARSENAL = 'generation.arsenal'
ARSENAL_POWERS = 'generation.arsenal.power_counts'
REWARD_WEIGHTS = 'generation.reward_weights'
ENEMY_SCALING = 'generation.enemy_scaling'
ENEMY_CAPS = 'generation.enemy_scaling.caps'

# How many starting rewards a control offers. The launcher itself allows
# far more; a spinner that can reach four figures is a spinner nobody
# reaches the end of, and a run that starts with thirty rewards has
# already answered the question the setting was asking.
MAXIMUM_STARTING_REWARDS = 30


RUN_SETTINGS = (
    _row(
        'seed', 'Seed name', TEXT,
        'Type one to play a run somebody else played. Blank means a new '
        'one is made when the seed is generated.',
        maximum_length=MAXIMUM_SEED_LENGTH,
        # The classic window leaves this box empty while a generated seed
        # stands, so that pressing Generate does not silently replay the
        # run in progress. A second window showing the old seed in it
        # would be the same trap wearing a different face.
        blank_while_generated=True,
    ),
    _row(
        'campaign_filter', 'Campaign', CHOICE,
        'Which side\'s missions the run draws from.',
        choices=list(CAMPAIGN_FILTERS),
    ),
    _row(
        'mission_goal', 'Missions to finish', NUMBER,
        'How many missions a run is. Grid builds its board from this too.',
        minimum=1, maximum=MAXIMUM_MISSION_GOAL, step=1,
    ),
    _row(
        'difficulty', 'Difficulty', CHOICE,
        'What the game itself is played on.',
        choices=[name for name, _value in DIFFICULTIES],
    ),
    _row(
        'game_speed', 'Game speed', CHOICE,
        'The pace a mission starts at.',
        choices=[name for name, _value in GAME_SPEEDS],
    ),
)

REWARD_SETTINGS = (
    _row(
        'reward_mode', 'Reward mode', CHOICE,
        'Standard keeps a unit behind its own faction. Chaos draws from '
        'all four and lets any matching building make what is unlocked. '
        'Randomizer Arsenal gives each mission a mixed roster of its own.',
        where=GENERATION, choices=list(REWARD_MODES),
    ),
    _row(
        'rewards_per_objective', 'Rewards per objective', NUMBER,
        'How many rewards each objective is worth.',
        minimum=1, maximum=MAX_REWARDS_PER_CHECK, step=1,
    ),
    _row(
        'rewards_on_victory_only', 'Rewards only when a mission is finished',
        SWITCH,
        'Otherwise objectives pay as they are met, mid-mission.',
    ),
    _row(
        'use_act_based_reward_multipliers', 'Act-based reward multipliers',
        SWITCH,
        'Later acts pay more than earlier ones.',
    ),
    _row(
        'buff_allied_helpers', 'Buff allied helpers', SWITCH,
        'Whether a mission\'s friendly AI gets the run\'s upgrades too.',
        where=GENERATION,
    ),
    _row(
        'failure_assistance', 'Strengthen failed missions on retry', SWITCH,
        'Each retry makes the units that mission gives you a little better.',
        where=GENERATION,
    ),
)

POOL_SETTINGS = (
    _row(
        'randomize_unit_access', 'Randomize unit access', SWITCH,
        'Lock unearned tech, and hand it back as rewards.',
        where=GENERATION,
    ),
    _row(
        'start_with_tier_one_units', 'Start with basic Tier 1 units', SWITCH,
        'A floor under a run that has unlocked nothing yet.',
        where=GENERATION,
    ),
    _row(
        'start_with_tier_one_defenses', 'Start with basic Tier 1 defences',
        SWITCH,
        'The same floor, for what a base can build to defend itself.',
        where=GENERATION,
    ),
    _row(
        'include_buff_rewards', 'Buff rewards', SWITCH,
        'Rewards that improve a unit rather than unlocking one.',
        where=GENERATION,
    ),
    _row(
        'include_superweapon_rewards', 'Superweapon rewards', SWITCH,
        'The offensive ones.', where=GENERATION,
    ),
    _row(
        'include_secondary_superweapon_rewards', 'Secondary superweapons',
        SWITCH, 'The ones that are not an attack.', where=GENERATION,
    ),
    _row(
        'include_aid_power_rewards', 'Support and aid powers', SWITCH,
        'Powers that help rather than destroy.', where=GENERATION,
    ),
    _row(
        'include_power_buff_rewards', 'Power buff rewards', SWITCH,
        'Rewards that improve a power you already have.', where=GENERATION,
    ),
    _row(
        'include_defensive_buildings', 'Defensive building rewards', SWITCH,
        'Base defences among the buildings a run can unlock.',
        where=GENERATION,
    ),
    _row(
        'include_special_buildings', 'Special economy buildings', SWITCH,
        'The economy buildings a mission map carries.', where=GENERATION,
    ),
    _row(
        'include_special_rewards', 'Campaign-only special rewards', SWITCH,
        'What only one map has, offered as a reward.', where=GENERATION,
    ),
    _row(
        'unlimited_hero_units', 'Unlimited hero units', SWITCH,
        'Lift the build limit on unique units.', where=GENERATION,
    ),
)

LIMIT_SETTINGS = (
    _row(
        'enabled', 'Limit what one reward unlocks', SWITCH,
        'On, a reward opens a few units rather than everything of its kind.',
        where=ACCESS_LIMITS,
    ),
    _row(
        'units', 'Units per reward', NUMBER,
        'How many units one access reward hands over.',
        where=ACCESS_LIMITS, minimum=1, maximum=8, step=1,
        needs=(f'{ACCESS_LIMITS}.enabled', True),
    ),
    _row(
        'powers', 'Powers per reward', NUMBER,
        'The same, for superweapons and support powers.',
        where=ACCESS_LIMITS, minimum=1, maximum=8, step=1,
        needs=(f'{ACCESS_LIMITS}.enabled', True),
    ),
)

UNIT_BUFF_CATALOGUE = [
    {'id': str(entry['id']),
     'label': str(entry.get('setting_label') or entry['id'])}
    for entry in BUFF_TYPES
]
POWER_BUFF_CATALOGUE = [
    {'id': str(entry['id']),
     'label': str(entry.get('setting_label') or entry['id'])}
    for entry in POWER_BUFF_TYPES
]

BUFF_TYPE_SETTINGS = (
    _row(
        'enabled_buff_types', 'Unit buffs a reward may be', SET,
        'Turn one off and no reward improves a unit that way.',
        where=GENERATION,
        catalogue=UNIT_BUFF_CATALOGUE,
    ),
    _row(
        'enabled_power_buff_types', 'Power buffs a reward may be', SET,
        'The same, for what a reward can improve about a power.',
        where=GENERATION,
        catalogue=POWER_BUFF_CATALOGUE,
    ),
    # The same question asked of one thing rather than of all of them.
    # Turning cloaking off everywhere is a different run from turning it
    # off for the one unit that made a mission unwinnable with it.
    _row(
        'excluded_unit_buff_types', 'Upgrades one unit may never get', MAP,
        'Name a unit, then turn off the upgrades it is never offered. '
        'Everything else about that unit stays as it is.',
        where=GENERATION,
        catalogue=UNIT_BUFF_CATALOGUE,
        catalogue_name=UNIT_ACCESS,
    ),
    _row(
        'excluded_power_buff_types', 'Upgrades one power may never get', MAP,
        'The same, for what a superweapon or support power is offered.',
        where=GENERATION,
        catalogue=POWER_BUFF_CATALOGUE,
        catalogue_name=SUPERWEAPON,
    ),
)

STARTING_SETTINGS = (
    _row(
        'starting_reward_count', 'Rewards to start with', NUMBER,
        'Handed over before the first mission, drawn from the kinds below.',
        where=GENERATION, minimum=0, maximum=MAXIMUM_STARTING_REWARDS, step=1,
    ),
    _row(
        'starting_reward_types', 'Kinds a starting reward may be', SET,
        'Turn one off and nothing of that kind is handed over at the start.',
        where=GENERATION,
        catalogue=[
            {'id': str(entry['id']), 'label': str(entry['label'])}
            for entry in STARTING_REWARD_TYPE_DEFINITIONS
        ],
        needs=(f'{GENERATION}.starting_reward_count', True),
    ),
    _row(
        'starting_unlock_rewards', 'Rewards to start with, by name',
        SEARCH,
        'Named here, a reward is handed over at the start whatever the '
        'seed rolls -- on top of the ones drawn above, not instead of '
        'them.',
        where=GENERATION, catalogue_name=REWARD_NAME,
    ),
)

ARSENAL_SETTINGS = (
    _row(
        'factions', 'Sides an arsenal draws from', SET,
        'Each mission gets a mixed roster; these are what it is mixed from.',
        where=ARSENAL,
        catalogue=[
            {'id': faction, 'label': faction} for faction in ARSENAL_FACTIONS
        ],
        needs=(f'{GENERATION}.reward_mode', ARSENAL_MODE),
    ),
) + tuple(
    _row(
        unit_type,
        f'{tier.replace("_", " ").title()} {unit_type}',
        NUMBER,
        f'How many {unit_type} of that tier one roster carries.',
        where=f'{ARSENAL}.roster_sizes.{tier}',
        minimum=0, maximum=ARSENAL_COUNT_MAXIMUM, step=1,
        needs=(f'{GENERATION}.reward_mode', ARSENAL_MODE),
    )
    for tier in ARSENAL_TIERS
    for unit_type in ARSENAL_UNIT_TYPES
) + tuple(
    _row(
        power_type, f'{power_type.title()} powers', NUMBER,
        'How many powers of that kind one roster carries.',
        where=ARSENAL_POWERS,
        minimum=0, maximum=ARSENAL_COUNT_MAXIMUM, step=1,
        needs=(f'{GENERATION}.reward_mode', ARSENAL_MODE),
    )
    for power_type in ARSENAL_POWER_TYPES
)

GRID_SETTINGS = (
    _row(
        'grid_two_start_positions', 'Two starting positions', SWITCH,
        'Open the board from two corners rather than one.',
        mode='Grid Mode',
    ),
    _row(
        'hide_locked_grid_missions', 'Hide locked mission names', SWITCH,
        'A locked tile shows a question mark instead of its title.',
        mode='Grid Mode',
    ),
    _row(
        'unlock_all_rewards_after_final_grid_mission',
        'Release every reward at the goal', SWITCH,
        'When the goal mission is done, what is left is handed over.',
        mode='Grid Mode',
    ),
)

EXCLUSION_SETTINGS = (
    _row(
        'excluded_unit_access_ids', 'Units left out', SEARCH,
        'Named here, a unit is never unlocked by a reward and never turns '
        'up in the pool a run draws from.',
        where=GENERATION, catalogue_name=UNIT_ACCESS,
    ),
    _row(
        'excluded_superweapon_ids', 'Powers left out', SEARCH,
        'The same, for superweapons and support powers. A power several '
        'sides share is not one side\'s to leave out, so it is not listed.',
        where=GENERATION, catalogue_name=SUPERWEAPON,
    ),
)

# What a weight is worth is decided against the others in its group, so a
# group is one control rather than a run of them. Every weight is still a
# setting of its own underneath: that is what is written when one moves.
WEIGHT_GROUPS = (
    (
        'main',
        'Kinds of reward',
        tuple(
            (item['id'], item['label'], item['description'])
            for item in MAIN_REWARD_WEIGHT_TYPES
        ),
    ),
) + tuple(
    (
        section['id'],
        section['title'],
        tuple((item[0], item[1], '') for item in section['types']),
    )
    for section in SUB_WEIGHT_SECTIONS
)


def _weight_rows(group, title, items):
    """Return one group's control and the settings it draws."""
    where = f'{REWARD_WEIGHTS}.{group}'
    numbers = tuple(
        hidden(_row(
            item_id, label, NUMBER,
            description or f'How often {label.lower()} comes up.',
            where=where, minimum=0, maximum=MAX_REWARD_WEIGHT, step=5,
            default=DEFAULT_REWARD_WEIGHTS.get(group, {}).get(
                item_id, MAX_REWARD_WEIGHT
            ),
        ))
        for item_id, label, description in items
    )
    return (
        _row(
            group, title, WEIGHTS,
            'How often each of these comes up, against the others here. '
            'Zero never comes up at all.',
            where=REWARD_WEIGHTS,
            entries=[f'{where}.{item_id}' for item_id, _l, _d in items],
        ),
    ) + numbers


WEIGHT_SETTINGS = tuple(
    row
    for group, title, items in WEIGHT_GROUPS
    for row in _weight_rows(group, title, items)
)

# What the enemy can be given at most, when every bonus is allowed and
# each is stacked as far as it goes. Asking for more than this is asking
# for something the generator cannot hand out.
ENEMY_BUFF_CAPACITY = enemy_buff_capacity({})
# A ceiling that is not a number but a question: how much the bonuses
# that are allowed right now could add up to. The boundary works it
# out; the table only says which rows are asking.
ENEMY_CAPACITY = 'enemy_capacity'
_ENEMY_GROUP_BY_ID = {
    effect_id: group['label']
    for group in ENEMY_BUFF_GROUP_DEFINITIONS
    for effect_id in group['effect_ids']
}
_ENEMY_GROUP_ORDER = {
    group['label']: index
    for index, group in enumerate(ENEMY_BUFF_GROUP_DEFINITIONS)
}


def _enemy_buff_entry(definition):
    stacks = int(definition.get('maximum_stacks', 1))
    percent = definition.get('per_stack_percent')
    return {
        'id': str(definition['id']),
        'label': str(definition.get('name') or definition['id']),
        'group': _ENEMY_GROUP_BY_ID.get(str(definition['id']), 'Other'),
        'maximum_stacks': stacks,
        'note': (
            f'{percent}% a stack, up to {stacks}' if percent
            else f'up to {stacks}'
        ),
    }


ENEMY_BUFF_CATALOGUE = sorted(
    (_enemy_buff_entry(definition) for definition in ENEMY_BUFF_DEFINITIONS),
    key=lambda entry: (
        _ENEMY_GROUP_ORDER.get(entry['group'], 9),
        entry['label'].casefold(),
    ),
)
ALLOWED_BUFFS = f'{ENEMY_SCALING}.allowed_buff_ids'

# How far each bonus may be stacked, as one number a player reads as
# "up to this many, and nought means never". Which is two settings
# underneath -- whether the enemy may be given it at all, and how much of
# it -- because a bonus allowed with a limit of nought and a bonus not
# allowed are the same enemy. The screen asks the question once; the
# boundary keeps the two in step.
ENEMY_CAP_SETTINGS = tuple(
    hidden(_row(
        entry['id'], entry['label'], NUMBER,
        f'How much of it the enemy may collect: {entry["note"]}.',
        where=ENEMY_CAPS,
        minimum=0,
        maximum=int(entry['maximum_stacks']),
        step=1,
        default=int(entry['maximum_stacks']),
        gated_by=ALLOWED_BUFFS,
        group=entry['group'],
        note=entry['note'],
    ))
    for entry in ENEMY_BUFF_CATALOGUE
)

ENEMY_SETTINGS = (
    _row(
        'maximum_total_buffs', 'Bonuses the enemy collects', NUMBER,
        'How many the run hands the enemy over its whole length, out of '
        'what the bonuses below add up to. Zero is an enemy that never '
        'grows.',
        where=ENEMY_SCALING,
        minimum=0, maximum=ENEMY_BUFF_CAPACITY, step=1, default=0,
        ceiling=ENEMY_CAPACITY,
    ),
    _row(
        'caps', 'What the enemy may be given, and how much of each', LIMITS,
        'Nought is a bonus the enemy is never handed at all. The rest is '
        'how far one bonus may be stacked over a whole run.',
        where=ENEMY_SCALING,
        entries=[f'{ENEMY_CAPS}.{entry["id"]}' for entry in ENEMY_BUFF_CATALOGUE],
    ),
    _row(
        'allowed_buff_ids', 'Bonuses the enemy may be given', SET,
        'Which of them the enemy may be handed. Written for it by the '
        'limits above, where nought means never.',
        where=ENEMY_SCALING,
        catalogue=ENEMY_BUFF_CATALOGUE,
        # Everything, written as one entry rather than as forty-eight.
        # What the launcher keeps has always said it this way, and a
        # settings file that says "all of them" still means all of them
        # after a submod adds one.
        wildcard='*',
        hidden=True,
    ),
) + ENEMY_CAP_SETTINGS


SECTIONS = (
    ('Run', RUN_SETTINGS),
    ('Rewards', REWARD_SETTINGS),
    ('Reward pool', POOL_SETTINGS),
    ('Access limits', LIMIT_SETTINGS),
    ('Starting rewards', STARTING_SETTINGS),
    ('What is left out', EXCLUSION_SETTINGS),
    ('How often a reward comes up', WEIGHT_SETTINGS),
    ('What the enemy is given', ENEMY_SETTINGS),
    ('Arsenal', ARSENAL_SETTINGS),
    ('What a buff may be', BUFF_TYPE_SETTINGS),
    ('Grid', GRID_SETTINGS),
)

BY_KEY = by_key(SECTIONS)


def rows_for(mode):
    """Return the settings one campaign mode shows, section by section."""
    return _rows_for(SECTIONS, mode)
